(function () {
  const TOKEN = document.querySelector('meta[name="gup-token"]').content;
  const $ = id => document.getElementById(id);
  const CATS = { "1": "영화/애니메이션", "2": "자동차", "10": "음악", "15": "동물", "17": "스포츠", "19": "여행/이벤트", "20": "게임", "22": "인물/블로그", "23": "코미디", "24": "엔터테인먼트", "25": "뉴스/정치", "26": "노하우/스타일", "27": "교육", "28": "과학기술" };

  let state = null, job = null, result = null, pollTimer = null;
  let pick = { t: 'search', d: 'search', h: 'search' };
  let thumbId = null, applied = false, edited = false, autoOpened = false, appliedVideoId = null;

  // ---------- 공통 ----------
  async function api(path, opts = {}) {
    const init = { method: opts.method || 'GET', headers: { 'X-GUP-Token': TOKEN } };
    if (opts.form) { init.body = opts.form; init.method = 'POST'; }
    else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json'; init.method = opts.method || 'POST'; }
    let r;
    try { r = await fetch(path, init); } catch (e) { throw new Error('프로그램과 연결이 끊겼습니다. G-UPLOADER 창이 켜져 있는지 확인해 주세요.'); }
    const data = await r.json().catch(() => ({}));
    if (r.status === 403 && data.detail === 'forbidden') staleReload();
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다.');
    return data;
  }
  // 프로그램이 다시 켜지면 보안 열쇠가 바뀐다. 예전 화면이면 알아서 새로고침한다.
  let reloading = false;
  function staleReload() {
    if (reloading) return;
    reloading = true;
    toast('프로그램이 다시 켜져서 화면을 새로고침합니다');
    setTimeout(() => location.reload(), 1200);
    throw new Error('프로그램이 다시 켜져서 화면을 새로고침합니다');
  }
  function h(tag, attrs = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') el.className = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v);
    }
    for (const c of kids.flat()) if (c != null) el.append(c.nodeType ? c : String(c));
    return el;
  }
  let tt;
  function toast(msg, bad) {
    const el = $('toast'); el.textContent = msg; el.className = 'toast show' + (bad ? ' bad' : '');
    clearTimeout(tt); tt = setTimeout(() => el.className = 'toast', bad ? 5000 : 2800);
  }
  function setMsg(id, text, bad) { const el = $(id); el.textContent = text || ''; el.className = 'msg' + (bad ? ' bad' : ''); }
  function fmtDur(s) { s = Math.round(s); const hh = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = s % 60; return (hh ? hh + ':' + String(m).padStart(2, '0') : m) + ':' + String(r).padStart(2, '0'); }
  const bytes = s => new TextEncoder().encode(s).length;

  // ---------- 상태·설정 ----------
  async function loadState() {
    state = await api('/api/state');
    const ch = state.channel;
    $('chStatus').innerHTML = '';
    $('chStatus').append(h('span', { class: 'dot' + (ch ? ' on' : '') }), ch ? ch.title : '유튜브 미연결');
    $('okClaude').textContent = state.has_claude ? '설정됨' : '필요';
    $('okClaude').className = 'ok' + (state.has_claude ? ' yes' : '');
    $('okYt').textContent = ch ? '연결됨 · ' + ch.title : (state.has_google_client ? '파일 등록됨 · 연결 필요' : '필요');
    $('okYt').className = 'ok' + (ch ? ' yes' : '');
    $('disconnectBtn').style.display = ch ? '' : 'none';
    $('claudeModel').value = state.settings.claude_model;
    $('whisperSel').value = state.settings.whisper_model;
    $('whisperInfo').textContent = `현재: ${state.whisper.model} · ${state.whisper.device === 'cuda' ? 'NVIDIA 그래픽카드 사용' : 'CPU 사용'}. 모델은 처음 한 번만 내려받습니다.`;
    const d = state.settings.defaults;
    $('dAi').checked = d.synthetic; $('dPaid').checked = d.paid; $('dKids').checked = d.made_for_kids;
    showUpdate(state.update);
    if (!autoOpened && (!state.has_claude || !ch)) { autoOpened = true; openDrawer(); }
  }
  function showUpdate(u) {
    if (!u) return;
    if (!u.enabled) { $('updInfo').textContent = '자동 업데이트 저장소가 아직 설정되지 않았습니다.'; return; }
    if (u.newer) {
      $('updBtn').style.display = '';
      $('updInfo').textContent = `새 버전 v${u.latest}이 있습니다.` + (u.installed ? '' : ' (소스 실행 중: git pull로 업데이트)');
      $('installUpd').style.display = u.installed ? '' : 'none';
    } else {
      $('updBtn').style.display = 'none';
      $('updInfo').textContent = `최신 버전입니다 (v${u.current}).`;
      $('installUpd').style.display = 'none';
    }
  }
  function openDrawer() {
    document.body.classList.add('drawer-open');
    api('/api/identity').then(r => { $('identityText').value = r.text; $('idPath').textContent = '저장 위치: ' + r.path; }).catch(() => {});
  }
  function closeDrawer() { document.body.classList.remove('drawer-open'); }
  $('setBtn').onclick = openDrawer; $('closeSet').onclick = closeDrawer; $('shade').onclick = closeDrawer;
  $('updBtn').onclick = openDrawer;

  $('saveClaude').onclick = async () => {
    const key = $('claudeKey').value.trim();
    if (!key) { // 키 없이 모델만 바꾸기
      if (!state.has_claude) return setMsg('msgClaude', 'API 키를 입력해 주세요.', true);
      await api('/api/settings', { body: { claude_model: $('claudeModel').value } });
      setMsg('msgClaude', '모델을 바꿨습니다.'); return loadState();
    }
    setMsg('msgClaude', '확인 중...');
    try {
      await api('/api/settings/claude', { body: { key, model: $('claudeModel').value } });
      $('claudeKey').value = ''; setMsg('msgClaude', '저장했습니다.'); loadState();
    } catch (e) { setMsg('msgClaude', e.message, true); }
  };
  $('clientBtn').onclick = () => $('clientFile').click();
  $('clientFile').onchange = async e => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try { await api('/api/google/client', { form: fd }); setMsg('msgYt', '클라이언트 파일을 등록했습니다. 이제 계정을 연결하세요.'); loadState(); }
    catch (err) { setMsg('msgYt', err.message, true); }
  };
  $('saveClientId').onclick = async () => {
    try {
      await api('/api/google/client-id', { body: { client_id: $('gcId').value, client_secret: $('gcSecret').value } });
      $('gcId').value = ''; $('gcSecret').value = '';
      setMsg('msgYt', '등록했습니다. 이제 [유튜브 계정 연결]을 누르세요.'); loadState();
    } catch (e) { setMsg('msgYt', e.message, true); }
  };
  $('connectBtn').onclick = async () => {
    setMsg('msgYt', '브라우저에 열린 구글 로그인 창에서 계정을 선택하고 권한을 허용해 주세요...');
    $('connectBtn').disabled = true;
    try { const r = await api('/api/google/connect', { method: 'POST', body: {} }); setMsg('msgYt', '연결됨: ' + r.channel.title); loadState(); }
    catch (e) { setMsg('msgYt', e.message, true); }
    finally { $('connectBtn').disabled = false; }
  };
  $('disconnectBtn').onclick = async () => { await api('/api/google/disconnect', { method: 'POST', body: {} }); setMsg('msgYt', '연결을 해제했습니다.'); loadState(); };
  $('saveId').onclick = async () => {
    try { await api('/api/identity', { body: { text: $('identityText').value } }); setMsg('msgId', '저장했습니다.'); }
    catch (e) { setMsg('msgId', e.message, true); }
  };
  $('genId').onclick = async () => {
    if (!state.channel) return setMsg('msgId', '먼저 유튜브 계정을 연결해 주세요.', true);
    if (!state.has_claude) return setMsg('msgId', '먼저 Claude API 키를 입력해 주세요.', true);
    $('genId').disabled = true; setMsg('msgId', '채널을 분석하는 중입니다 (30초~1분)...');
    try {
      const r = await api('/api/identity/generate', { method: 'POST', body: {} });
      $('identityText').value = r.text;
      setMsg('msgId', '초안을 만들었습니다. 내용을 확인하고 [저장]을 눌러 주세요.');
    } catch (e) { setMsg('msgId', e.message, true); }
    finally { $('genId').disabled = false; }
  };
  $('loadIdBtn').onclick = () => $('idFile').click();
  $('idFile').onchange = async e => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    $('identityText').value = await f.text();
    setMsg('msgId', `${f.name}을 불러왔습니다. 저장을 눌러야 적용됩니다.`);
  };
  $('whisperSel').onchange = () => api('/api/settings', { body: { whisper_model: $('whisperSel').value } }).then(loadState);
  for (const [id, key] of [['dAi', 'synthetic'], ['dPaid', 'paid'], ['dKids', 'made_for_kids']]) {
    $(id).onchange = () => api('/api/settings', { body: { defaults: { [key]: $(id).checked } } });
  }
  $('checkUpd').onclick = async () => {
    $('updInfo').textContent = '확인 중...';
    try { showUpdate(await api('/api/update/check')); } catch (e) { $('updInfo').textContent = e.message; }
  };
  $('installUpd').onclick = async () => {
    if (!confirm('업데이트를 설치할까요? 프로그램이 잠시 닫혔다가 다시 열립니다. 설정과 정체성 파일은 그대로 유지됩니다.')) return;
    try { await api('/api/update/install', { method: 'POST', body: {} }); $('updInfo').textContent = '설치 중입니다. 잠시 후 프로그램이 다시 열립니다.'; }
    catch (e) { $('updInfo').textContent = e.message; }
  };

  // ---------- 영상 넣기 ----------
  $('pickBtn').onclick = async () => {
    if (!ready()) return;
    try { const r = await api('/api/pick', { method: 'POST', body: {} }); if (r.path) startJob(r.path); }
    catch (e) { toast(e.message, true); }
  };
  function ready() {
    if (!state || !state.has_claude) { toast('먼저 설정에서 Claude API 키를 입력해 주세요.', true); openDrawer(); return false; }
    return true;
  }
  let dragDepth = 0;
  const idle = () => !job || job.status !== 'running';
  window.addEventListener('dragenter', e => { e.preventDefault(); if (!idle() || result) return; dragDepth++; Sphere.setMode('hover'); $('sub').textContent = '놓으면 분석을 시작합니다'; });
  window.addEventListener('dragleave', () => { if (!idle() || result) return; if (--dragDepth <= 0) { dragDepth = 0; Sphere.setMode('idle'); $('sub').textContent = '영상 파일을 여기에 끌어다 놓으세요'; } });
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => {
    e.preventDefault(); dragDepth = 0;
    if (!idle() || result) return;
    const f = e.dataTransfer.files[0];
    if (!f) return;
    if (!f.type.startsWith('video') && !/\.(mp4|mov|mkv|avi|webm|m4v|wmv|flv)$/i.test(f.name)) { Sphere.setMode('idle'); return toast('영상 파일만 넣을 수 있어요', true); }
    if (!ready()) { Sphere.setMode('idle'); return; }
    uploadThenStart(f);
  });
  function uploadThenStart(f) {
    Sphere.setMode('analyzing');
    showProgressUI(f.name, '파일 준비 중');
    const fd = new FormData(); fd.append('file', f);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload-video'); xhr.setRequestHeader('X-GUP-Token', TOKEN);
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) setBar(ev.loaded / ev.total); };
    xhr.onload = () => {
      const data = JSON.parse(xhr.responseText || '{}');
      if (xhr.status === 403 && data.detail === 'forbidden') { try { staleReload(); } catch (e) {} return; }
      if (xhr.status !== 200) return showError(data.detail || '파일을 받지 못했습니다.');
      startJob(data.path);
    };
    xhr.onerror = () => showError('파일을 받지 못했습니다.');
    xhr.send(fd);
  }
  function setBar(p) { $('bar').style.display = p == null ? 'none' : 'block'; if (p != null) $('bar').firstElementChild.style.width = (p * 100).toFixed(1) + '%'; }
  function showProgressUI(name, sub) {
    $('pickBtn').style.display = 'none'; $('errbox').style.display = 'none';
    $('sub').textContent = sub; $('fname').style.display = 'block'; $('fname').textContent = name;
  }
  async function startJob(path) {
    Sphere.setMode('analyzing');
    showProgressUI(path.split(/[\\/]/).pop(), '분석 중');
    setBar(null);
    try {
      const r = await api('/api/jobs', { body: { path } });
      job = { id: r.id, status: 'running' };
      poll();
    } catch (e) { showError(e.message); }
  }
  async function poll() {
    clearTimeout(pollTimer);
    try { job = await api('/api/jobs/' + job.id); }
    catch (e) { return showError(e.message); }
    renderSteps();
    if (job.status === 'running') pollTimer = setTimeout(poll, 600);
    else if (job.status === 'error') showError(job.error);
    else finish();
  }
  function renderSteps() {
    const st = $('steps'); st.style.display = 'block'; st.innerHTML = '';
    for (const s of job.steps) st.append(h('div', { class: s.state }, s.label));
    setBar(job.progress);
    $('note').textContent = job.note || '';
  }
  function showError(msg) {
    Sphere.setMode('idle');
    $('sub').textContent = '중단됨'; setBar(null);
    $('errbox').style.display = 'block'; $('errmsg').textContent = msg;
  }
  $('retryBtn').onclick = reset;
  $('againBtn').onclick = () => { if (!applied && result && !confirm('아직 적용하지 않았습니다. 처음으로 돌아갈까요?')) return; reset(); };
  $('logo').onclick = () => { if (!result && idle()) reset(); };
  function reset() {
    clearTimeout(pollTimer);
    job = null; result = null; thumbId = null; applied = false; edited = false; appliedVideoId = null;
    // 영상에 묶인 스튜디오만 지운다(따로 만들던 썸네일 작업은 남긴다)
    if (studioJob) { $('studioWrap').querySelector('iframe')?.remove(); studioFrame = null; studioJob = null; }
    closeStudio();
    $('studioLink').style.display = 'none';
    pick = { t: 'search', d: 'search', h: 'search' };
    Sphere.setMode('idle');
    $('result').style.display = 'none';
    $('steps').style.display = 'none'; $('note').textContent = ''; setBar(null);
    $('errbox').style.display = 'none'; $('fname').style.display = 'none';
    $('pickBtn').style.display = ''; $('sub').textContent = '영상 파일을 여기에 끌어다 놓으세요';
    $('applyBtn').textContent = '세팅 적용 (비공개 유지)'; $('pubBtn').textContent = '공개'; $('pubBtn').disabled = true;
    window.scrollTo({ top: 0 });
  }

  // ---------- 결과 ----------
  function finish() {
    result = job.result;
    Sphere.setMode('done');
    $('sub').textContent = '분석 완료'; setBar(null); $('note').textContent = '';
    const m = job.meta;
    $('metaRow').innerHTML = '';
    const chips = [['형식', m.shorts ? '숏폼' : '롱폼'], ['길이', fmtDur(m.duration)], ['비율', m.ratio], ['언어', result.language],
      ['카테고리', CATS[result.category_id] || result.category_id], ['챕터', result.chapters.length ? result.chapters.length + '개' : '없음']];
    for (const [k, v] of chips) $('metaRow').append(h('span', { class: 'chip' }, k + ' ', h('b', {}, v)));
    $('summary').textContent = result.summary || '';
    $('warns').innerHTML = '';
    for (const w of job.warnings) $('warns').append(h('div', {}, '⚠ ' + w));

    const d = state.settings.defaults, ds = result.disclosure || {};
    $('cAi').checked = d.synthetic || !!ds.synthetic; $('cPaid').checked = d.paid || !!ds.paid; $('cKids').checked = d.made_for_kids;
    $('aiWhy').textContent = ds.synthetic ? 'AI 판단: ' + ds.synthetic_reason : '실제처럼 보이는 AI 생성·합성 장면이 있으면 체크';
    $('paidWhy').textContent = ds.paid ? 'AI 판단: ' + ds.paid_reason : '협찬, 제품 제공, 광고가 있으면 체크';
    $('catSel').innerHTML = '';
    for (const [k, v] of Object.entries(CATS)) $('catSel').append(h('option', { value: k }, v));
    $('catSel').value = result.category_id;
    renderVideoSel(); renderThumb(); renderCards(); renderFinal();
    if (pendingThumb && !thumbId) { useThumbBlob(pendingThumb, 'studio.jpg'); pendingThumb = null; }
    $('result').style.display = 'block';
    setTimeout(() => $('result').scrollIntoView({ behavior: 'smooth' }), 400);
  }
  const V = s => result.versions.find(v => v.strategy === s);

  function renderVideoSel() {
    const sel = $('videoSel'); sel.innerHTML = '';
    if (!state.channel) {
      sel.append(h('option', { value: '' }, '유튜브 계정을 먼저 연결해 주세요 (설정)'));
      updateApplyLabel();
      return;
    }
    sel.append(h('option', { value: '__new__' }, `⬆ 이 파일을 새로 업로드 (${job.file_name})`));
    const PRIV = { private: '비공개', unlisted: '일부 공개', public: '공개' };
    for (const u of job.uploads) {
      const label = `이미 올린 영상에 적용: ${u.title} · ${PRIV[u.privacy] || u.privacy}` + (u.file_name ? ` · ${u.file_name}` : '');
      sel.append(h('option', { value: u.id }, label));
    }
    sel.value = job.video ? job.video.id : '__new__';
    updateApplyLabel();
  }
  function updateApplyLabel() {
    if (applied) return;
    $('applyBtn').textContent = $('videoSel').value === '__new__' ? '업로드 + 세팅 (비공개)' : '세팅 적용 (비공개 유지)';
  }
  $('videoSel').onchange = updateApplyLabel;

  // ---------- 썸네일 스튜디오 (거나두잇 썸네일 스튜디오 v8 내장) ----------
  // studioJob: 연결된 분석 작업 id, null이면 영상 없이 따로 여는 썸네일 제작 모드
  let studioFrame = null, studioJob = null, pendingThumb = null;
  const analyzedJob = () => (job && result ? job.id : null);
  function newStudio(jid) {
    $('studioWrap').querySelector('iframe')?.remove();
    studioFrame = h('iframe', { src: '/static/studio/studio.html?v=' + Date.now(), title: '거나두잇 썸네일 스튜디오' });
    $('studioWrap').append(studioFrame);
    studioJob = jid;
  }
  function openStudio() {
    const jid = analyzedJob();
    if (!studioFrame) newStudio(jid);
    else if (studioJob !== jid) {
      if (studioJob === null && jid) {
        // 따로 만들던 작업은 그대로 두고, 방금 분석한 영상에 연결만 한다
        studioJob = jid;
        studioFrame.contentWindow.postMessage({ type: 'gup:attach', job: jid }, location.origin);
      } else newStudio(jid);
    }
    $('studioHint').textContent = studioJob
      ? '다 만들었으면 미리보기 아래 [G-UPLOADER에 적용]을 누르세요'
      : '영상이나 사진을 올려 썸네일을 만드세요 · [JPG로 저장]은 파일로 저장하고, 다음에 분석하는 영상에도 자동으로 들어갑니다';
    document.body.classList.add('studio-open');
  }
  function closeStudio() { document.body.classList.remove('studio-open'); }
  $('studioClose').onclick = closeStudio;
  $('thumbOnlyBtn').onclick = openStudio;
  function downloadBlob(blob, name) {
    const a = h('a', { href: URL.createObjectURL(blob), download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '');
  window.addEventListener('message', async e => {
    if (e.origin !== location.origin || !studioFrame || e.source !== studioFrame.contentWindow) return;
    const m = e.data || {};
    if (m.type === 'gup:ready') {
      studioFrame.contentWindow.postMessage(studioJob ? {
        type: 'gup:init',
        job: studioJob,
        video: { url: '/media/' + studioJob, name: job.file_name },
        text: result && result.thumbnail && result.thumbnail.line1 ? result.thumbnail : null
      } : { type: 'gup:init', standalone: true }, location.origin);
    } else if (m.type === 'gup:thumb' && m.blob) {
      if (studioJob && result) {
        closeStudio();
        await useThumbBlob(m.blob, 'studio.jpg');
      } else {
        pendingThumb = m.blob;
        downloadBlob(m.blob, `thumbnail_${m.fmt === 'short' ? '9x16' : '16x9'}_${stamp()}.jpg`);
        toast('썸네일을 저장했습니다. 다음에 분석하는 영상에도 자동으로 들어갑니다.');
      }
    } else if (m.type === 'gup:save' && m.blob) {
      downloadBlob(m.blob, m.name || `thumbnail_${stamp()}.png`);
      toast('PNG로 저장했습니다 (다운로드 폴더)');
    }
  });

  function renderThumb() {
    const w = $('thumbWrap'); w.innerHTML = '';
    w.append(h('div', { class: 'line', style: 'display:flex;gap:8px;margin-bottom:10px' },
      h('button', { class: 'btn solid', type: 'button', style: 'flex:1', onclick: openStudio }, '썸네일 스튜디오에서 만들기'),
      h('button', { class: 'btn', type: 'button', style: 'flex:none;padding:10px 14px', onclick: () => $('thumbFile').click() }, '이미지 올리기')));
    const v = job.meta.shorts;
    const box = h('div', { class: 'thumb', id: 'thumbBox', style: v ? 'aspect-ratio:9/16;max-width:220px' : '' },
      '썸네일 이미지를 놓거나 클릭해서 선택', h('br'), v ? '1080×1920 (9:16) · 2MB 이하로 자동 변환' : '1280×720 · 2MB 이하로 자동 변환');
    box.onclick = () => $('thumbFile').click();
    box.ondragover = e => { e.preventDefault(); e.stopPropagation(); };
    box.ondrop = e => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer.files[0]; if (f) setThumb(f); };
    w.append(box);
    if (v) w.append(h('div', { class: 'warn', style: 'margin-top:10px' }, '숏폼 썸네일은 유튜브 처리가 끝난 뒤에 적용됩니다. 업로드 직후 실패하면 몇 분 뒤 [다시 적용]을 눌러 주세요.'));
  }
  $('thumbFile').onchange = e => { const f = e.target.files[0]; e.target.value = ''; if (f) setThumb(f); };
  async function setThumb(f) {
    if (!f.type.startsWith('image')) return toast('이미지 파일만 넣을 수 있어요', true);
    await useThumbBlob(f, f.name);
  }
  async function useThumbBlob(f, name) {
    const box = $('thumbBox');
    box.textContent = '변환 중...'; box.style.backgroundImage = '';
    const fd = new FormData(); fd.append('file', f, name);
    try {
      const r = await api('/api/thumbnail?vertical=' + (job.meta.shorts ? 'true' : 'false'), { form: fd });
      thumbId = r.id;
      box.style.backgroundImage = `url(${URL.createObjectURL(f)})`; box.textContent = '';
      toast('썸네일을 넣었습니다. [업로드 + 세팅] 때 함께 올라갑니다.');
    } catch (e) { box.textContent = e.message; thumbId = null; }
  }

  function renderCards() {
    const wrap = $('cards'); wrap.innerHTML = '';
    for (const v of result.versions) {
      const s = v.strategy;
      const full = pick.t === s && pick.d === s && pick.h === s;
      const field = (f, label, cls, text) => {
        const el = h('div', { class: 'field' + (pick[f] === s ? ' sel' : '') }, h('div', { class: 'k' }, label), h('div', { class: cls }, text));
        el.onclick = () => { pick[f] = s; renderCards(); renderFinal(); };
        return el;
      };
      const facts = h('div', { class: 'facts' });
      for (const k of v.keywords) facts.append(h('span', {}, k));
      facts.append(h('span', {}, `제목 ${v.title.length}자`));
      if (v.problems.length) for (const p of v.problems) facts.append(h('span', { class: 'bad' }, '⚠ ' + p));
      else facts.append(h('span', {}, '말투 점검 ✓'));

      const input = h('input', { type: 'text', placeholder: '예: 더 짧게, 덜 진지하게 (비워도 됨)' });
      const rw = h('div', { class: 'rw' }, input, h('button', { class: 'btn solid', type: 'button', style: 'flex:none;padding:8px 14px', onclick: () => doRewrite(s, input.value, card) }, '실행'));
      input.addEventListener('keydown', e => { if (e.key === 'Enter') doRewrite(s, input.value, card); });
      const card = h('div', { class: 'card' + (full ? ' full' : '') },
        h('div', { class: 'lab' }, h('span', { class: 'en' }, v.label), h('span', {}, v.strategy === 'search' ? '검색 유입 중심' : v.strategy === 'click' ? '추천 피드 중심' : '내 채널 말투 중심')),
        field('t', '제목', 't', v.title),
        field('d', '설명', 'd', v.description),
        field('h', '해시태그', 'h', v.hashtags.join(' ')),
        facts,
        v.rationale ? h('div', { class: 'why' }, v.rationale) : null,
        rw,
        h('div', { class: 'btns' },
          h('button', { class: 'btn' + (full ? ' solid' : ''), type: 'button', onclick: () => { pick = { t: s, d: s, h: s }; renderCards(); renderFinal(); } }, full ? '선택됨' : '이 버전 전체 선택'),
          h('button', { class: 'btn', type: 'button', onclick: () => { rw.style.display = rw.style.display === 'flex' ? 'none' : 'flex'; input.focus(); } }, '다시 쓰기')));
      wrap.append(card);
    }
  }
  async function doRewrite(strategy, instruction, card) {
    card.classList.add('busy');
    toast(V(strategy).label + ' 다시 쓰는 중...');
    try {
      const nv = await api(`/api/jobs/${job.id}/rewrite`, { body: { strategy, instruction } });
      result.versions[result.versions.findIndex(v => v.strategy === strategy)] = nv;
      renderCards(); renderFinal(); toast('새로 썼습니다');
    } catch (e) { card.classList.remove('busy'); toast(e.message, true); }
  }

  function renderFinal() {
    const L = s => ({ search: 'A', click: 'B', channel: 'C' })[s];
    $('combo').textContent = `TITLE ${L(pick.t)}  ·  DESCRIPTION ${L(pick.d)}  ·  HASHTAGS ${L(pick.h)}`;
    $('fT').textContent = V(pick.t).title;
    $('fD').textContent = V(pick.d).description;
    $('fH').textContent = V(pick.h).hashtags.join(' ');
    $('fG').textContent = V(pick.t).tags.join(', ');
    edited = false; counters();
  }
  const finalTags = () => $('fG').textContent.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
  const finalHashtags = () => $('fH').textContent.split(/\s+/).map(s => s.trim()).filter(Boolean).map(s => s.startsWith('#') ? s : '#' + s);
  function counters() {
    const t = $('fT').textContent.trim();
    const desc = $('fD').textContent.trim() + (finalHashtags().length ? '\n\n' + finalHashtags().join(' ') : '');
    const tagLen = finalTags().reduce((a, s, i) => a + s.length + (s.includes(' ') ? 2 : 0) + (i ? 1 : 0), 0);
    const set = (id, txt, bad) => { $(id).textContent = txt; $(id).className = 'counter' + (bad ? ' bad' : ''); };
    set('fTc', `${t.length} / 100자`, t.length > 100 || !t);
    set('fDc', `${bytes(desc)} / 5000바이트`, bytes(desc) > 5000);
    set('fGc', `${tagLen} / 500자`, tagLen > 500);
  }
  for (const id of ['fT', 'fD', 'fH', 'fG']) $(id).addEventListener('input', () => { edited = true; counters(); });

  $('when').onchange = () => {
    const on = $('when').value === 'sched';
    $('whenAt').style.display = on ? 'block' : 'none';
    if (on && !$('whenAt').value) {
      const d = new Date(Date.now() + 86400000); d.setHours(18, 0, 0, 0);
      $('whenAt').value = new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
  };

  $('applyBtn').onclick = async () => {
    const videoId = $('videoSel').value;
    if (!state.channel) { openDrawer(); return toast('먼저 유튜브 계정을 연결해 주세요.', true); }
    if (!videoId) return toast('적용할 유튜브 영상을 선택해 주세요.', true);
    let publishAt = null;
    if ($('when').value === 'sched') {
      const d = new Date($('whenAt').value);
      if (isNaN(d) || d < new Date()) return toast('예약 시간은 지금 이후로 정해 주세요.', true);
      publishAt = d.toISOString();
    }
    const tags = finalTags();
    const body = {
      job_id: job.id, video_id: videoId,
      title: $('fT').textContent.trim(), description: $('fD').textContent.trim(),
      hashtags: finalHashtags(), tags,
      category_id: $('catSel').value, language: result.language,
      made_for_kids: $('cKids').checked, synthetic: $('cAi').checked, paid: $('cPaid').checked,
      publish_at: publishAt, thumbnail_id: thumbId, picked: pick, edited
    };
    const isNew = videoId === '__new__';
    $('applyBtn').disabled = true; $('applyBtn').textContent = isNew ? '업로드 준비 중...' : '적용 중...';
    try {
      const { task } = await api('/api/apply', { body });
      let t;
      while (true) {
        await new Promise(r => setTimeout(r, 800));
        t = await api('/api/tasks/' + task);
        const pct = t.progress != null ? ` ${Math.round(t.progress * 100)}%` : '';
        $('applyBtn').textContent = t.stage + pct;
        if (t.status !== 'running') break;
      }
      if (t.status === 'error') throw new Error(t.error);
      applied = true; appliedVideoId = t.video_id;
      if (isNew) {
        // 같은 영상을 두 번 올리지 않도록, 이후 적용은 방금 올린 영상에 한다.
        const sel = $('videoSel');
        sel.prepend(h('option', { value: t.video_id }, `방금 올린 영상에 다시 적용 (${t.video_id})`));
        sel.querySelector('option[value="__new__"]').remove();
        sel.value = t.video_id;
      }
      $('applyBtn').textContent = '다시 적용';
      $('studioLink').href = `https://studio.youtube.com/video/${t.video_id}/edit`; $('studioLink').style.display = '';
      if (publishAt) { $('pubBtn').textContent = '예약됨 ✓'; $('pubBtn').disabled = true; toast('완료했습니다. 예약 시간에 자동으로 공개됩니다.'); }
      else { $('pubBtn').disabled = false; toast(isNew ? '비공개로 업로드하고 세팅까지 마쳤습니다' : '유튜브에 세팅을 적용했습니다 (비공개 상태)'); }
      for (const w of t.warnings || []) $('warns').append(h('div', {}, '⚠ ' + w));
      if ((t.warnings || []).length) toast(t.warnings[0], true);
    } catch (e) { applied = false; updateApplyLabel(); toast(e.message, true); }
    finally { $('applyBtn').disabled = false; }
  };
  $('pubBtn').onclick = async () => {
    if (!confirm('지금 공개할까요? 구독자에게 바로 보이게 됩니다.')) return;
    $('pubBtn').disabled = true;
    try { await api('/api/publish', { body: { video_id: appliedVideoId } }); $('pubBtn').textContent = '공개됨 ✓'; toast('영상이 공개되었습니다'); }
    catch (e) { $('pubBtn').disabled = false; toast(e.message, true); }
  };

  loadState().catch(e => toast(e.message, true));
})();
