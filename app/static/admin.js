let currentSettings = null;
let hlsPlayers = {};
let formsFilledOnce = false;
let userEditing = false;

const SECRET_FIELDS = new Set([
  'weather.openweather_api_key',
  'home_assistant.token',
  'destinations.youtube_stream_key',
  'destinations.twitch_stream_key'
]);

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

function nestedValue(settings, name) {
  const parts = name.split('.');
  let v = settings;
  for (const part of parts) v = v?.[part];
  return v;
}

function fillForm(formId, settings) {
  const form = document.getElementById(formId);
  if (!form) return;

  [...form.elements].forEach(el => {
    if (!el.name) return;
    if (SECRET_FIELDS.has(el.name)) {
      el.value = '';
      return;
    }
    const v = nestedValue(settings, el.name);
    if (v === undefined) return;
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = v;
  });
}

function fillAllForms(settings) {
  if (userEditing && formsFilledOnce) return;
  ['systemSettings', 'weatherSettings', 'destSettings', 'haSettings', 'audioBrbSettings'].forEach(id => fillForm(id, settings));
  formsFilledOnce = true;
}

function formToNested(form) {
  const out = {};
  [...form.elements].forEach(el => {
    if (!el.name) return;

    // Important: blank secret fields mean "keep the saved value".
    if (SECRET_FIELDS.has(el.name) && !el.value.trim()) return;

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
  const current = select.value;
  select.innerHTML = '<option value="">None selected</option>';
  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    if (f === active || f === current) opt.selected = true;
    select.appendChild(opt);
  });
}

function setModeClasses(data) {
  document.body.dataset.mode = data.mode || 'OFFLINE';
  document.body.dataset.system = data.system_enabled ? 'enabled' : 'disabled';
  document.body.dataset.test = data.local_test_mode ? 'on' : 'off';
}

function summarizeDestinations(data) {
  const d = data.destination_summary || {};
  if (!d.system_enabled) return 'System disabled. Nothing will stream.';
  if (d.local_test_mode) return 'Local Test Mode is ON. Final program preview only. YouTube/Twitch are blocked.';
  const bits = [];
  bits.push(`YouTube ${d.youtube_enabled ? (d.youtube_ready ? 'ready' : 'enabled, no key') : 'off'}`);
  bits.push(`Twitch ${d.twitch_enabled ? (d.twitch_ready ? 'ready' : 'enabled, no key') : 'off'}`);
  return bits.join(' · ');
}

function summarizeWeather(data) {
  const w = data.current_weather || {};
  if (w.error || data.last_weather_error) {
    return `Weather error: ${w.error || data.last_weather_error}`;
  }
  const age = data.last_weather_age_seconds == null ? '—' : `${data.last_weather_age_seconds}s ago`;
  const key = data.weather_key_saved ? 'key saved' : 'no key';
  const src = w.source_location_name ? ` · source: ${w.source_location_name}` : '';
  return `${key} · updated ${age}${src}`;
}

async function refreshStatus(forceForms = false) {
  try {
    const data = await api('/api/status');
    currentSettings = data.settings;

    setText('mode', data.mode || '—');
    setText('input', data.input_connected ? 'CONNECTED' : 'MISSING');
    setText('output', data.ffmpeg_running ? data.process_kind : 'STOPPED');
    setText('autoEnd', data.auto_end_seconds_remaining == null ? '—' : `${data.auto_end_seconds_remaining}s`);
    setText('weatherLine', data.last_weather_line || '—');
    setText('weatherMeta', summarizeWeather(data));
    setText('destinationSummary', summarizeDestinations(data));
    setText('systemPill', data.system_enabled ? 'SYSTEM ON' : 'SYSTEM DISABLED');
    setText('testPill', data.local_test_mode ? 'LOCAL TEST ON' : 'LIVE OUTPUT MODE');

    const errs = [data.last_weather_error, data.last_ffmpeg_error].filter(Boolean).join(' | ');
    setText('errors', errs);

    setText('summaryLine', [
      `Preset: ${data.active_preset || '—'}`,
      `Offline: ${data.offline_seconds || 0}s`,
      summarizeDestinations(data)
    ].join(' · '));

    setModeClasses(data);

    const rawHls = hlsUrl('live/drone');
    const programHls = hlsUrl('live/program');
    setupVideo('programPreview', programHls);
    setupVideo('rawPreview', rawHls);

    const links = {
      programHlsLink: programHls,
      rawHlsLink: rawHls,
      programWebrtcLink: webrtcUrl('live/program'),
      rawWebrtcLink: webrtcUrl('live/drone')
    };
    Object.entries(links).forEach(([id, url]) => {
      const el = document.getElementById(id);
      if (el) el.href = url;
    });

    fillSelect('activeBrb', data.media?.brb || [], currentSettings?.brb?.active_mp4 || '');
    fillSelect('activeMp3', data.media?.audio || [], currentSettings?.audio?.active_mp3 || '');

    if (forceForms) formsFilledOnce = false;
    fillAllForms(currentSettings);

    const ingest = [
      `Local DJI Fly ingest: rtmp://${location.hostname}:19350/live/drone`,
      currentSettings?.ingest?.tailscale_url_hint ? `Tailscale ingest: ${currentSettings.ingest.tailscale_url_hint}` : 'Tailscale ingest: add later',
      `Admin: http://${location.hostname}:8589/admin`,
      `Final program preview: ${programHls}`,
      `Mode: ${data.local_test_mode ? 'LOCAL TEST ONLY' : 'YouTube/Twitch allowed if enabled'}`
    ].join('\n');
    setText('ingestUrls', ingest);
  } catch (err) {
    setText('errors', err.message);
  }
}

async function postAction(path) {
  try {
    await api(path, {method: 'POST', body: '{}'});
    await refreshStatus(true);
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
  form.addEventListener('input', () => { userEditing = true; });
  form.addEventListener('focusin', () => { userEditing = true; });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/api/settings', {method: 'POST', body: JSON.stringify(formToNested(form))});
      userEditing = false;
      formsFilledOnce = false;
      await refreshStatus(true);
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
      await refreshStatus(true);
      alert('Uploaded');
    } catch (err) {
      alert(err.message);
    }
  });
});

document.getElementById('selectBrb')?.addEventListener('click', async () => {
  const filename = document.getElementById('activeBrb').value;
  await api('/api/media/select', {method: 'POST', body: JSON.stringify({kind: 'brb', filename})});
  await refreshStatus(true);
});

document.getElementById('selectMp3')?.addEventListener('click', async () => {
  const filename = document.getElementById('activeMp3').value;
  await api('/api/media/select', {method: 'POST', body: JSON.stringify({kind: 'audio', filename})});
  await refreshStatus(true);
});

refreshStatus(true);
setInterval(() => refreshStatus(false), 3000);
