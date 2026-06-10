// ── State
const state = {
  scripts: [],
  index: 0,
  recorder: null,
  chunks: [],
  recordedBlob: null,
  recordingStartMs: 0,
  timerHandle: null,
  isRecording: false,
};

// ── DOM
const $ = (id) => document.getElementById(id);
const refs = {
  scriptCard:     $('scriptCard'),
  counterCurrent: $('counterCurrent'),
  counterTotal:   $('counterTotal'),
  tagDomain:      $('tagDomain'),
  tagLength:      $('tagLength'),
  progressText:   $('progressText'),
  progressFill:   $('progressFill'),
  speakerInput:   $('speakerInput'),
  recordBtn:      $('recordBtn'),
  recordLabel:    document.querySelector('.recordLabel'),
  timer:          $('timer'),
  playback:       $('playback'),
  skipBtn:        $('skipBtn'),
  redoBtn:        $('redoBtn'),
  saveBtn:        $('saveBtn'),
  status:         $('status'),
  prevBtn:        $('prevBtn'),
  nextBtn:        $('nextBtn'),
};

// ── Init
(async function init() {
  const saved = localStorage.getItem('blani_speaker') || '';
  refs.speakerInput.value = saved;
  refs.speakerInput.addEventListener('input', (e) => {
    localStorage.setItem('blani_speaker', e.target.value.trim());
  });

  await loadScripts();
  const first = state.scripts.findIndex((s) => !s.recorded);
  state.index = first === -1 ? 0 : first;
  render();
  bindEvents();
})();

async function loadScripts() {
  try {
    setStatus('Loading…');
    const r = await fetch('/api/scripts');
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    state.scripts = d.scripts || [];
    refs.counterTotal.textContent = d.total;
    updateProgress(d.recorded_count);
    setStatus('');
  } catch (e) {
    setStatus('Failed to load — ' + e.message, 'err');
  }
}

// ── Render
function render() {
  const s = state.scripts[state.index];
  if (!s) return;
  refs.counterCurrent.textContent = String(state.index + 1).padStart(3, '0');
  refs.tagDomain.textContent = s.domain;
  refs.tagLength.textContent = s.length;
  refs.scriptCard.innerHTML = `
    ${s.recorded ? '<span class="recordedBadge">✓ Recorded</span>' : ''}
    <div class="scriptArabic">${esc(s.arabic)}</div>
    <div class="scriptLatin">${esc(s.latin)}</div>
    <div class="scriptEnglish">${esc(s.english)}</div>
  `;
  resetUI();
  refs.prevBtn.disabled = state.index === 0;
  refs.nextBtn.disabled = state.index === state.scripts.length - 1;
}

function updateProgress(count) {
  const total = state.scripts.length || 1;
  refs.progressText.textContent = `${count} / ${total} recorded`;
  refs.progressFill.style.right = `${100 - (count / total) * 100}%`;
}

function setStatus(msg, kind = '') {
  refs.status.textContent = msg;
  refs.status.className = 'status' + (kind === 'ok' ? ' statusOk' : kind === 'err' ? ' statusErr' : '');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>'"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])
  );
}

function resetUI() {
  state.recordedBlob = null;
  state.chunks = [];
  state.isRecording = false;
  refs.recordBtn.classList.remove('recording');
  refs.recordLabel.textContent = 'Tap to Record';
  refs.timer.textContent = '00:00';
  refs.playback.hidden = true;
  refs.playback.src = '';
  refs.saveBtn.hidden = true;
  refs.redoBtn.hidden = true;
  setStatus('');
}

