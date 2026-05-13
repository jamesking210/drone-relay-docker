let currentSettings = null;
let hlsPlayers = {};
let formsFilledOnce = false;
let userEditing = false;

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
    video.outerHTML = `<p class="muted">HLS preview needs hls.js/browser support. Open the link below in VLC.</p>`;
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
    const v = nestedValue(settings, el.name);
    if (v === undefined) return;
    if (el.type === 'checkbox') el.checked = !!v;
    else el.value = v;
  });
}

function fillAllForms(settings) {
  if (userEditing && formsFilledOnce) return;
  ['outputSettings', 'weatherSettings', 'haSettings', 'audioBrbSettings'].forEach(id => fillForm(id, settings));
  formsFilledOnce = true;
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
    else if (el.type === 'number' || el.type === 'range') value = el.value === '' ? '' : Number(el.value);
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
  document.body.dataset.test = data.local_test_mode || data.mode === 'TEST_PATTERN' ? 'on' : 'off';
}

function summarizeDestinations(data) {
  const d = data.destination_summary || {};
  if (!d.system_enabled) return 'System disabled. Nothing will stream.';
  if (d.local_test_mode || data.mode === 'TEST_PATTERN') return 'Local-only mode. YouTube/Twitch are blocked.';
  const bits = [];
  bits.push(`YouTube ${d.youtube_enabled ? (d.youtube_ready ? 'ready' : 'enabled, missing .env key') : 'off'}`);
  bits.push(`Twitch ${d.twitch_enabled ? (d.twitch_ready ? 'ready' : 'enabled, missing .env key') : 'off'}`);
  return bits.join(' · ');
}

function summarizeWeather(data) {
  const w = data.current_weather || {};
  if (w.error || data.last_weather_error) return `Weather error: ${w.error || data.last_weather_error}`;
  const age = data.last_weather_age_seconds == null ? '—' : `${data.last_weather_age_seconds}s ago`;
  const key = data.weather_key_saved ? 'OpenWeather key in .env' : 'missing OPENWEATHER_API_KEY in .env';
  const src = w.source_location_name ? ` · source: ${w.source_location_name}` : '';
  return `${key} · updated ${age}${src}`;
}

function boolWord(v) { return v ? 'YES' : 'NO'; }

function updateConfigHints(data) {
  const c = data.config_summary || {};
  const d = data.destination_summary || {};
  setText('youtubeReady', d.youtube_ready ? 'Stream key found in .env.' : 'Missing YOUTUBE_STREAM_KEY in .env.');
  setText('twitchReady', d.twitch_ready ? 'Stream key found in .env.' : 'Missing TWITCH_STREAM_KEY in .env.');
  setText('haReady', d.home_assistant_ready ? 'HA token found in .env.' : 'Missing HOME_ASSISTANT_TOKEN in .env.');
  setText('haNotifyInfo', `Notify service: ${c.ha_notify_service || 'not set'}`);

  const box = [
    `HA URL set: ${boolWord(c.home_assistant_url)}`,
    `HA token set: ${boolWord(c.home_assistant_token)}`,
    `Phone entity: ${c.ha_phone_entity || 'not set'}`,
    `ZIP helper: ${c.ha_zip_override_entity || 'not set'}`,
    `Notify service: ${c.ha_notify_service || 'not set'}`,
    '',
    `YouTube URL: ${c.youtube_url || 'not set'}`,
    `YouTube key set: ${boolWord(c.youtube_key)}`,
    `Twitch URL: ${c.twitch_url || 'not set'}`,
    `Twitch key set: ${boolWord(c.twitch_key)}`,
    '',
    `OpenWeather key set: ${boolWord(c.openweather_key)}`,
  ].join('\n');
  setText('haConfigBox', box);
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
    setText('systemPill', data.system_enabled ? 'SYSTEM ON' : 'DISABLED');
    setText('testPill', data.mode === 'TEST_PATTERN' ? 'TEST PATTERN' : (data.local_test_mode ? 'LOCAL TEST ON' : 'EXTERNAL OUTPUTS OK'));

    const errs = [data.last_weather_error, data.last_ffmpeg_error].filter(Boolean).join(' | ');
    setText('errors', errs);

    setText('summaryLine', [
      `Preset: ${data.active_preset || '—'}`,
      `Offline: ${data.offline_seconds || 0}s`,
      summarizeDestinations(data)
    ].join(' · '));

    setModeClasses(data);
    updateConfigHints(data);

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
      `Mode: ${data.mode || '—'}`,
      `External outputs: ${data.local_test_mode || data.mode === 'TEST_PATTERN' ? 'blocked' : 'allowed if enabled and keys exist'}`
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

function applyTheme(theme) {
  document.body.classList.toggle('light', theme === 'light');
  setText('themeToggle', theme === 'light' ? 'Dark' : 'Light');
  localStorage.setItem('droneRelayTheme', theme);
}

document.getElementById('themeToggle')?.addEventListener('click', () => {
  const next = document.body.classList.contains('light') ? 'dark' : 'light';
  applyTheme(next);
});

applyTheme(localStorage.getItem('droneRelayTheme') || 'dark');
refreshStatus(true);
setInterval(() => refreshStatus(false), 3000);
