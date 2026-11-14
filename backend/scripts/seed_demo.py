import time, json
from datetime import date, timedelta
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, CapacityDay, Occupancy
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.services import ledger
from src.utils.security import hash_password
from src.utils.serialization import checksum
SEED_CAPACITY = 700  # 厨房每日总产能（份），仅写入缺失日期，不覆盖用户调整
def ensure_capacity(db, start, end):
    existing = set(db.scalars(select(CapacityDay.date)))
    day = start
    while day <= end:
        if day.isoformat() not in existing:
            db.add(CapacityDay(date=day.isoformat(), capacity=SEED_CAPACITY, updated_at=time.time(), updated_by='seed'))
        day += timedelta(days=1)
    db.flush()
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        j=db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name']))
        if not j:
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595)
            db.add(j);db.flush()
            first=date.fromisoformat(result['table']['rows'][0]['date'])
            last=date.fromisoformat(result['table']['rows'][-1]['date'])
            ensure_capacity(db, first, last+timedelta(days=14))
            ledger.approve(db, j.id, 'seed')  # 基线方案经台账整段占额，保持账实一致
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        # 升级回填：历史已批准且仍生效但尚未入账的方案按顺序补登占用（幂等，不覆盖用户修改）
        pending=[x for x in db.scalars(select(Job).where(Job.approved==True,Job.superseded==False).order_by(Job.id)) if not db.scalar(select(func.count()).select_from(Occupancy).where(Occupancy.job_id==x.id))]
        if pending:
            days=[date.fromisoformat(row['date']) for x in pending for row in (x.result or {}).get('table',{}).get('rows',[])]
            if days: ensure_capacity(db, min(days), max(days))
            for x in pending:
                x.approved=False; db.flush()
                ledger.approve(db, x.id, 'seed')
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
