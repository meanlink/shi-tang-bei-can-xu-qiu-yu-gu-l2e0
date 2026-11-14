import {capacity} from '../api/entities.js';
import {session} from '../stores/session.js';
import {workspace} from '../stores/workspace.js';
import {heading} from '../components/common/shell.js';
import {esc,fmt,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
function stateOf(d){
 if(!d.configured)return ['未配置','state-none'];
 if(d.remaining<0)return ['超额','state-over'];
 if(d.remaining===0&&d.occupied>0)return ['已满','state-full'];
 if(d.remaining<=Math.ceil(d.capacity*0.1))return ['紧张','state-tight'];
 return ['充足','state-ok'];
}
function ledgerTable(days){
 if(!days.length)return '<div class="empty">窗口内没有台账记录，调整查询窗口或先设置每日产能。</div>';
 return '<div class="table-wrap"><table><thead><tr><th>日期</th><th>星期</th><th>每日产能</th><th>已占用</th><th>剩余</th><th>状态</th><th>占用方案明细</th></tr></thead><tbody>'+days.map(d=>{const [label,cls]=stateOf(d);return '<tr><td>'+esc(d.date)+'</td><td>'+esc(d.weekday)+'</td><td>'+(d.configured?fmt(d.capacity):'未配置')+'</td><td>'+fmt(d.occupied)+'</td><td>'+(d.configured?fmt(d.remaining):'—')+'</td><td><span class="cap-state '+cls+'">'+label+'</span></td><td>'+(d.plans.length?'<ul class="plan-list">'+d.plans.map(p=>'<li>'+esc(p.stall)+' · '+esc(p.job||'#'+p.job_id)+' · '+fmt(p.portions)+' 份'+(p.current?'':'（已替换）')+'</li>').join('')+'</ul>':'<span class="muted">—</span>')+'</td></tr>';}).join('')+'</tbody></table></div>';
}
export async function capacityPage(){
 const q=workspace.capacityQuery,data=await capacity.list(q&&q.from,q&&q.to);
 workspace.capacityQuery={from:data.from,to:data.to};
 const days=data.days||[],totals=days.reduce((a,d)=>({cap:a.cap+d.capacity,occ:a.occ+d.occupied}),{cap:0,occ:0});
 return heading('06 / CAPACITY','厨房产能台账','厨房按每日总产能接单，全部档口共享同一天产能。批准试算按建议份数整段占额；任一日期不足即整体拒绝并列出缺口。','<button class="button" id="refresh-capacity">刷新台账 ↻</button>')
 +'<section class="metrics capacity-metrics">'+[['窗口总产能',totals.cap,'份'],['已占用',totals.occ,'份'],['剩余可接',totals.cap-totals.occ,'份'],['有占用的天数',days.filter(d=>d.occupied>0).length,'天']].map(([k,v,u])=>'<div><span>'+k+'</span><strong>'+fmt(v)+'<small>'+u+'</small></strong></div>').join('')+'</section>'
 +'<div class="capacity-grid"><section class="panel"><div class="section-title"><h2>查询窗口</h2><span>'+esc(data.from)+' → '+esc(data.to)+'</span></div>'
 +'<form id="capacity-query"><label>起始日期<input type="date" name="from" value="'+esc(data.from)+'" required></label><label>截止日期<input type="date" name="to" value="'+esc(data.to)+'" required></label><button class="button" type="submit">查询台账</button></form>'
 +'<div class="section-title"><h2>设置每日总产能</h2><span>仅业务负责人</span></div>'
 +'<form id="capacity-form"><label>起始日期<input type="date" name="date_from" value="'+esc(data.from)+'" required></label><label>截止日期（留空为单日）<input type="date" name="date_to"></label><label>每日总产能（份）<input type="number" name="capacity" min="0" max="200000" step="1" value="700" required></label><button class="primary" type="submit" '+(session.user.role!=='admin'?'disabled':'')+'>保存产能</button></form>'
 +'<p class="hint">调低产能不能低于当日已占用量，否则保存被拒绝。同一档口更换方案只按新旧差额入账；并发批准与失败重试由台账事务保护，不会超额或重复占额。</p></section>'
 +'<section class="panel"><div class="section-title"><h2>逐日产能与占用</h2><span>'+days.length+' 天</span></div>'+ledgerTable(days)+'</section></div>';
}
export function bindCapacity(refresh){
 document.querySelector('#refresh-capacity').onclick=refresh;
 submit(document.querySelector('#capacity-query'),async f=>{workspace.capacityQuery={from:f.get('from'),to:f.get('to')};await refresh();});
 submit(document.querySelector('#capacity-form'),async f=>{await capacity.set({date_from:f.get('date_from'),date_to:f.get('date_to')||null,capacity:Number(f.get('capacity'))});notify('每日产能已保存');await refresh();});
}
