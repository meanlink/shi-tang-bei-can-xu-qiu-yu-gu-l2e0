"""厨房逐日产能台账与占用账。

规则：
- 厨房按每日总产能接单，全部档口共享同一天的产能。
- 批准试算时按建议份数整段占额；任一日期不足即整体拒绝，并列出逐日缺口。
- 同一档口更换已批准方案：重叠日期只计新旧差额，未重叠日期释放或新增；
  任一日期失败则保留原方案全部占用（整事务回滚，占用不变）。
- 并发批准与调低产能都不能超额：进程内互斥锁 + 数据库行锁（FOR UPDATE）双保险，
  所有占用变更先锁档口行、再按日期顺序锁产能行。
- 响应丢失后重试不重复占额：已批准任务的重复批准是幂等空操作。
"""
import threading
import time
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.models import Dataset, Job, Stall, CapacityDay, Occupancy
from src.services.audit import record

LEDGER_LOCK = threading.RLock()  # 进程内互斥；跨进程由数据库行锁兜底
MAX_SPAN_DAYS = 93
MAX_CAPACITY = 200000


def _parse_day(value, label='日期'):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise HTTPException(422, f'{label}须为 YYYY-MM-DD')


def _stall_of(db, job):
    dataset = db.get(Dataset, job.dataset_id)
    if not dataset:
        raise HTTPException(409, '数据批次不存在，无法计入产能台账')
    meals = {str(row.get('meal', '')).strip() for row in dataset.records if str(row.get('meal', '')).strip()}
    if len(meals) != 1:
        raise HTTPException(409, '数据批次档口不唯一，无法计入产能台账')
    return meals.pop()


def _plan_rows(job):
    rows = (job.result or {}).get('table', {}).get('rows', [])
    plan = {}
    for row in rows:
        day = _parse_day(row.get('date'), '结果日期').isoformat()
        try:
            portions = int(round(float(row.get('plan'))))
        except (TypeError, ValueError, OverflowError):
            raise HTTPException(409, '结果建议份数无效，无法占额')
        if portions < 0:
            raise HTTPException(409, '结果建议份数无效，无法占额')
        plan[day] = plan.get(day, 0) + portions
    if not plan:
        raise HTTPException(409, '结果缺少建议明细，无法占额')
    return plan


def _ensure_stall(db, name):
    stall = db.scalar(select(Stall).where(Stall.name == name))
    if stall:
        return stall
    try:
        with db.begin_nested():
            stall = Stall(name=name)
            db.add(stall)
            db.flush()
    except IntegrityError:  # 并发已建同名档口，回滚到保存点后重读
        stall = db.scalar(select(Stall).where(Stall.name == name))
    db.commit()
    return stall


def _ensure_capacity_rows(db, days):
    existing = set(db.scalars(select(CapacityDay.date).where(CapacityDay.date.in_(days))))
    for day in days:
        if day in existing:
            continue
        try:
            with db.begin_nested():
                db.add(CapacityDay(date=day, capacity=0, updated_at=time.time(), updated_by='system'))
                db.flush()
        except IntegrityError:  # 并发已建行，锁定读取时可见
            pass


def _locked_capacity(db, days):
    rows = db.scalars(select(CapacityDay).where(CapacityDay.date.in_(days)).order_by(CapacityDay.date).with_for_update())
    return {row.date: row for row in rows}


def _occupied_by_date(db, days, lock=True):
    """返回每日全厨房已占用合计与按方案明细。lock=True 时为当前读，配合产能行锁保证不超额。"""
    stmt = select(Occupancy.date, Occupancy.job_id, Occupancy.stall, Occupancy.portions).where(Occupancy.date.in_(days))
    if lock:
        stmt = stmt.with_for_update()
    totals, plans = {}, {}
    for day, job_id, stall, portions in db.execute(stmt):
        totals[day] = totals.get(day, 0) + portions
        plans.setdefault(day, []).append({'job_id': job_id, 'stall': stall, 'portions': portions})
    return totals, plans


