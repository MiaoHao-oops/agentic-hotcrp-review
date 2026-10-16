const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={deploy_wait:'等待服务更新',deleting:'删除中',delete_failed:'删除失败',cancelled:'已取消',queued:'等待中',researching:'调查会议中',running:'Agent 运行中',ready:'可投稿',reviewing:'审稿中',done:'已完成',failed:'需要重试',superseded:'历史版本'};
const badge=s=>`<span class="badge ${esc(s)}">${labels[s]||esc(s)}</span>`;
const date=t=>new Date(t*1000).toLocaleString('zh-CN');
let data=null, busy=false, lastState="", refreshing=false;
async function api(url,options={}){const r=await fetch(url,options);if(!r.ok){let e=await r.json().catch(()=>({detail:r.statusText}));throw Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail));}return r.json();}
function fail(e){$('#error').hidden=false;$('#error').textContent=e.message;}
function safeLink(s){try{let u=new URL(s);return ['http:','https:'].includes(u.protocol)?esc(u.href):'#';}catch{return '#';}}
function duration(seconds){seconds=Math.max(0,Math.floor(seconds));return seconds<60?`${seconds} 秒`:`${Math.floor(seconds/60)} 分 ${seconds%60} 秒`;}
function progressCard(j){const p=j.progress;if(!p)return '';const end=j.status==='running'?Date.now()/1000:(j.finished||p.updated||j.started);return `<div class="task-progress"><strong>${esc(p.label)}</strong><ol class="stage-list">${p.steps.map((s,i)=>`<li class="${j.status==='done'||i<p.index?'complete':i===p.index&&j.status==='running'?'current':''}">${esc(s)}</li>`).join('')}</ol>${j.started?`<p>${j.status==='running'?'已运行':'本次耗时'} ${duration(end-j.started)}</p>`:''}${p.retry_at&&j.status==='running'?`<p>自动重试倒计时：${duration(p.retry_at-Date.now()/1000)}</p>`:''}${p.activity.length?`<ul class="activity">${p.activity.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>`:''}${p.last_event&&j.status==='running'?`<p>最近日志更新：${duration(Date.now()/1000-p.last_event)}前；长时间无更新不一定表示卡住。</p>`:''}${j.status==='running'?'<small>按实际阶段显示，Agent 未提供完成百分比。</small>':''}</div>`;}
function jobCard(j){return `<div class="job"><div class="job-head"><strong>${j.kind==='research'?'会议调查':`Reviewer ${j.reviewer+1}`}</strong>${badge(j.status)}</div><p>${j.kind==='research'?'检索会议来源 · 配置投稿表单':esc(j.persona?.name||(j.status==='queued'?'审稿视角将在启动时抽取':'旧版审稿视角'))}</p>${j.persona?`<details data-panel="reviewer:${esc(j.id)}"><summary>模拟 reviewer 档案</summary><p>${esc(j.persona.background)}</p>${j.persona.public_background?`<p>公开背景参考：${esc(j.persona.public_background.name)} · ${esc(j.persona.public_background.edition)}（仅借鉴研究方向，不代表本人意见）</p><p>${esc(j.persona.public_background.research_areas.join(' / '))}</p>${j.persona.public_background.source_urls.map(u=>`<a href="${safeLink(u)}" target="_blank" rel="noopener">背景来源 ↗</a> `).join('')}`:''}<p>${esc(j.persona.lens)}</p><p>${esc(j.persona.tradeoff)}</p><p>${esc(j.persona.calibration)}</p></details>`:''}<p>${j.started?'开始于 '+date(j.started):'等待可用 worker'}</p>${progressCard(j)}${j.error?`<p class="failure">${esc(j.error)}</p>`:''}${j.status==='failed'?`<button data-retry="${j.id}">重试任务</button>`:''}</div>`;}
function conferenceProgress(c){const active=data.jobs.filter(j=>j.cid===c.id&&['running','queued'].includes(j.status));return active.length?`<div class="hint">${active.length} 个任务进行中 · ${esc(active.find(j=>j.status==='running')?.progress?.label||'排队等待')}</div>`:'';}
const reviewSummaries=new Map();
const excerpt=(s,n=260)=>{s=String(s||'');return esc(s.length>n?s.slice(0,n)+'…':s);};
async function loadReviewSummaries(){
 const cid=new URLSearchParams(location.search).get('conference');
 await Promise.all(data.runs.filter(r=>r.cid===cid).map(async r=>{
  const jobs=data.jobs.filter(j=>j.run_id===r.id);
  const signature=JSON.stringify(jobs.map(j=>[j.id,j.status,j.finished]));
  if(!jobs.some(j=>j.status==='done')||reviewSummaries.get(r.id)?.signature===signature)return;
  try{const exported=await api('/api/runs/'+r.id+'/export');reviewSummaries.set(r.id,{signature,reviews:exported.reviews});}
  catch(e){reviewSummaries.set(r.id,{error:e.message});}
 }));
}
function reviewSummary(run,jobs,profile){
 const completed=jobs.filter(j=>j.status==='done').length;
 if(!completed)return '';
 const cached=reviewSummaries.get(run.id);
 if(!cached||cached.error)return `<div class="review-summary"><h3>审稿摘要</h3><p>${cached?.error?'摘要暂时加载失败，下次刷新将重试。':'正在加载审稿摘要…'}</p></div>`;
 const reviews=cached.reviews.filter(j=>j.status==='done'&&j.result).sort((a,b)=>a.reviewer-b.reviewer);
 if(!reviews.length)return '';
 const scores=reviews.map(j=>j.result.score),mean=scores.reduce((a,b)=>a+b,0)/scores.length;
 const labels=profile?.score_labels||[];
 return `<section class="review-summary"><h3>得分摘要</h3><p class="muted">已完成 ${reviews.length} / ${jobs.length} 位 reviewer${reviews.length<jobs.length?' · 以下为部分结果，其余任务完成后自动更新':''}。${run.status==='superseded'?'此摘要属于该历史投稿版本。':''}</p><div class="score-overview"><strong>平均分 ${mean.toFixed(2)} / ${labels.length||'—'}</strong><span>范围 ${Math.min(...scores)}–${Math.max(...scores)}</span><span>均分仅作数值汇总，不代表录用决定。</span></div><p class="reviewer-scores">${reviews.map(j=>`<span>R${j.reviewer+1}：<strong>${j.result.score}</strong>（${esc(labels[j.result.score-1]||'')}）</span>`).join('')}</p><h3>审稿意见摘要</h3><p class="muted">仅展示各 reviewer 的最终判断与理由，其他细节可展开查看。</p><div class="opinion-grid">${reviews.map(j=>`<article class="opinion"><h4>Reviewer ${j.reviewer+1} · ${esc(labels[j.result.score-1]||String(j.result.score))}</h4><p class="pre">${esc(j.result.recommendation)}</p><details data-panel="review-full:${esc(run.id)}:${j.reviewer}"><summary>展开完整意见</summary><p class="pre">${esc(j.result.recommendation)}</p><p class="pre">${esc(j.result.summary)}</p>${['strengths','weaknesses','questions','evidence'].map((k,i)=>`<strong>${['优点','问题','提问','论文证据'][i]}</strong><ul>${(j.result[k]||[]).map(v=>`<li>${esc(v)}</li>`).join('')}</ul>`).join('')}<p class="pre">${esc(j.result.limitations)}</p></details></article>`).join('')}</div></section>`;
}
function deleteButton(c){return `<button class="danger" data-delete="${c.id}" ${c.status==='deleting'?'disabled':''}>${c.status==='delete_failed'?'重试删除':'删除会议'}</button>`;}
function rubric(p){return `<h3>评分维度与依据</h3>${(p.dimensions||[]).map(d=>`<details data-panel="dimension:${esc(d.name)}"><summary>${esc(d.name)} · ${esc({official:'本届公开量表',historical:'历史量表',simulated:'模拟补充'}[d.basis])}</summary><p>${esc(d.description)}</p><ol>${d.labels.map(l=>`<li>${esc(l)}</li>`).join('')}</ol><p>${esc(d.editions.join(' / '))}：${esc(d.rationale)}</p>${d.source_urls.map(u=>`<p><a href="${safeLink(u)}" target="_blank" rel="noopener">${esc(u)}</a></p>`).join('')}</details>`).join('')}<h3>最近几届量表对比</h3>${(p.edition_comparison||[]).map(e=>`<details data-panel="edition:${esc(e.edition)}"><summary>${esc(e.edition)}</summary><p>${esc(e.findings)}</p><p class="muted">${esc(e.gaps)}</p>${e.source_urls.map(u=>`<p><a href="${safeLink(u)}" target="_blank" rel="noopener">${esc(u)}</a></p>`).join('')}</details>`).join('')}`;}
function render(){
 const panels=new Map([...document.querySelectorAll('details[data-panel]')].map(el=>[el.dataset.panel,el.open]));
 renderContent();
 document.querySelectorAll('details[data-panel]').forEach(el=>{if(panels.has(el.dataset.panel))el.open=panels.get(el.dataset.panel);});
}
function renderContent(){
 $('#count').textContent=data.conferences.length;
 $('#total').textContent=`${data.conferences.length} conferences`;
 $('#connection').textContent=data.codex_available?'● Codex CLI 可用 · '+data.model:'Codex CLI 未找到';
 const id=new URLSearchParams(location.search).get('conference');
 const c=data.conferences.find(x=>x.id===id);
 $('#home').hidden=!!c;$('#detail').hidden=!c;
 if(!c){$('#conferences').innerHTML=data.conferences.length?`<table><thead><tr><th>Conference</th><th>Status</th><th>Reviewers</th><th>Created</th><th></th></tr></thead><tbody>${data.conferences.map(c=>`<tr><td><a class="conf-name" href="/?conference=${c.id}">${esc(c.name)}</a><div class="hint">${esc(c.profile?.summary?.slice(0,80)||'会议规则将由 Codex 调查生成')}</div></td><td>${badge(c.status)}${conferenceProgress(c)}</td><td>${c.count} agents</td><td class="hint">${date(c.created)}</td><td><a href="/?conference=${c.id}">打开 →</a> ${deleteButton(c)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">还没有会议。创建目标会议，开始第一次模拟投稿。</div>';return;}
 const jobs=data.jobs.filter(j=>j.cid===c.id),runs=data.runs.filter(r=>r.cid===c.id),p=c.profile;
 $('#detail').innerHTML=`<a class="back" href="/">← 所有会议</a><div class="page-heading"><div><div class="eyebrow">LOCAL CONFERENCE</div><h1>${esc(c.name)}</h1>${badge(c.status)} <span class="muted">${c.count} independent reviewers · ${esc(c.language)}</span></div><div class="actions">${deleteButton(c)}${c.status==='ready'?`<a class="button primary" href="/c/${c.id}/signin">进入 HotCRP →</a><a class="button" href="/c/${c.id}/paper/new">上传论文</a>`:''}</div></div>${c.error?`<div class="notice">${esc(c.error)}</div>`:''}<section class="panel"><h2>会议调查与配置</h2><div class="panel-body jobs">${jobs.filter(j=>j.kind==='research').map(jobCard).join('')}</div></section>
 ${p?`<div class="detail-grid"><section class="panel"><h2>投稿规则 <small>Conference profile</small></h2><div class="panel-body"><p>${esc(p.summary)}</p><dl class="kv"><dt>匿名方式</dt><dd>${esc(p.anonymity)}</dd><dt>篇幅要求</dt><dd>${esc(p.page_limit)}</dd><dt>真实截止日期</dt><dd>${esc(p.deadline_reference)}</dd><dt>本地投稿窗口</dt><dd>开放中，不受真实日期限制</dd><dt>审稿量表</dt><dd>${p.score_labels.map((v,i)=>`${i+1}. ${esc(v)}`).join('<br>')}</dd></dl><div class="notice">${esc(p.rubric_status)}</div>${p.dimensions?.length?rubric(p):''}<details data-panel="submission-guidance"><summary>完整投稿说明与评审标准</summary><p class="pre">${esc(p.submission_instructions)}</p><p class="pre">${esc(p.review_guidance)}</p></details><div>${p.topics.map(t=>`<span class="topic">${esc(t)}</span>`).join('')}</div></div></section><section class="panel"><h2>信息来源与待核实项</h2><div class="panel-body"><ul class="sources">${p.sources.map(s=>`<li><a href="${safeLink(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)} ↗</a><p>${esc(s.supports)}</p></li>`).join('')}</ul>${p.uncertainties.length?`<div class="notice">${p.uncertainties.map(esc).join('<br>')}</div>`:''}</div></section></div>`:''}
 <section class="panel"><h2>论文与模拟审稿 <small>${runs.length} submission versions</small></h2><div class="panel-body">${runs.length?runs.map(r=>`<div class="run-heading"><div><h3><a href="/c/${c.id}/paper/${r.pid}?m=main">#${r.pid} ${esc(r.title)}</a></h3>${badge(r.status)} <span class="version">snapshot ${r.fingerprint.slice(0,16)}</span></div><div class="actions"><a href="/api/runs/${r.id}/export">导出 JSON</a><a class="button" href="/c/${c.id}/paper/${r.pid}?m=main">查看原生 reviews →</a></div></div>${r.status==='superseded'?'<div class="notice">这是历史投稿版本。下方导出保留旧结果；HotCRP 页面显示各 reviewer 最近写入的结果，请核对 review 内的 snapshot 标记。</div>':''}<div class="jobs">${jobs.filter(j=>j.run_id===r.id).map(jobCard).join('')}</div>${reviewSummary(r,jobs.filter(j=>j.run_id===r.id),p)}<hr style="border:0;border-top:1px solid #e2e8ec;margin:24px 0">`).join(''):'<div class="empty">在 HotCRP 中上传论文并勾选“Ready for review”提交后，审稿任务会自动出现在这里。<br>草稿不会启动审稿。</div>'}</div></section>`;
}
$('#create').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;$('#create-button').disabled=true;$('#error').hidden=true;try{const f=new FormData(e.target);const c=await api('/api/conferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.get('name'),reviewers:Number(f.get('reviewers')),language:f.get('language')})});location.href='/?conference='+c.id;}catch(e){fail(e);}finally{busy=false;$('#create-button').disabled=false;}});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-retry]');if(!b)return;b.disabled=true;try{await api('/api/jobs/'+b.dataset.retry+'/retry',{method:'POST'});await refresh();}catch(e){fail(e);b.disabled=false;}});
async function refresh(){if(refreshing)return;refreshing=true;try{data=await api('/api/state');await loadReviewSummaries();const serialized=JSON.stringify([data,[...reviewSummaries]]);if(serialized!==lastState||data.jobs.some(j=>j.status==='running')){lastState=serialized;render();}}catch(e){$('#connection').textContent='服务连接中断';fail(e);}finally{refreshing=false;}}
refresh();setInterval(refresh,4000);

document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-delete]');if(!b)return;
 const c=data.conferences.find(c=>c.id===b.dataset.delete);if(!c)return;
 if(!confirm(`永久删除会议“${c.name}”？\n将停止该会议正在运行的 agent，并删除全部投稿、审稿、任务记录及文件。此操作无法恢复。`))return;
 b.disabled=true;$('#error').hidden=true;
 try{await api('/api/conferences/'+c.id,{method:'DELETE'});if(new URLSearchParams(location.search).get('conference')===c.id)history.replaceState(null,'','/');lastState='';await refresh();}
 catch(e){fail(e);b.disabled=false;}
});
