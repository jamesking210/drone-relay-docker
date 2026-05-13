let statusTimer = null;

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return [...document.querySelectorAll(sel)]; }

function getTheme() {
  return localStorage.getItem("droneRelayTheme") || "light";
}

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("droneRelayTheme", theme);
  const btn = qs("#themeToggle");
  if (btn) btn.textContent = theme === "dark" ? "Light" : "Dark";
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    ...opts
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json();
}

async function post(path, body = {}) {
  return api(path, {method: "POST", body: JSON.stringify(body)});
}

function setText(id, val) {
  const el = qs(`#${id}`);
  if (el) el.textContent = val;
}

function setClass(id, cls) {
  const el = qs(`#${id}`);
  if (!el) return;
  el.className = "val " + cls;
}

function pct(v) {
  return `${Math.round(Number(v || 0) * 100)}%`;
}

function bindActionButtons() {
  qsa("[data-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      btn.disabled = true;
      const old = btn.textContent;
      btn.textContent = "Working...";
      try {
        await post(`/api/${action}`);
        await refreshStatus();
      } catch (e) {
        alert(e.message);
      } finally {
        btn.textContent = old;
        btn.disabled = false;
      }
    });
  });
}

function bindToggleButtons() {
  qsa("[data-toggle]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.toggle;
      const current = btn.dataset.value === "true";
      try {
        await post("/api/settings", {[key]: !current});
        await refreshStatus();
      } catch (e) {
        alert(e.message);
      }
    });
  });
}

function bindSliders() {
  const mp3 = qs("#mp3_volume");
  const drone = qs("#drone_volume");
  const brb = qs("#brb_volume");
  if (mp3) mp3.addEventListener("input", () => setText("mp3VolumeLabel", pct(mp3.value)));
  if (drone) drone.addEventListener("input", () => setText("droneVolumeLabel", pct(drone.value)));
  if (brb) brb.addEventListener("input", () => setText("brbVolumeLabel", pct(brb.value)));
}

function renderToggle(btn, on) {
  btn.dataset.value = on ? "true" : "false";
  btn.textContent = on ? "ON" : "OFF";
  btn.classList.toggle("on", !!on);
}

async function saveSettings() {
  const data = {
    location_label: qs("#location_label").value,
    fallback_zip: qs("#fallback_zip").value,
    manual_zip: qs("#manual_zip").value,
    video_bitrate: qs("#video_bitrate").value,
    brb_delay_seconds: Number(qs("#brb_delay_seconds").value || 5),
    end_timeout_seconds: Number(qs("#end_timeout_seconds").value || 300),
    mp3_volume: Number(qs("#mp3_volume").value || 0.35),
    drone_volume: Number(qs("#drone_volume").value || 1),
    brb_volume: Number(qs("#brb_volume").value || 1),
    active_audio: qs("#active_audio").value,
    active_brb: qs("#active_brb").value
  };
  try {
    await post("/api/settings", data);
    await refreshStatus();
    alert("Saved");
  } catch (e) {
    alert(e.message);
  }
}

async function uploadFile(kind) {
  const input = qs(kind === "audio" ? "#upload_audio" : "#upload_brb");
  if (!input.files.length) return alert("Pick a file first.");

  const form = new FormData();
  form.append("file", input.files[0]);
  form.append("kind", kind);

  const res = await fetch("/api/upload", {
    method: "POST",
    body: form,
    credentials: "same-origin"
  });

  if (!res.ok) {
    alert(await res.text());
    return;
  }

  input.value = "";
  await refreshStatus();
  alert("Uploaded");
}

async function refreshWeather() {
  try {
    await post("/api/weather/refresh");
    await refreshStatus();
  } catch (e) {
    alert(e.message);
  }
}

async function refreshStatus() {
  const data = await api("/api/status");

  setText("mode", data.mode || "unknown");
  setText("input", data.input_connected ? "connected" : "missing");
  setClass("input", data.input_connected ? "good" : "warn");
  setText("system", data.settings.system_enabled ? "enabled" : "disabled");
  setClass("system", data.settings.system_enabled ? "good" : "bad");
  setText("preset", data.settings.active_preset || "custom");
  setText("weatherLine", data.weather_line || "No weather line yet");

  setText("youtubeKey", data.env.youtube_key_present ? "key set" : "no key");
  setClass("youtubeKey", data.env.youtube_key_present ? "good" : "warn");
  setText("twitchKey", data.env.twitch_key_present ? "key set" : "no key");
  setClass("twitchKey", data.env.twitch_key_present ? "good" : "warn");
  setText("owmKey", data.env.openweather_key_present ? "key set" : "no key");
  setClass("owmKey", data.env.openweather_key_present ? "good" : "warn");

  Object.entries(data.settings).forEach(([key, val]) => {
    qsa(`[data-toggle="${key}"]`).forEach(btn => renderToggle(btn, !!val));
  });

  ["location_label", "fallback_zip", "manual_zip", "video_bitrate", "brb_delay_seconds", "end_timeout_seconds"].forEach(id => {
    const el = qs(`#${id}`);
    if (el && document.activeElement !== el && data.settings[id] !== undefined) el.value = data.settings[id];
  });

  const mp3 = qs("#mp3_volume");
  if (mp3 && document.activeElement !== mp3) mp3.value = data.settings.mp3_volume ?? 0.35;
  setText("mp3VolumeLabel", pct(mp3 ? mp3.value : data.settings.mp3_volume));

  const drone = qs("#drone_volume");
  if (drone && document.activeElement !== drone) drone.value = data.settings.drone_volume ?? 1;
  setText("droneVolumeLabel", pct(drone ? drone.value : data.settings.drone_volume));

  const brb = qs("#brb_volume");
  if (brb && document.activeElement !== brb) brb.value = data.settings.brb_volume ?? 1;
  setText("brbVolumeLabel", pct(brb ? brb.value : data.settings.brb_volume));

  fillSelect("#active_audio", data.audio_files || [], data.settings.active_audio || "");
  fillSelect("#active_brb", data.brb_files || [], data.settings.active_brb || "");
  setUrls(data.urls);
}

function fillSelect(sel, items, active) {
  const el = qs(sel);
  if (!el) return;
  const old = el.value;
  el.innerHTML = `<option value="">None selected</option>` + items.map(x => `<option value="${x}">${x}</option>`).join("");
  el.value = active || old || "";
}

function setUrls(urls) {
  const list = qs("#urlList");
  if (!list || !urls) return;
  list.innerHTML = Object.entries(urls).map(([name, url]) => `
    <div class="url-item">
      <div class="title">${name}</div>
      <code>${url}</code>
    </div>
  `).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getTheme());

  qs("#themeToggle").addEventListener("click", () => {
    applyTheme(getTheme() === "dark" ? "light" : "dark");
  });

  bindActionButtons();
  bindToggleButtons();
  bindSliders();

  qs("#saveSettings").addEventListener("click", saveSettings);
  qs("#uploadAudioBtn").addEventListener("click", () => uploadFile("audio"));
  qs("#uploadBrbBtn").addEventListener("click", () => uploadFile("brb"));
  qs("#refreshWeatherBtn").addEventListener("click", refreshWeather);

  refreshStatus().catch(console.error);
  statusTimer = setInterval(() => refreshStatus().catch(console.error), 3000);
});
