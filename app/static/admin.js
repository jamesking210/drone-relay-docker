let statusTimer = null;
function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return [...document.querySelectorAll(sel)]; }
function getTheme() { return localStorage.getItem("droneRelayTheme") || "light"; }
function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("droneRelayTheme", theme);
  const btn = qs("#themeToggle");
  if (btn) btn.textContent = theme === "dark" ? "Light" : "Dark";
}
async function api(path, opts = {}) {
  const res = await fetch(path, {credentials: "same-origin", headers: {"Content-Type":"application/json"}, ...opts});
  if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);
  return res.json();
}
async function post(path, body = {}) { return api(path, {method:"POST", body: JSON.stringify(body)}); }
function setText(id, val) { const el = qs(`#${id}`); if (el) el.textContent = val; }
function setClass(id, cls) { const el = qs(`#${id}`); if (el) el.className = "val " + cls; }
function pct(v) { return `${Math.round(Number(v || 0) * 100)}%`; }
function bindActionButtons() {
  qsa("[data-action]").forEach(btn => btn.addEventListener("click", async () => {
    const action = btn.dataset.action;
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = "Working...";
    try { await post(`/api/${action}`); await refreshStatus(); setTimeout(reloadPreviews, 800); }
    catch (e) { alert(e.message); }
    finally { btn.textContent = old; btn.disabled = false; }
  }));
}
function bindToggleButtons() {
  qsa("[data-toggle]").forEach(btn => btn.addEventListener("click", async () => {
    const key = btn.dataset.toggle;
    const current = btn.dataset.value === "true";
    try { await post("/api/settings", {[key]: !current}); await refreshStatus(); }
    catch (e) { alert(e.message); }
  }));
}
function bindSliders() {
  const program = qs("#program_audio_volume");
  const brb = qs("#brb_volume");
  if (program) program.addEventListener("input", () => setText("programVolumeLabel", pct(program.value)));
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
    program_audio_source: qs("#program_audio_source").value,
    program_audio_volume: Number(qs("#program_audio_volume").value || 0.35),
    mp3_volume: Number(qs("#program_audio_volume").value || 0.35),
    scanner_volume: Number(qs("#program_audio_volume").value || 0.35),
    azuracast_volume: Number(qs("#program_audio_volume").value || 0.35),
    brb_volume: Number(qs("#brb_volume").value || 1),
    active_audio: qs("#active_audio").value,
    active_brb: qs("#active_brb").value
  };
  try { await post("/api/settings", data); await refreshStatus(); alert("Saved"); }
  catch (e) { alert(e.message); }
}
async function uploadFile(kind) {
  const input = qs(kind === "audio" ? "#upload_audio" : "#upload_brb");
  if (!input.files.length) return alert("Pick a file first.");
  const form = new FormData();
  form.append("file", input.files[0]);
  form.append("kind", kind);
  const res = await fetch("/api/upload", {method:"POST", body: form, credentials:"same-origin"});
  if (!res.ok) return alert(await res.text());
  input.value = "";
  await refreshStatus();
  alert("Uploaded");
}
async function refreshWeather() {
  try { await post("/api/weather/refresh"); await refreshStatus(); }
  catch (e) { alert(e.message); }
}
function fillSelect(sel, items, active) {
  const el = qs(sel); if (!el) return;
  const old = el.value;
  el.innerHTML = `<option value="">None selected</option>` + items.map(x => `<option value="${x}">${x}</option>`).join("");
  el.value = active || old || "";
}
function setUrls(urls) {
  const list = qs("#urlList"); if (!list || !urls) return;
  list.innerHTML = Object.entries(urls).map(([name, url]) => `
    <div class="url-item"><div class="title">${name}</div><code>${url}</code></div>
  `).join("");
}
function reloadPreviews() {
  const stamp = Date.now();
  const program = qs("#programFrame");
  const raw = qs("#rawFrame");
  if (program) program.src = `http://192.168.1.17:8889/live/program?reload=${stamp}`;
  if (raw) raw.src = `http://192.168.1.17:8889/live/drone?reload=${stamp}`;
}
async function refreshStatus() {
  const data = await api("/api/status");
  setText("mode", data.mode || "unknown");
  setText("input", data.input_connected ? "connected" : "missing");
  setClass("input", data.input_connected ? "good" : "warn");
  setText("system", data.settings.system_enabled ? "enabled" : "disabled");
  setClass("system", data.settings.system_enabled ? "good" : "bad");
  setText("audioSourceStat", data.settings.program_audio_source || "mp3");
  setText("weatherLine", data.weather_line || "No weather line yet");
  setText("owmKey", data.env.openweather_key_present ? "key set" : "no key");
  setClass("owmKey", data.env.openweather_key_present ? "good" : "warn");
  setText("scannerKey", data.env.scanner_url_present ? "set" : "blank");
  setClass("scannerKey", data.env.scanner_url_present ? "good" : "warn");
  setText("azuraKey", data.env.azuracast_url_present ? "set" : "blank");
  setClass("azuraKey", data.env.azuracast_url_present ? "good" : "warn");
  Object.entries(data.settings).forEach(([key, val]) => qsa(`[data-toggle="${key}"]`).forEach(btn => renderToggle(btn, !!val)));
  ["location_label","fallback_zip","manual_zip","video_bitrate","brb_delay_seconds","end_timeout_seconds"].forEach(id => {
    const el = qs(`#${id}`); if (el && document.activeElement !== el && data.settings[id] !== undefined) el.value = data.settings[id];
  });
  const src = qs("#program_audio_source");
  if (src && document.activeElement !== src) src.value = data.settings.program_audio_source || "mp3";
  const program = qs("#program_audio_volume");
  if (program && document.activeElement !== program) program.value = data.settings.program_audio_volume ?? data.settings.mp3_volume ?? 0.35;
  setText("programVolumeLabel", pct(program ? program.value : data.settings.program_audio_volume));
  const brb = qs("#brb_volume");
  if (brb && document.activeElement !== brb) brb.value = data.settings.brb_volume ?? 1;
  setText("brbVolumeLabel", pct(brb ? brb.value : data.settings.brb_volume));
  fillSelect("#active_audio", data.audio_files || [], data.settings.active_audio || "");
  fillSelect("#active_brb", data.brb_files || [], data.settings.active_brb || "");
  setUrls(data.urls);
}
document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getTheme());
  qs("#themeToggle").addEventListener("click", () => applyTheme(getTheme() === "dark" ? "light" : "dark"));
  bindActionButtons(); bindToggleButtons(); bindSliders();
  qs("#saveSettings").addEventListener("click", saveSettings);
  qs("#uploadAudioBtn").addEventListener("click", () => uploadFile("audio"));
  qs("#uploadBrbBtn").addEventListener("click", () => uploadFile("brb"));
  qs("#refreshWeatherBtn").addEventListener("click", refreshWeather);
  qs("#reloadPreviews").addEventListener("click", reloadPreviews);
  refreshStatus().catch(console.error);
  statusTimer = setInterval(() => refreshStatus().catch(console.error), 3000);
});
