const $ = id => document.getElementById(id);
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token = document.querySelector('meta[name="local-token"]').content;
const streamNames = {teacher:'教师画面', ppt:'PPT画面', student:'学生画面'};
const statuses = {queued:'等待下载', resolving:'获取播放地址', downloading:'下载中', processing:'合并视频', done:'已完成', failed:'失败', cancelled:'已取消'};
const running = ['queued','resolving','downloading','processing'];
let state = {courses:[], jobs:[], auth:{}, library:[], replays:{}}, active = null, replays = [], selected = new Set(), courseSelection = new Set();
let replayVersion = 0, refreshing = false, loginPending = false, queueBusy = false, lastSignature = '', polling = false;
const streams = () => [...document.querySelectorAll('input[name=stream]:checked')].map(i=>i.value);
const bytes = value => value >= 1073741824 ? `${(value/1073741824).toFixed(2)} GB` : `${(value/1048576).toFixed(1)} MB`;
function notice(message, error = false) { $('notice').hidden = false; $('notice').textContent = message; $('notice').className = 'notice' + (error ? ' error' : ''); }
async function api(path, body = {}) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-Local-Token':token}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
}
async function busy(button, fn) {
  button.disabled = true;
  try { await fn(); } catch (e) { notice(e.message, true); }
  finally { button.disabled = false; updateSelection(); }
}
function filteredCourses() {
  const q = $('search').value.trim().toLocaleLowerCase(), term = $('term').value;
  return state.courses.filter(c => (!term || c.term === term) && (!$('only-tracked').checked || c.tracked) && (!q || `${c.title} ${c.teacher}`.toLocaleLowerCase().includes(q)));
}
function renderCourses() {
  const courses = filteredCourses(), term = $('term').value;
  const terms = [...new Set(state.courses.map(c=>c.term).filter(Boolean))].sort().reverse();
  $('term').innerHTML = '<option value="">全部学期</option>' + terms.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join(''); $('term').value = terms.includes(term) ? term : '';
  $('course-count').textContent = state.courses.length; $('visible-count').textContent = `${courses.length} 门`;
  $('course-list').innerHTML = courses.length ? courses.map(c=>`<div class="course-row ${active?.id===c.id?'active':''}"><input type="checkbox" data-course="${esc(c.id)}" aria-label="选择课程 ${esc(c.title)}" ${courseSelection.has(c.id)?'checked':''}><button data-open="${esc(c.id)}" ${active?.id===c.id?'aria-current="true"':''}><strong>${esc(c.title)} ${c.tracked?'<span class="follow-badge">跟踪</span>':''}</strong><small>${esc(c.teacher)} · ${esc(c.term || '未标记学期')}</small><small>${c.checked?`已保存 ${c.downloaded_count} / ${c.ready_count} 节 · 待补齐 ${c.pending_count} 节`:`${c.lesson_count || 0} 个课时 · 尚未检查`}${c.new_count?` · <b class="new-text">${c.new_count} 节新回放</b>`:''}</small></button></div>`).join('') : `<div class="empty">${state.courses.length?'没有匹配的课程':'完成统一认证后，点击“拉取课程”。'}</div>`;
  const checked = courses.filter(c=>courseSelection.has(c.id)).length;
  $('all-courses').checked = !!courses.length && checked===courses.length; $('all-courses').indeterminate = checked>0 && checked<courses.length; $('all-courses').disabled = !courses.length;
  const tracked = state.courses.filter(c=>c.tracked);
  $('tracked-total').textContent = tracked.length; $('saved-total').textContent = state.library.filter(f=>f.exists).length;
  $('pending-total').textContent = tracked.reduce((s,c)=>s+c.pending_count,0); $('new-total').textContent = tracked.reduce((s,c)=>s+c.new_count,0);
  updateSelection();
}
function missing(row) { return row.ready && streams().some(k=>!row.downloaded?.includes(k) && !running.includes(row.tasks?.[k])); }
function updateSelection() {
  selected = new Set([...selected].filter(id=>replays.some(r=>r.id===id && missing(r))));
  const available = replays.filter(missing);
  $('download').disabled = !selected.size || queueBusy; $('download').textContent = selected.size?`下载所选回放 (${selected.size})`:'下载所选回放';
  $('fill').disabled = !active || !available.length || queueBusy; $('bulk').disabled = !courseSelection.size || queueBusy;
  $('bulk').textContent = courseSelection.size?`下载所选课程 (${courseSelection.size})`:'下载所选课程';
  $('all-replays').disabled = !available.length; $('all-replays').checked = !!available.length && selected.size===available.length; $('all-replays').indeterminate = selected.size>0 && selected.size<available.length;
}
function openButton(f) { return `<button class="video-open" data-video="${esc(JSON.stringify([f.course_id,f.sub_id,f.stream]))}" title="${esc(f.path)}">▶ ${esc(streamNames[f.stream])}</button>`; }
function renderFollow() {
  $('follow-controls').hidden = !active;
  if (!active) return;
  const c = state.courses.find(c=>c.id===active.id) || active;
  $('follow').checked = !!c.tracked; $('auto-download').checked = !!c.auto_download; $('auto-download').disabled = !c.tracked;
  $('save-follow').disabled = !c.tracked;
  $('follow-streams').textContent = c.tracked?'跟踪画面：'+(c.streams || ['teacher']).map(k=>streamNames[k]).join('、'):'自动下载默认关闭';
}
function renderReplays() {
  if (!active) return;
  updateSelection();
  $('replay-count').textContent = `${replays.length} 个课时 · ${replays.filter(r=>r.ready).length} 节已有回放 · ${replays.filter(r=>r.downloaded?.length).length} 节已保存`;
  $('replays').innerHTML = replays.length ? replays.map(r=>{
    const tasks = Object.entries(r.tasks || {}).filter(([k,v])=>running.includes(v));
    const saved = r.files || [];
    return `<tr><td class="check-col"><input type="checkbox" data-replay="${esc(r.id)}" aria-label="选择回放 ${esc(r.title)}" ${missing(r)?'':'disabled'} ${selected.has(r.id)?'checked':''}></td><td><span class="sub-title">${esc(r.title)}</span>${r.is_new?'<span class="new-text">新回放</span>':''}</td><td>${esc(r.teacher || '—')}</td><td><span class="tag ${r.ready?'':'warn'}">${r.ready?(saved.length?'已保存':'待下载'):esc(r.status)}</span>${saved.map(openButton).join('')}${tasks.map(([k,v])=>`<small class="replay-task">${streamNames[k]} · ${statuses[v]}</small>`).join('')}</td></tr>`;
  }).join('') : '<tr><td colspan="4"><div class="empty tall">这门课程暂无课时或回放。</div></td></tr>';
  renderFollow();
}
async function openCourse(id) {
  const version = ++replayVersion;
  active = state.courses.find(c=>c.id===id); if (!active) return;
  replays = state.replays[id] || []; selected.clear();
  $('course-title').textContent = active.title; $('course-meta').textContent = `${active.term || ''} / ${active.teacher || ''}`;
  renderCourses(); renderReplays(); $('replay-count').textContent += ' · 正在检查更新…';
  try {
    const data = await api('/api/replays',{course_id:id}); if (version!==replayVersion) return;
    replays = data.replays; state.replays[id]=replays; renderReplays();
    if (data.cached) notice('当前显示上次保存的课程目录。完成登录后可检查最新回放。');
    await poll();
  } catch(e) { if (version===replayVersion) { $('replay-count').textContent = '获取失败，重新选择课程可重试'; notice(e.message,true); } }
}
async function refreshCourses() {
  if (refreshing) return; refreshing=true;
  await busy($('refresh'),async()=>{
    notice('正在拉取个人课程…'); await api('/api/courses'); await poll();
    courseSelection = new Set([...courseSelection].filter(id=>state.courses.some(c=>c.id===id))); renderCourses();
    notice(`已拉取 ${state.courses.length} 门课程。`);
    if (active) await openCourse(active.id);
  }); refreshing=false;
}
function showView(view) {
  for (const key of ['courses','library','jobs']) { $(key+'-view').hidden=key!==view; if(key===view) $(key+'-tab').setAttribute('aria-current','page'); else $(key+'-tab').removeAttribute('aria-current'); }
}
function renderLibrary() {
  const q=$('library-search').value.trim().toLocaleLowerCase();
  const rows=state.library.filter(f=>!q || `${f.course} ${f.title}`.toLocaleLowerCase().includes(q)).sort((a,b)=>(b.saved_at||0)-(a.saved_at||0));
  $('library-count').textContent=state.library.filter(f=>f.exists).length;
  $('library').innerHTML=rows.length?rows.map(f=>`<tr><td><strong>${esc(f.course)}</strong><small class="replay-task">${esc(f.title)}</small></td><td>${streamNames[f.stream]}</td><td>${f.exists?bytes(f.bytes||0):'<span class="tag warn">文件已缺失</span>'}</td><td>${f.exists?openButton(f):'可在课程中重新下载'}</td></tr>`).join(''):'<tr><td colspan="4"><div class="empty tall">尚无本地视频。已有旧版下载文件时，选择原视频目录后点击扫描。</div></td></tr>';
}
function renderJobs() {
  const jobs=state.jobs;
  $('job-count').textContent=jobs.length; $('queue-summary').textContent=`${jobs.filter(j=>running.includes(j.status)).length} 个待完成 · ${jobs.filter(j=>j.status==='done').length} 个已完成 · ${jobs.filter(j=>j.status==='failed').length} 个失败`;
  $('jobs').innerHTML=jobs.length?[...jobs].reverse().map(j=>`<article class="job"><div><strong>${esc(j.course)}</strong><small>${esc(j.title)} · ${streamNames[j.stream]}</small>${j.error?`<small class="job-error">${esc(j.error)}</small>`:''}</div><div><div class="job-state"><span>${statuses[j.status]}</span><span>${j.progress==null?'大小未知':Math.round(j.progress)+'%'}</span></div><div class="progress" role="progressbar" aria-label="${esc(j.title)}下载进度" ${j.progress==null?'':'aria-valuenow="'+Math.round(j.progress)+'"'} aria-valuemin="0" aria-valuemax="100"><span style="width:${j.progress==null?3:j.progress}%"></span></div><small>${bytes(j.bytes||0)}${j.speed?' · '+bytes(j.speed)+'/s':''}${j.eta?' · 剩余 '+Math.ceil(j.eta/60)+' 分钟':''}</small></div><div>${running.includes(j.status)?`<button data-cancel="${esc(j.id)}">取消</button>`:['failed','cancelled'].includes(j.status)?`<button data-retry="${esc(j.id)}">重试</button>`:'<span class="tag">已完成</span>'}</div></article>`).join(''):'<div class="empty tall"><span class="empty-icon">↓</span><p>下载队列为空</p><small>在课程中勾选回放，或使用“补齐缺失回放”。</small></div>';
}
async function enqueue(items) {
  if(!streams().length) throw new Error('请至少选择一种下载画面'); if(!items.length) throw new Error('所选课程暂无缺失的可下载回放');
  const result=await api('/api/queue',{items,streams:streams()});
  notice(result.added?`已加入 ${result.added} 个视频任务，已有文件自动跳过。`:'这些回放已在队列中或已保存。');
  selected.clear(); showView('jobs'); await poll();
}
async function downloadItems(items) {
  queueBusy=true; updateSelection();
  try {await enqueue(items);} catch(e){notice(e.message,true);} finally{queueBusy=false;updateSelection();}
}
async function saveFollow(applyStreams=false) {
  if(!active) return;
  const course=state.courses.find(c=>c.id===active.id);
  try {
    await api('/api/track',{course_id:active.id,tracked:$('follow').checked,auto_download:$('auto-download').checked,streams:applyStreams || !course.tracked?streams():course.streams});
    await poll(); renderFollow();
    notice($('follow').checked?($('auto-download').checked?'已启用自动下载：每次检查将补齐所选跟踪画面的所有缺失回放。':'已跟踪课程，新回放出现后可手动补齐下载。'):'已取消跟踪。');
  } catch(e){notice(e.message,true);renderFollow();}
}
async function checkAuth() {
  state.auth=await api('/api/auth/check'); renderAuth();
  if(state.auth.logged_in){loginPending=false;if(!state.courses.length) await refreshCourses();}
  else notice(state.auth.message || '请在认证窗口完成登录，再点击“检查登录”。');
}
function renderAuth(){
  $('auth-status').textContent=state.auth.logged_in?`${state.auth.name || ''} · 已登录`:'未登录'; $('auth-status').className='tag'+(state.auth.logged_in?'':' warn');
  $('login').textContent=state.auth.logged_in?'重新认证 ↗':'统一认证登录 ↗';
}
async function poll() {
  if(polling) return; polling=true;
  try {
    const response=await fetch('/api/state');if(!response.ok)throw new Error();const data=await response.json();state=data;
    if(document.activeElement!==$('outdir'))$('outdir').value=data.outdir; $('choose-dir').hidden=!data.desktop; $('parallel').textContent=`${data.concurrency} 个并行任务`;
    if(document.activeElement!==$('interval'))$('interval').value=data.check_minutes;
    $('sync-status').textContent=data.sync.message || (data.sync.last_check?'上次检查 '+new Date(data.sync.last_check*1000).toLocaleString():'软件运行时检查；请先跟踪课程'); $('sync').disabled=data.sync.running;
    renderAuth();
    const signature=JSON.stringify([data.courses,data.jobs,data.library,data.replays]);
    if(signature!==lastSignature){lastSignature=signature; if(active){active=state.courses.find(c=>c.id===active.id)||active;replays=data.replays[active.id]||replays;} renderCourses();renderLibrary();renderJobs();renderReplays();}
    if(!data.ffmpeg)notice('未检测到 FFmpeg，请安装后重新启动。',true);
    $('footer-status').textContent='本地资料库已连接';
  } catch(e){$('footer-status').textContent='本地服务未连接，请重新启动软件';} finally{polling=false;}
}
$('login').onclick=()=>busy($('login'),async()=>{const data=await api('/api/auth/login');notice(data.message);loginPending=true;});
$('check-auth').onclick=()=>busy($('check-auth'),checkAuth); $('refresh').onclick=refreshCourses;
$('open-folder').onclick=()=>busy($('open-folder'),()=>api('/api/open-folder'));
$('choose-dir').onclick=()=>busy($('choose-dir'),async()=>{const data=await api('/api/choose-folder');if(data.outdir){await api('/api/settings',{outdir:data.outdir});await poll();notice('视频目录已更新，原视频仍保留在原位置。');}});
$('save-dir').onclick=()=>busy($('save-dir'),async()=>{await api('/api/settings',{outdir:$('outdir').value});await poll();notice('视频目录已更新。');});
$('sync').onclick=()=>busy($('sync'),async()=>{const data=await api('/api/sync');notice(data.message);await poll();});
$('interval').onchange=async()=>{try{await api('/api/sync-settings',{check_minutes:Number($('interval').value)});notice('自动检查间隔已保存；仅在软件运行时执行。');}catch(e){notice(e.message,true);await poll();}};
$('scan').onclick=()=>busy($('scan'),async()=>{const data=await api('/api/scan');await poll();notice(`扫描完成，找到 ${data.count} 个本地视频。`);});
$('follow').onchange=()=>saveFollow(true);$('auto-download').onchange=()=>saveFollow();$('save-follow').onclick=()=>busy($('save-follow'),()=>saveFollow(true));
$('search').oninput=renderCourses;$('term').onchange=renderCourses;$('only-tracked').onchange=renderCourses;$('library-search').oninput=renderLibrary;
for(const key of ['courses','library','jobs'])$(key+'-tab').onclick=()=>showView(key);
for(const input of document.querySelectorAll('input[name=stream]'))input.onchange=renderReplays;
$('course-list').onclick=event=>{const button=event.target.closest('button[data-open]');if(button)openCourse(button.dataset.open);};
$('course-list').onchange=event=>{const id=event.target.dataset.course;if(id){event.target.checked?courseSelection.add(id):courseSelection.delete(id);renderCourses();}};
$('all-courses').onchange=event=>{for(const c of filteredCourses())event.target.checked?courseSelection.add(c.id):courseSelection.delete(c.id);renderCourses();};
$('replays').onchange=event=>{const id=event.target.dataset.replay;if(id){event.target.checked?selected.add(id):selected.delete(id);updateSelection();}};
$('all-replays').onchange=event=>{selected=new Set(event.target.checked?replays.filter(missing).map(r=>r.id):[]);renderReplays();};
$('download').onclick=()=>downloadItems([...selected].map(id=>({course_id:active.id,sub_id:id})));
$('fill').onclick=()=>downloadItems(replays.filter(missing).map(r=>({course_id:active.id,sub_id:r.id})));
$('bulk').onclick=async()=>{
  queueBusy=true;updateSelection();
  try{const items=[];const courses=[...courseSelection];for(let i=0;i<courses.length;i++){notice(`正在获取所选课程的回放… ${i+1}/${courses.length}`);const data=await api('/api/replays',{course_id:courses[i]});items.push(...data.replays.filter(missing).map(r=>({course_id:courses[i],sub_id:r.id})));}await enqueue(items);}catch(e){notice(e.message,true);}finally{queueBusy=false;updateSelection();}
};
$('jobs').onclick=event=>{const button=event.target.closest('button');if(!button)return;const id=button.dataset.retry||button.dataset.cancel;busy(button,async()=>{await api(button.dataset.retry?'/api/retry':'/api/cancel',{id});await poll();});};
document.addEventListener('click',event=>{const button=event.target.closest('button[data-video]');if(!button)return;const [course_id,sub_id,stream]=JSON.parse(button.dataset.video);busy(button,()=>api('/api/open-video',{course_id,sub_id,stream}));});
(async()=>{await poll();try{await checkAuth();}catch(e){notice(e.message,true);}setInterval(poll,1500);setInterval(()=>{if(loginPending)checkAuth().catch(e=>notice(e.message,true));},4000);})();
