import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
function planState(j){
 if(j.approved&&!j.superseded)return '<span class="approval">已占额 · 当前生效方案</span>';
 if(j.approved)return '<span class="approval superseded">已被新方案替换</span>';
 if(j.rejection&&j.rejection.gaps&&j.rejection.gaps.length)return '<span class="approval rejected">批准曾被拒绝 · 产能不足</span>';
 return '<span>待负责人复核</span>';
}
function approvalPanel(j){
 if(j.status!=='completed')return '';
 if(j.approved&&!j.superseded)return '<p class="approval">已按建议份数整段占额，是档口「'+esc(j.stall||'未入账')+'」的当前生效方案。</p><a class="text-link" href="#/capacity">核对每日产能、剩余与占用明细 ↗</a>';
 if(j.approved)return '<p>该方案已被同档口更新的方案替换，占用已按新旧差额转移。</p><p class="hint">历史归档简报保留在收件箱；仅当前生效方案可新建分发。</p>';
 let h='';
 const r=j.rejection;
 if(r&&r.gaps&&r.gaps.length){
  h+='<div class="rejection"><h3>最近一次批准被拒绝 · 逐日缺口</h3><div class="table-wrap"><table><thead><tr><th>日期</th><th>当日产能</th><th>其他方案已占</th><th>本方案需要</th><th>缺口</th></tr></thead><tbody>'+r.gaps.map(g=>'<tr><td>'+esc(g.date)+'</td><td>'+fmt(g.capacity)+'</td><td>'+fmt(g.occupied)+'</td><td>'+fmt(g.required)+'</td><td>'+fmt(g.missing)+'</td></tr>').join('')+'</tbody></table></div><p class="hint">'+esc(r.message||'')+(r.at?' · '+date(r.at):'')+'</p></div>';
 }
 h+=(session.user.role==='admin'?'<button class="primary" id="approve-job">批准并整段占额</button>':'<p class="hint">待业务负责人复核批准。</p>');
 h+='<p class="hint">批准按建议份数逐日占额；任一日期产能不足将整体拒绝并列出缺口。仅当前生效的批准方案可进入定时分发档案。</p>';
 return h;
}
export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>')+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+'<span>'+date(j.created_at)+'</span>'+planState(j)+'</div>'+(j.status==='completed'?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+approvalPanel(j)+'</section></div><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':'<section class="panel empty">'+(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台调整参数或数据。':'后台正在执行计算。点击刷新结果查看最新进展。')+'<a href="#/workbench">返回工作台 ↗</a></section>');
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，建议份数已整段占额');}catch(e){notify(e.message,true);}await refresh();});}
