let currentSettings = null;
let hlsPlayers = {};

function api(path, options = {}) {
  return fetch(path, {
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options
  }).then(async r => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  });
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setStatusClass() {
  const mode = document.getElementById('mode')?.textContent || '';
  document.body.dataset.mode = mode;
}

function hlsUrl(path) {
  return `http://${location.hostname}:8888/${path}/index.m3u8`;
}
function webrtcUrl(path) {
  return `http://${location.hostname}:8889/${path}`;
}

function setupVideo(id, url) {
  const video = document.getElementById(id);
  if (!video) return;
  if (video.dataset.src === url) return;
  video.dataset.src = url;
  if (hlsPlayers[id]) {
    hlsPlayers[id].destroy();
    delete hlsPlayers[id];
  }
  if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = url;
  } else if (window.Hls && Hls.isSupported()) {
    const hls = new Hls({lowLatencyMode: true, liveDurationInfinity: true});
    hls.loadSource(url);
    hls.attachMedia(video);
    hlsPlayers[id] = hls;
  } else {
    video.outerHTML = `<p class="small">HLS preview needs hls.js/browser support. Open the link below in VLC.</p>`;
  }
}

function fillForm(formId, settings) {
  const form = document.getElementById(formId);
  if (!form) return;
  [...form.elements].forEach(el => {
    if (!el.name) return;
    const parts = el.name.split('.');
    let v = settings;
    for (const part of parts) v = v?.[part];
    if (v === undefined) return;
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = v;
  });
}

function formToNested(form) {
  const out = {};
  [...form.elements].forEach(el => {
    if (!el.name) return;
    const parts = el.name.split('.');
    let ref = out;
    for (let i = 0; i < parts.length - 1; i++) {
      ref[parts[i]] = ref[parts[i]] || {};
      ref = ref[parts[i]];
    }
    let value;
    if (el.type === 'checkbox') value = el.checked;
    else if (el.type === 'number') value = el.value === '' ? '' : Number(el.value);
    else value = el.value;
    ref[parts[parts.length - 1]] = value;
  });
  return out;
}

function fillSelect(id, files, active) {
  const select = document.getElementById(id);
  if (!select) return;
  select.innerHTML = '<option value="">None selected</option>';
  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    if (f === active) opt.selected = true;
    select.appendChild(opt);
  });
}

async function refreshStatus() {
  try {
    const data = await api('/api/status');
    currentSettings = data.settings;
    setText('mode', data.mode || '—');
    setText('input', data.input_connected ? 'CONNECTED' : 'MISSING');
    setText('output', data.ffmpeg_running ? data.process_kind : 'STOPPED');
    setText('autoEnd', data.auto_end_seconds_remaining == null ? '—' : `${data.auto_end_seconds_remaining}s`);
    setText('weatherLine', `Weather line: ${data.last_weather_line || '—'}`);
    const errs = [data.last_weather_error, data.last_ffmpeg_error].filter(Boolean).join(' | ');
    setText('errors', errs);
    setStatusClass();

    const rawHls = hlsUrl('live/drone');
    const programHls = hlsUrl('live/program');
    setupVideo('programPreview', programHls);
    setupVideo('rawPreview', rawHls);
    document.getElementById('programHlsLink').href = programHls;
    document.getElementById('rawHlsLink').href = rawHls;
    document.getElementById('programWebrtcLink').href = webrtcUrl('live/program');
    document.getElementById('rawWebrtcLink').href = webrtcUrl('live/drone');

    fillSelect('activeBrb', data.media?.brb || [], currentSettings?.brb?.active_mp4 || '');
    fillSelect('activeMp3', data.media?.audio || [], currentSettings?.audio?.active_mp3 || '');
    fillForm('quickSettings', currentSettings);
    fillForm('destSettings', currentSettings);
    fillForm('haSettings', currentSettings);

    document.getElementById('ingestUrls').textContent = [
      `Local DJI Fly ingest: rtmp://${location.hostname}:19350/live/drone`,
      currentSettings?.ingest?.tailscale_url_hint ? `Tailscale ingest: ${currentSettings.ingest.tailscale_url_hint}` : 'Tailscale ingest: add later',
      `Admin: http://${location.hostname}:8589/admin`,
      `Program preview: ${programHls}`
    ].join('\n');
  } catch (err) {
    setText('errors', err.message);
  }
}

async function postAction(path) {
  try {
    await api(path, {method: 'POST', body: '{}'});
    await refreshStatus();
  } catch (err) {
    alert(err.message);
  }
}

document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  e.preventDefault();
  postAction(btn.dataset.action);
});

document.querySelectorAll('.settings-form').forEach(form => {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/settings', {method: 'POST', body: JSON.stringify(formToNested(form))});
      await refreshStatus();
      alert('Saved');
    } catch (err) {
      alert(err.message);
    }
  });
});

document.querySelectorAll('.upload-form').forEach(form => {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = form.dataset.kind;
    const fd = new FormData(form);
    try {
      const r = await fetch(`/api/upload/${kind}`, {method: 'POST', body: fd, credentials: 'same-origin'});
      const data = await r.json();
      if (!r.ok || data.ok === false) throw new Error(data.error || `HTTP ${r.status}`);
      form.reset();
      await refreshStatus();
      alert('Uploaded');
    } catch (err) {
      alert(err.message);
    }
  });
});

document.getElementById('selectBrb')?.addEventListener('click', async () => {
  const filename = document.getElementById('activeBrb').value;
  await api('/api/media/select', {method: 'POST', body: JSON.stringify({kind: 'brb', filename})});
  await refreshStatus();
});

document.getElementById('selectMp3')?.addEventListener('click', async () => {
  const filename = document.getElementById('activeMp3').value;
  await api('/api/media/select', {method: 'POST', body: JSON.stringify({kind: 'audio', filename})});
  await refreshStatus();
});

refreshStatus();
setInterval(refreshStatus, 3000);
