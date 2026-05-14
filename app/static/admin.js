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
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function post(path, body = {}) {
  return api(path, {method: "POST", body: JSON.stringify(body)});
}

function setText(id, val) {
  const el = qs("#" + id);
  if (el) el.textContent = val;
}

function setValClass(id, val, cls) {
  const el = qs("#" + id);
  if (!el) return;
  el.textContent = val;
  el.className = "val " + cls;
}

function renderToggle(btn, on) {
  btn.dataset.value = on ? "true" : "false";
  btn.textContent = on ? "ON" : "OFF";
  btn.classList.toggle("on", !!on);
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

function reloadPreviews() {
  qsa("iframe[data-preview]").forEach(frame => {
    const src = frame.dataset.src;
    frame.src = "about:blank";
    setTimeout(() => frame.src = src + (src.includes("?") ? "&" : "?") + "t=" + Date.now(), 150);
  });
}

async function refreshStatus() {
  const data = await api("/api/status");

  setValClass("mode", data.mode || "unknown", data.mode === "DISABLED" ? "bad" : "good");
  setValClass("rawInput", data.input_connected ? "online" : "offline", data.input_connected ? "good" : "warn");
  setValClass("program", data.program_connected ? "online" : "offline", data.program_connected ? "good" : "warn");
  setValClass("encoder", data.last_encoder || "none", data.last_encoder === "cpu" ? "warn" : "good");
  setValClass("system", data.settings.system_enabled ? "enabled" : "disabled", data.settings.system_enabled ? "good" : "bad");
  setText("weatherLine", data.weather_line || "No weather yet");

  setValClass("owmKey", data.env.openweather_key_present ? "set" : "missing", data.env.openweather_key_present ? "good" : "warn");
  setValClass("youtubeKey", data.env.youtube_key_present ? "set" : "missing", data.env.youtube_key_present ? "good" : "warn");
  setValClass("twitchKey", data.env.twitch_key_present ? "set" : "missing", data.env.twitch_key_present ? "good" : "warn");
  setValClass("scannerUrl", data.env.scanner_url_present ? "set" : "missing", data.env.scanner_url_present ? "good" : "warn");
  setValClass("azuracastUrl", data.env.azuracast_url_present ? "set" : "missing", data.env.azuracast_url_present ? "good" : "warn");

  Object.entries(data.settings).forEach(([key, val]) => {
    qsa(`[data-toggle="${key}"]`).forEach(btn => renderToggle(btn, !!val));
  });

  [
    "location_label", "fallback_zip", "manual_zip", "weather_refresh_seconds", "video_bitrate",
    "program_audio_volume", "drone_audio_volume", "mp3_volume", "brb_audio_volume",
    "brb_delay_seconds", "end_timeout_seconds"
  ].forEach(id => {
    const el = qs("#" + id);
    if (el && document.activeElement !== el && data.settings[id] !== undefined) {
      el.value = data.settings[id];
      const display = qs(`#${id}_display`);
      if (display) display.textContent = data.settings[id];
    }
  });

  ["program_audio_source"].forEach(id => {
    const el = qs("#" + id);
    if (el && document.activeElement !== el && data.settings[id] !== undefined) el.value = data.settings[id];
  });

  fillSelect("#active_audio", data.audio_files || [], data.settings.active_audio || "");
  fillSelect("#active_brb", data.brb_files || [], data.settings.active_brb || "");

  setUrls(data.urls);
}

async function saveSettings() {
  const data = {
    location_label: qs("#location_label").value,
    fallback_zip: qs("#fallback_zip").value,
    manual_zip: qs("#manual_zip").value,
    weather_refresh_seconds: Number(qs("#weather_refresh_seconds").value || 30),
    video_bitrate: qs("#video_bitrate").value,
    program_audio_source: qs("#program_audio_source").value,
    program_audio_volume: Number(qs("#program_audio_volume").value || 0.35),
    drone_audio_volume: Number(qs("#drone_audio_volume").value || 1),
    mp3_volume: Number(qs("#mp3_volume").value || 0.35),
    brb_audio_volume: Number(qs("#brb_audio_volume").value || 0.6),
    active_audio: qs("#active_audio").value,
    active_brb: qs("#active_brb").value,
    brb_delay_seconds: Number(qs("#brb_delay_seconds").value || 5),
    end_timeout_seconds: Number(qs("#end_timeout_seconds").value || 300)
  };

  await post("/api/settings", data);
  await refreshStatus();
  alert("Saved");
}

async function uploadFile(kind) {
  const input = qs(kind === "audio" ? "#upload_audio" : "#upload_brb");
  if (!input.files.length) return alert("Pick a file first.");

  const form = new FormData();
  form.append("file", input.files[0]);
  form.append("kind", kind);

  const res = await fetch("/api/upload", {method: "POST", body: form, credentials: "same-origin"});
  if (!res.ok) return alert(await res.text());

  await refreshStatus();
  alert("Uploaded");
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(getTheme());

  qs("#themeToggle").addEventListener("click", () => {
    applyTheme(getTheme() === "dark" ? "light" : "dark");
  });

  qsa("[data-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      const old = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Working...";
      try {
        await post(`/api/${action}`);
        await refreshStatus();
        if (["test-pattern", "test-brb", "test-audio", "start", "brb", "live"].includes(action)) {
          setTimeout(reloadPreviews, 1500);
        }
      } catch (e) {
        alert(e.message);
      } finally {
        btn.textContent = old;
        btn.disabled = false;
      }
    });
  });

  qsa("[data-toggle]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.toggle;
      const current = btn.dataset.value === "true";
      await post("/api/settings", {[key]: !current});
      await refreshStatus();
    });
  });

  qsa("input[type='range']").forEach(slider => {
    slider.addEventListener("input", () => {
      const display = qs(`#${slider.id}_display`);
      if (display) display.textContent = slider.value;
    });
  });

  qs("#saveSettings").addEventListener("click", () => saveSettings().catch(e => alert(e.message)));
  qs("#uploadAudioBtn").addEventListener("click", () => uploadFile("audio").catch(e => alert(e.message)));
  qs("#uploadBrbBtn").addEventListener("click", () => uploadFile("brb").catch(e => alert(e.message)));
  qs("#refreshWeatherBtn").addEventListener("click", async () => {
    await post("/api/weather/refresh");
    await refreshStatus();
  });
  qs("#reloadPreviews").addEventListener("click", reloadPreviews);

  reloadPreviews();
  refreshStatus().catch(console.error);
  setInterval(() => refreshStatus().catch(console.error), 3000);
});
