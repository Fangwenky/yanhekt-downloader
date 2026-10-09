const $ = id => document.getElementById(id);
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token = document.querySelector('meta[name="local-token"]').content;
let state = {courses: [], jobs: [], auth: {}}, active = null, replays = [], selected = new Set(), courseSelection = new Set();
let replayVersion = 0, refreshing = false, loginPending = false, queueBusy = false, lastJobs = '';
const streamNames = {teacher:'教师画面', ppt:'PPT画面', student:'学生画面'};
const statuses = {queued:'等待下载', resolving:'获取播放地址', downloading:'下载中', processing:'合并视频', done:'已完成', failed:'失败', cancelled:'已取消'};
const activeStatuses = ['queued','resolving','downloading','processing'];
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
  const query = $('search').value.trim().toLocaleLowerCase(), term = $('term').value;
  return state.courses.filter(c => (!term || c.term === term) && (!query || `${c.title} ${c.teacher}`.toLocaleLowerCase().includes(query)));
}
function renderCourses() {
  const courses = filteredCourses();
  $('course-count').textContent = state.courses.length;
  $('visible-count').textContent = `${courses.length} 门`;
  $('course-list').innerHTML = courses.length ? courses.map(c => `<div class="course-row ${active?.id === c.id ? 'active' : ''}"><input type="checkbox" data-course="${escapeHTML(c.id)}" aria-label="选择课程 ${escapeHTML(c.title)}" ${courseSelection.has(c.id)?'checked':''}><button data-open="${escapeHTML(c.id)}" ${active?.id===c.id?'aria-current="true"':''}><strong>${escapeHTML(c.title)}</strong><small>${escapeHTML(c.teacher)} · ${escapeHTML(c.term || '未标记学期')}</small><small>${c.lesson_count} 个课时 · ${escapeHTML(c.department)}</small></button></div>`).join('') : `<div class="empty">${state.courses.length?'没有匹配的课程':'完成统一认证后，点击“拉取课程”。'}</div>`;
  const checked = courses.filter(c => courseSelection.has(c.id)).length;
  $('all-courses').checked = courses.length > 0 && checked === courses.length;
  $('all-courses').indeterminate = checked > 0 && checked < courses.length;
  $('all-courses').disabled = !courses.length;
  updateSelection();
}
function updateSelection() {
  $('download').disabled = !selected.size || queueBusy;
  $('download').textContent = selected.size ? `下载所选回放 (${selected.size})` : '下载所选回放';
  $('bulk').disabled = !courseSelection.size || queueBusy;
  $('bulk').textContent = courseSelection.size ? `下载所选课程 (${courseSelection.size})` : '下载所选课程';
  const available = replays.filter(r => r.ready);
  $('all-replays').disabled = !available.length;
  $('all-replays').checked = available.length > 0 && selected.size === available.length;
  $('all-replays').indeterminate = selected.size > 0 && selected.size < available.length;
}
function renderReplays() {
  const ready = replays.filter(r => r.ready).length;
  $('replay-count').textContent = `${replays.length} 个课时 · ${ready} 节已有回放`;
  $('replays').innerHTML = replays.length ? replays.map(r => `<tr><td class="check-col"><input type="checkbox" data-replay="${escapeHTML(r.id)}" aria-label="选择回放 ${escapeHTML(r.title)}" ${r.ready?'':'disabled'} ${selected.has(r.id)?'checked':''}></td><td><span class="sub-title">${escapeHTML(r.title)}</span></td><td>${escapeHTML(r.teacher || '—')}</td><td><span class="tag ${r.ready?'':'warn'}">${escapeHTML(r.status)}</span></td></tr>`).join('') : '<tr><td colspan="4"><div class="empty tall">这门课程暂无课时或回放。</div></td></tr>';
  updateSelection();
}
async function openCourse(id) {
  const version = ++replayVersion;
  active = state.courses.find(c => c.id === id); replays = []; selected.clear();
  $('course-title').textContent = active.title;
  $('course-meta').textContent = `${active.term} / ${active.teacher}`;
  $('replay-count').textContent = '正在获取回放…';
  $('replays').innerHTML = '<tr><td colspan="4"><div class="empty tall" role="status">正在读取课程目录…</div></td></tr>';
  renderCourses();
  try {
    const data = await api('/api/replays', {course_id:id});
    if (version !== replayVersion) return;
    replays = data.replays; renderReplays();
  } catch (e) {
    if (version !== replayVersion) return;
    $('replay-count').textContent = '获取失败，重新选择课程可重试';
    $('replays').innerHTML = '<tr><td colspan="4"><div class="empty tall">回放加载失败。</div></td></tr>';
    notice(e.message, true);
  }
}
async function refreshCourses() {
  if (refreshing) return;
  refreshing = true;
  await busy($('refresh'), async () => {
    $('footer-status').textContent = '正在拉取所有课程…';
    const data = await api('/api/courses'); state.courses = data.courses;
    courseSelection = new Set([...courseSelection].filter(id => state.courses.some(c => c.id === id)));
    const terms = [...new Set(state.courses.map(c => c.term).filter(Boolean))].sort().reverse();
    $('term').innerHTML = '<option value="">全部学期</option>' + terms.map(t => `<option>${escapeHTML(t)}</option>`).join('');
    renderCourses(); notice(`已拉取 ${state.courses.length} 门课程。选择课程可查看已有回放。`);
    if (active) await openCourse(active.id);
  });
  refreshing = false; $('footer-status').textContent = '准备就绪';
}
function showView(view) {
  $('courses-view').hidden = view !== 'courses'; $('jobs-view').hidden = view !== 'jobs';
  for (const key of ['courses','jobs']) {
    if (key === view) $(key+'-tab').setAttribute('aria-current','page'); else $(key+'-tab').removeAttribute('aria-current');
  }
}
const bytes = value => value >= 1073741824 ? `${(value/1073741824).toFixed(2)} GB` : `${(value/1048576).toFixed(1)} MB`;
function renderJobs() {
  const jobs = state.jobs, running = jobs.filter(j => activeStatuses.includes(j.status)).length;
  $('job-count').textContent = jobs.length;
  $('queue-summary').textContent = `${running} 个待完成 · ${jobs.filter(j=>j.status==='done').length} 个已完成 · ${jobs.filter(j=>j.status==='failed').length} 个失败`;
  $('jobs').innerHTML = jobs.length ? [...jobs].reverse().map(j => `<article class="job"><div><strong>${escapeHTML(j.course)}</strong><small>${escapeHTML(j.title)} · ${streamNames[j.stream]}</small>${j.error?`<small class="job-error">${escapeHTML(j.error)}</small>`:''}${j.status==='done'?`<small title="${escapeHTML(j.path)}">${escapeHTML(j.path)}</small>`:''}</div><div><div class="job-state"><span>${statuses[j.status]}</span><span>${j.progress == null?'大小未知':Math.round(j.progress)+'%'}</span></div><div class="progress" role="progressbar" aria-label="${escapeHTML(j.title)}下载进度" ${j.progress==null?'':'aria-valuenow="'+Math.round(j.progress)+'"'} aria-valuemin="0" aria-valuemax="100"><span style="width:${j.progress==null?3:j.progress}%"></span></div><small>${bytes(j.bytes || 0)}${j.speed?' · '+bytes(j.speed)+'/s':''}${j.eta?' · 剩余 '+Math.ceil(j.eta/60)+' 分钟':''}</small></div><div>${activeStatuses.includes(j.status)?`<button data-cancel="${j.id}">取消</button>`:['failed','cancelled'].includes(j.status)?`<button data-retry="${j.id}">重试</button>`:'<span class="tag">已保存</span>'}</div></article>`).join('') : '<div class="empty tall"><span class="empty-icon">↓</span><p>下载队列为空</p><small>在课程中勾选回放，添加第一批下载。</small></div>';
}
async function enqueue(items) {
  const streams = [...document.querySelectorAll('input[name=stream]:checked')].map(i=>i.value);
  if (!streams.length) throw new Error('请至少选择一种下载画面');
  if (!items.length) throw new Error('所选课程暂无可下载回放');
  const result = await api('/api/queue', {items, streams});
  notice(result.added ? `已加入 ${result.added} 个视频任务。每种画面单独保存，已完成及正在排队的任务会自动跳过。` : '这些回放已在队列中或已保存。');
  selected.clear(); renderReplays(); showView('jobs'); await poll();
}
async function checkAuth() {
  state.auth = await api('/api/auth/check'); renderAuth();
  if (state.auth.logged_in) { loginPending = false; if (!state.courses.length) await refreshCourses(); }
  else notice(state.auth.message || '请在认证窗口完成登录，再点击“检查登录”。');
}
function renderAuth() {
  $('auth-status').textContent = state.auth.logged_in ? `${state.auth.name} · 已登录` : '未登录';
  $('auth-status').className = 'tag' + (state.auth.logged_in?'':' warn');
  $('login').textContent = state.auth.logged_in ? '重新认证 ↗' : '统一认证登录 ↗';
}
async function poll() {
  try {
    const response = await fetch('/api/state'); if (!response.ok) throw new Error();
    const data = await response.json(); state.jobs = data.jobs; state.auth = data.auth;
    if (document.activeElement !== $('outdir')) $('outdir').value = data.outdir;
    $('parallel').textContent = `${data.concurrency} 个并行任务`; renderAuth();
    const signature = JSON.stringify(state.jobs); if (signature !== lastJobs) { renderJobs(); lastJobs = signature; }
    if (!data.ffmpeg) notice('未检测到 FFmpeg。请先安装后再下载（macOS：brew install ffmpeg）。', true);
    $('footer-status').textContent = '本地服务已连接';
  } catch (_) { $('footer-status').textContent = '本地服务未连接，请检查启动终端'; }
}
$('login').onclick = () => busy($('login'), async () => { const data = await api('/api/auth/login'); notice(data.message); loginPending = true; });
$('check-auth').onclick = () => busy($('check-auth'), checkAuth);
$('refresh').onclick = refreshCourses;
$('open-folder').onclick = () => busy($('open-folder'), () => api('/api/open-folder'));
$('save-dir').onclick = () => busy($('save-dir'), async () => { const data = await api('/api/settings', {outdir:$('outdir').value}); $('outdir').value = data.outdir; notice('保存目录已更新。'); });
$('search').oninput = renderCourses; $('term').onchange = renderCourses;
$('courses-tab').onclick = () => showView('courses'); $('jobs-tab').onclick = () => showView('jobs');
$('course-list').onclick = event => { const button = event.target.closest('button[data-open]'); if (button) openCourse(button.dataset.open); };
$('course-list').onchange = event => { const id = event.target.dataset.course; if (!id) return; event.target.checked?courseSelection.add(id):courseSelection.delete(id); renderCourses(); };
$('all-courses').onchange = event => { for (const c of filteredCourses()) event.target.checked?courseSelection.add(c.id):courseSelection.delete(c.id); renderCourses(); };
$('replays').onchange = event => { const id = event.target.dataset.replay; if (!id) return; event.target.checked?selected.add(id):selected.delete(id); updateSelection(); };
$('all-replays').onchange = event => { selected = new Set(event.target.checked?replays.filter(r=>r.ready).map(r=>r.id):[]); renderReplays(); };
$('download').onclick = async () => {
  const items = [...selected].map(id=>({course_id:active.id, sub_id:id})); queueBusy = true; updateSelection();
  try { await enqueue(items); } catch (e) { notice(e.message, true); } finally { queueBusy=false; updateSelection(); }
};
$('bulk').onclick = async () => {
  const courses = [...courseSelection]; queueBusy=true; updateSelection();
  try {
    const items=[];
    for (let i=0;i<courses.length;i++) {
      notice(`正在获取所选课程的全部回放… ${i+1}/${courses.length}`);
      const data=await api('/api/replays',{course_id:courses[i]});
      items.push(...data.replays.filter(r=>r.ready).map(r=>({course_id:courses[i], sub_id:r.id})));
    }
    await enqueue(items);
  } catch (e) { notice(e.message,true); } finally { queueBusy=false; updateSelection(); }
};
$('jobs').onclick = event => {
  const button=event.target.closest('button'); if (!button) return;
  const retry=button.dataset.retry;
  busy(button, async()=>{await api(retry?'/api/retry':'/api/cancel',{id:retry||button.dataset.cancel}); await poll();});
};
(async()=>{await poll(); renderJobs(); try {await checkAuth();} catch(e){notice(e.message,true);} setInterval(poll,1500); setInterval(()=>{if(loginPending) checkAuth().catch(e=>notice(e.message,true));},4000);})();