def approve(db, job_id, actor):
    """批准试算并整段占额。返回落库后的 Job；产能不足时先落库拒绝记录再抛 409。"""
    with LEDGER_LOCK:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, '分析任务不存在')
        if job.status != 'completed':
            raise HTTPException(409, '仅已完成结果可以批准')
        stall_name = _stall_of(db, job)
        plan = _plan_rows(job)
        stall = _ensure_stall(db, stall_name)
        for _ in range(3):
            try:
                stall = db.get(Stall, stall.id, with_for_update=True, populate_existing=True)
                job = db.get(Job, job_id, with_for_update=True, populate_existing=True)
                if job.approved:
                    db.commit()  # 幂等：响应丢失后的重试不重复占额
                    return job
                old_id = stall.current_job_id
                old_rows = list(db.scalars(select(Occupancy).where(Occupancy.job_id == old_id))) if old_id else []
                old_by_date = {}
                for row in old_rows:
                    old_by_date[row.date] = old_by_date.get(row.date, 0) + row.portions
                days = sorted(set(plan) | set(old_by_date))
                _ensure_capacity_rows(db, days)
                caps = _locked_capacity(db, days)
                totals, _ = _occupied_by_date(db, days)
                gaps = []
                for day in days:
                    required = plan.get(day, 0)
                    if not required:
                        continue
                    others = totals.get(day, 0) - old_by_date.get(day, 0)  # 重叠日期只算新旧差额
                    capacity = caps[day].capacity
                    if others + required > capacity:
                        gaps.append({'date': day, 'capacity': capacity, 'occupied': others, 'required': required, 'missing': others + required - capacity})
                if gaps:
                    message = '；'.join(f"{g['date']} 缺口 {g['missing']} 份（产能 {g['capacity']}，其他方案已占 {g['occupied']}，本方案需 {g['required']}）" for g in gaps[:5])
                    if len(gaps) > 5:
                        message += f'；另有 {len(gaps) - 5} 天不足'
                    job.rejection = {'at': time.time(), 'by': actor, 'message': message, 'gaps': gaps}
                    record(db, actor, 'job.approve.rejected', {'id': job.id, 'stall': stall_name, 'gaps': gaps})
                    db.commit()  # 只落库拒绝记录，原方案占用保持不变
                    raise HTTPException(409, f'厨房产能不足，已整体拒绝：{message}')
                for row in old_rows:  # 未重叠日期释放、重叠日期按差额重记
                    db.delete(row)
                db.flush()
                for day in sorted(plan):
                    if plan[day] > 0:
                        db.add(Occupancy(job_id=job.id, stall=stall_name, date=day, portions=plan[day]))
                if old_id and old_id != job.id:
                    old_job = db.get(Job, old_id)
                    if old_job:
                        old_job.superseded = True
                job.approved = True
                job.superseded = False
                job.stall = stall_name
                job.rejection = None
                stall.current_job_id = job.id
                record(db, actor, 'job.approve', {'id': job.id, 'stall': stall_name, 'days': len(plan), 'portions': sum(plan.values()), 'replaced': old_id})
                db.commit()
                return job
            except IntegrityError:
                db.rollback()
    raise HTTPException(409, '产能台账繁忙，请重试')


def set_capacity(db, actor, start_raw, end_raw, capacity):
    """设置逐日总产能；调低后不得低于当日已占用量。"""
    start = _parse_day(start_raw)
    end = _parse_day(end_raw) if end_raw else start
    if end < start:
        raise HTTPException(422, '截止日期不能早于起始日期')
    if (end - start).days > MAX_SPAN_DAYS:
        raise HTTPException(422, f'单次最多设置 {MAX_SPAN_DAYS} 天')
    capacity = int(capacity)
    if not 0 <= capacity <= MAX_CAPACITY:
        raise HTTPException(422, f'每日产能须为 0~{MAX_CAPACITY} 的整数')
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    with LEDGER_LOCK:
        for _ in range(3):
            try:
                _ensure_capacity_rows(db, days)
                caps = _locked_capacity(db, days)
                totals, _ = _occupied_by_date(db, days)
                violations = [{'date': day, 'occupied': totals.get(day, 0), 'requested': capacity} for day in days if totals.get(day, 0) > capacity]
                if violations:
                    record(db, actor, 'capacity.update.rejected', {'violations': violations})
                    db.commit()
                    first = violations[0]
                    message = f"调低后产能将低于已占用量：{first['date']} 已占 {first['occupied']} 份，不能设为 {first['requested']} 份"
                    if len(violations) > 1:
                        message += f'；另有 {len(violations) - 1} 天冲突'
                    raise HTTPException(409, message)
                for day in days:
                    row = caps[day]
                    row.capacity = capacity
                    row.updated_at = time.time()
                    row.updated_by = actor
                record(db, actor, 'capacity.update', {'from': days[0], 'to': days[-1], 'capacity': capacity})
                db.commit()
                return days
            except IntegrityError:
                db.rollback()
    raise HTTPException(409, '产能台账繁忙，请重试')


def ledger(db, start_raw=None, end_raw=None):
    """逐日台账：每日总量、已占用、剩余与占用方案明细。默认窗口覆盖今天与已有台账日期起四周。"""
    today = date.today()
    known = [date.fromisoformat(d) for d in db.scalars(select(CapacityDay.date))]
    known += [date.fromisoformat(d) for d in db.scalars(select(Occupancy.date).distinct())]
    if start_raw:
        start = _parse_day(start_raw)
    elif end_raw:
        start = _parse_day(end_raw) - timedelta(days=27)
    else:
        start = min([today] + known) if known else today
    end = _parse_day(end_raw) if end_raw else start + timedelta(days=27)
    if end < start:
        raise HTTPException(422, '截止日期不能早于起始日期')
    if (end - start).days > MAX_SPAN_DAYS:
        raise HTTPException(422, f'单次最多查询 {MAX_SPAN_DAYS} 天')
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    caps = {row.date: row for row in db.scalars(select(CapacityDay).where(CapacityDay.date.in_(days)))}
    totals, plans = _occupied_by_date(db, days, lock=False)
    job_ids = {p['job_id'] for entries in plans.values() for p in entries}
    names = {j.id: j.name for j in db.scalars(select(Job).where(Job.id.in_(job_ids)))} if job_ids else {}
    current = {s.name: s.current_job_id for s in db.scalars(select(Stall))}
    out = []
    for day in days:
        cap = caps.get(day)
        capacity = cap.capacity if cap else 0
        occupied = totals.get(day, 0)
        entries = [{**p, 'job': names.get(p['job_id'], ''), 'current': current.get(p['stall']) == p['job_id']} for p in plans.get(day, [])]
        out.append({'date': day, 'weekday': '周' + '一二三四五六日'[date.fromisoformat(day).weekday()], 'configured': bool(cap), 'capacity': capacity, 'occupied': occupied, 'remaining': capacity - occupied, 'plans': entries})
    return {'from': days[0], 'to': days[-1], 'days': out}