// ── Recording
async function startRecording() {
  if (state.isRecording) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const types = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'];
    const mime = types.find(t => MediaRecorder.isTypeSupported(t)) || '';
    state.recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    state.chunks = [];

    state.recorder.ondataavailable = (e) => {
      if (e.data?.size > 0) state.chunks.push(e.data);
    };

    state.recorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(state.chunks, { type: state.recorder.mimeType || 'audio/mp4' });
      state.recordedBlob = blob;
      refs.playback.src = URL.createObjectURL(blob);
      refs.playback.hidden = false;
      refs.saveBtn.hidden = false;
      refs.redoBtn.hidden = false;
      refs.recordBtn.classList.remove('recording');
      refs.recordLabel.textContent = 'Tap to Record';
      stopTimer();
      setStatus('Done — listen back then save.', 'ok');
    };

    state.recorder.start(100); // collect data every 100ms — helps Safari
    state.isRecording = true;
    state.recordingStartMs = Date.now();
    refs.recordBtn.classList.add('recording');
    refs.recordLabel.textContent = 'Recording… tap to stop';
    setStatus('Speak now.');
    startTimer();
  } catch (e) {
    setStatus('Mic error: ' + e.message, 'err');
  }
}

function stopRecording() {
  if (!state.isRecording || !state.recorder) return;
  state.isRecording = false;
  try { state.recorder.stop(); } catch {}
}

function startTimer() {
  state.timerHandle = setInterval(() => {
    const s = (Date.now() - state.recordingStartMs) / 1000;
    refs.timer.textContent =
      String(Math.floor(s / 60)).padStart(2, '0') + ':' +
      String(Math.floor(s % 60)).padStart(2, '0');
  }, 200);
}

function stopTimer() {
  clearInterval(state.timerHandle);
  state.timerHandle = null;
}

// ── Save
async function save() {
  if (!state.recordedBlob) { setStatus('Nothing to save.', 'err'); return; }
  const speaker = refs.speakerInput.value.trim();
  if (!speaker) { setStatus('Enter your name first.', 'err'); refs.speakerInput.focus(); return; }

  const s = state.scripts[state.index];
  const mime = state.recordedBlob.type || '';
  const ext = mime.includes('mp4') || mime.includes('m4a') ? 'm4a'
             : mime.includes('ogg') ? 'ogg' : 'webm';
  const form = new FormData();
  form.append('id', s.id);
  form.append('speaker_id', speaker);
  form.append('audio', state.recordedBlob, `${s.id}.${ext}`);

  setStatus('Saving…');
  refs.saveBtn.disabled = true;
  try {
    const r = await fetch('/api/recordings', { method: 'POST', body: form });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || `HTTP ${r.status}`);
    state.scripts[state.index].recorded = true;
    updateProgress(state.scripts.filter(x => x.recorded).length);
    setStatus(`✓ Saved (${d.row.duration_seconds}s)`, 'ok');
    const next = state.scripts.findIndex((x, i) => i > state.index && !x.recorded);
    if (next !== -1) { state.index = next; render(); }
    else setStatus('All done!', 'ok');
  } catch (e) {
    setStatus('Save failed: ' + e.message, 'err');
  } finally {
    refs.saveBtn.disabled = false;
  }
}

// ── Events — iOS-safe tap handling
function safeTap(el, fn) {
  let moved = false;
  el.addEventListener('touchstart', () => { moved = false; }, { passive: true });
  el.addEventListener('touchmove',  () => { moved = true;  }, { passive: true });
  el.addEventListener('touchend', (e) => {
    if (!moved) { e.preventDefault(); fn(); }
  });
  // fallback for desktop mouse
  el.addEventListener('click', (e) => {
    if (e.pointerType !== 'touch') fn();
  });
}

function bindEvents() {
  safeTap(refs.recordBtn, () => {
    state.isRecording ? stopRecording() : startRecording();
  });
  safeTap(refs.skipBtn, () => {
    const next = state.scripts.findIndex((x, i) => i > state.index && !x.recorded);
    state.index = next !== -1 ? next : Math.min(state.index + 1, state.scripts.length - 1);
    render();
  });
  safeTap(refs.redoBtn, resetUI);
  safeTap(refs.saveBtn, save);
  safeTap(refs.prevBtn, () => { if (state.index > 0) { state.index--; render(); } });
  safeTap(refs.nextBtn, () => { if (state.index < state.scripts.length - 1) { state.index++; render(); } });
}
