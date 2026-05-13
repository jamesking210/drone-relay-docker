import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from PIL import Image, ImageDraw, ImageFont
from werkzeug.utils import secure_filename

APP_DIR = Path("/app")
CONFIG_DIR = APP_DIR / "config"
MEDIA_DIR = APP_DIR / "media"
BRB_DIR = MEDIA_DIR / "brb"
AUDIO_DIR = MEDIA_DIR / "audio"
OVERLAY_DIR = APP_DIR / "overlay"
LOG_DIR = APP_DIR / "logs"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
SETTINGS_EXAMPLE = CONFIG_DIR / "settings.example.json"
WEATHER_PNG = OVERLAY_DIR / "weather.png"
WEATHER_JSON = OVERLAY_DIR / "weather.json"
LOG_FILE = LOG_DIR / "drone-relay.log"

PUBLIC_HOST = os.getenv("PUBLIC_HOST", "192.168.1.17")
ADMIN_PORT = os.getenv("ADMIN_PORT", "8589")
RTMP_PORT = os.getenv("RTMP_PORT", "19350")
HLS_PORT = os.getenv("HLS_PORT", "8888")
WEBRTC_PORT = os.getenv("WEBRTC_PORT", "8889")

INPUT_RTMP = os.getenv("INPUT_RTMP", "rtmp://mediamtx:1935/live/drone")
PROGRAM_RTMP = os.getenv("PROGRAM_RTMP", "rtmp://mediamtx:1935/live/program")

USERNAME = os.getenv("ADMIN_USERNAME", "admin")
PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
DRONE_API_TOKEN = os.getenv("DRONE_API_TOKEN", "")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
YOUTUBE_RTMP_URL = os.getenv("YOUTUBE_RTMP_URL", "rtmps://a.rtmps.youtube.com/live2")
YOUTUBE_STREAM_KEY = os.getenv("YOUTUBE_STREAM_KEY", "")
TWITCH_RTMP_URL = os.getenv("TWITCH_RTMP_URL", "rtmp://live.twitch.tv/app")
TWITCH_STREAM_KEY = os.getenv("TWITCH_STREAM_KEY", "")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me")

state_lock = threading.Lock()
ffmpeg_proc: subprocess.Popen | None = None
mode = "OFFLINE"
input_connected = False
last_input_seen = 0.0
weather_line = "Weather not loaded yet"


def log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_settings() -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_FILE.exists():
        if SETTINGS_EXAMPLE.exists():
            SETTINGS_FILE.write_text(SETTINGS_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            SETTINGS_FILE.write_text("{}", encoding="utf-8")
    return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))


def save_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    settings.update(patch)
    return save_settings(settings)


def env_status() -> Dict[str, bool]:
    return {
        "openweather_key_present": bool(OPENWEATHER_API_KEY),
        "youtube_key_present": bool(YOUTUBE_STREAM_KEY),
        "twitch_key_present": bool(TWITCH_STREAM_KEY),
        "ha_token_present": bool(os.getenv("HOME_ASSISTANT_TOKEN", "")),
    }


def urls() -> Dict[str, str]:
    return {
        "DJI Fly RTMP ingest": f"rtmp://{PUBLIC_HOST}:{RTMP_PORT}/live/drone",
        "Raw HLS preview": f"http://{PUBLIC_HOST}:{HLS_PORT}/live/drone/index.m3u8",
        "Program HLS output": f"http://{PUBLIC_HOST}:{HLS_PORT}/live/program/index.m3u8",
        "Raw WebRTC preview": f"http://{PUBLIC_HOST}:{WEBRTC_PORT}/live/drone",
        "Program WebRTC output": f"http://{PUBLIC_HOST}:{WEBRTC_PORT}/live/program",
        "Program RTMP output": f"rtmp://{PUBLIC_HOST}:{RTMP_PORT}/live/program",
        "Admin page": f"http://{PUBLIC_HOST}:{ADMIN_PORT}/admin",
    }


def list_files(folder: Path, exts: List[str]) -> List[str]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p.name)
    return sorted(out)


def require_login():
    if session.get("logged_in"):
        return None
    return redirect(url_for("login"))


@app.before_request
def guard():
    if request.path.startswith("/static") or request.path == "/login":
        return None
    if request.path.startswith("/api/"):
        token = request.headers.get("X-Drone-Token", "")
        if token and DRONE_API_TOKEN and token == DRONE_API_TOKEN:
            return None
        if session.get("logged_in"):
            return None
        return jsonify({"error": "unauthorized"}), 401
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == USERNAME and request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        return render_template("login.html", error="Bad login")
    return render_template("login.html")


@app.route("/")
def root():
    return redirect(url_for("admin"))


@app.route("/admin")
def admin():
    return render_template("admin.html")


def render_weather_png(line: str) -> None:
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    w, h = 1920, 52
    img = Image.new("RGBA", (w, h), (8, 12, 18, 222))
    draw = ImageDraw.Draw(img)

    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.rectangle((0, 0, w, h), fill=(9, 14, 22, 230))
    draw.rectangle((0, h - 3, w, h), fill=(66, 211, 146, 255))

    text = line or "Weather not loaded"
    max_text = text[:150]
    draw.text((18, 12), max_text, fill=(245, 248, 252, 255), font=font_big)
    img.save(WEATHER_PNG)


def refresh_weather() -> str:
    global weather_line
    settings = load_settings()

    if not settings.get("weather_enabled", True):
        weather_line = "Weather overlay disabled"
        render_weather_png("")
        return weather_line

    label = settings.get("location_label") or "DuPage County, IL"
    zip_code = (settings.get("manual_zip") or settings.get("fallback_zip") or "60148").strip()

    if not OPENWEATHER_API_KEY:
        weather_line = "OPENWEATHER API KEY NEEDED"
        render_weather_png(weather_line)
        return weather_line

    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "zip": f"{zip_code},US",
                "appid": OPENWEATHER_API_KEY,
                "units": "imperial",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        desc = data["weather"][0]["description"].upper()
        wind = round(data.get("wind", {}).get("speed", 0))
        gust = data.get("wind", {}).get("gust")
        vis_mi = data.get("visibility")
        parts = [
            label.upper(),
            f"{temp}°F",
            f"FEELS {feels}°",
            f"WIND {wind} MPH",
        ]
        if settings.get("show_gusts", True) and gust is not None:
            parts.append(f"GUSTS {round(gust)} MPH")
        if settings.get("show_visibility", True) and vis_mi is not None:
            parts.append(f"VIS {round(vis_mi / 1609.344)} MI")
        parts.append(desc)
        weather_line = "  |  ".join(parts)
        WEATHER_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        render_weather_png(weather_line)
        return weather_line

    except Exception as e:
        weather_line = f"WEATHER ERROR: {e}"
        render_weather_png(weather_line)
        return weather_line


def ensure_overlay() -> None:
    if not WEATHER_PNG.exists():
        refresh_weather()


def stop_ffmpeg() -> None:
    global ffmpeg_proc, mode
    with state_lock:
        proc = ffmpeg_proc
        ffmpeg_proc = None

    if proc and proc.poll() is None:
        log("Stopping FFmpeg")
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    with state_lock:
        if mode != "DISABLED":
            mode = "OFFLINE"


def output_targets(local_only: bool) -> str:
    targets = [f"[f=flv:onfail=ignore]{PROGRAM_RTMP}"]
    settings = load_settings()

    if not local_only and not settings.get("local_test_mode", True):
        if settings.get("youtube_enabled", False) and YOUTUBE_STREAM_KEY:
            targets.append(f"[f=flv:onfail=ignore]{YOUTUBE_RTMP_URL.rstrip('/')}/{YOUTUBE_STREAM_KEY}")
        if settings.get("twitch_enabled", False) and TWITCH_STREAM_KEY:
            targets.append(f"[f=flv:onfail=ignore]{TWITCH_RTMP_URL.rstrip('/')}/{TWITCH_STREAM_KEY}")

    return "|".join(targets)


def ffmpeg_base_encode_args(settings: Dict[str, Any], out: str) -> List[str]:
    bitrate = settings.get("video_bitrate", "6000k")
    audio_bitrate = settings.get("audio_bitrate", "160k")
    return [
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "h264_vaapi",
        "-b:v", bitrate,
        "-maxrate", bitrate,
        "-bufsize", "12000k",
        "-g", "60",
        "-r", "30",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", "44100",
        "-f", "tee",
        out,
    ]


def active_audio_path(settings: Dict[str, Any]) -> Path | None:
    name = settings.get("active_audio") or ""
    if not name:
        files = list_files(AUDIO_DIR, [".mp3"])
        name = files[0] if files else ""
    p = AUDIO_DIR / name
    return p if name and p.exists() else None


def active_brb_path(settings: Dict[str, Any]) -> Path | None:
    name = settings.get("active_brb") or ""
    if not name:
        files = list_files(BRB_DIR, [".mp4"])
        name = files[0] if files else ""
    p = BRB_DIR / name
    return p if name and p.exists() else None


def start_ffmpeg(kind: str) -> None:
    global ffmpeg_proc, mode
    settings = load_settings()

    if not settings.get("system_enabled", True):
        mode = "DISABLED"
        log("System disabled. Refusing to start FFmpeg.")
        return

    stop_ffmpeg()
    ensure_overlay()

    local_only = kind == "test_pattern"
    out = output_targets(local_only=local_only)

    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-vaapi_device", "/dev/dri/renderD128"]

    filter_complex = ""

    if kind == "test_pattern":
        cmd += ["-re", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30"]
        cmd += ["-loop", "1", "-i", str(WEATHER_PNG)]
        video_filter = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2[base];"
            "[base][1:v]overlay=0:0,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "text='%{localtime\\:%I\\\\:%M\\\\:%S %p}':x=w-tw-24:y=12:"
            "fontcolor=white:fontsize=24:box=1:boxcolor=black@0.35,"
            "format=nv12,hwupload[vout]"
        )
        audio_index = 2
    elif kind == "brb":
        brb = active_brb_path(settings)
        if brb:
            cmd += ["-stream_loop", "-1", "-re", "-i", str(brb)]
        else:
            cmd += ["-re", "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30"]
        video_filter = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "format=nv12,hwupload[vout]"
        )
        audio_index = 1
    else:
        cmd += ["-i", INPUT_RTMP]
        cmd += ["-loop", "1", "-i", str(WEATHER_PNG)]
        video_filter = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2[base];"
            "[base][1:v]overlay=0:0,"
            "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            "text='%{localtime\\:%I\\\\:%M\\\\:%S %p}':x=w-tw-24:y=12:"
            "fontcolor=white:fontsize=24:box=1:boxcolor=black@0.35,"
            "format=nv12,hwupload[vout]"
        )
        audio_index = 2

    audio = active_audio_path(settings) if settings.get("mp3_enabled", True) else None
    if audio:
        cmd += ["-stream_loop", "-1", "-i", str(audio)]
        volume = float(settings.get("mp3_volume", 0.35))
        audio_filter = f"[{audio_index}:a]volume={volume},aresample=44100[aout]"
    elif kind != "test_pattern" and settings.get("drone_audio_enabled", False):
        # Use drone/BRB audio if present; this can fail if no audio exists, so default is off.
        audio_filter = "[0:a]aresample=44100[aout]"
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        audio_filter = f"[{audio_index}:a]aresample=44100[aout]"

    filter_complex = video_filter + ";" + audio_filter

    cmd += [
        "-filter_complex", filter_complex,
        *ffmpeg_base_encode_args(settings, out)
    ]

    log("Starting FFmpeg: " + " ".join(cmd))
    logfile = (LOG_DIR / "ffmpeg.log").open("ab")
    proc = subprocess.Popen(cmd, stdout=logfile, stderr=logfile)

    with state_lock:
        ffmpeg_proc = proc
        mode = {
            "test_pattern": "TEST_PATTERN",
            "brb": "BRB",
            "live": "LIVE"
        }.get(kind, "LIVE")


def mediamtx_input_connected() -> bool:
    # Keep this simple: if the raw path responds on HLS/RTMP may not be ready.
    # For now return False unless MediaMTX API later adds a path reader check.
    try:
        r = requests.get(os.getenv("MEDIAMTX_API", "http://mediamtx:9997") + "/v3/paths/list", timeout=2)
        if r.ok:
            text = r.text
            return "live/drone" in text and "ready" in text.lower()
    except Exception:
        pass
    return False


def watchdog_loop():
    global input_connected, last_input_seen
    while True:
        try:
            refresh_weather()
        except Exception as e:
            log(f"Weather refresh failed: {e}")
        time.sleep(max(15, int(load_settings().get("weather_refresh_seconds", 30))))


@app.route("/api/status")
def api_status():
    global input_connected
    settings = load_settings()
    input_connected = mediamtx_input_connected()
    return jsonify({
        "mode": mode,
        "input_connected": input_connected,
        "offline_seconds": 0,
        "settings": settings,
        "env": env_status(),
        "weather_line": weather_line,
        "urls": urls(),
        "audio_files": list_files(AUDIO_DIR, [".mp3"]),
        "brb_files": list_files(BRB_DIR, [".mp4"]),
    })


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.get_json(force=True) or {}
    allowed = set(load_settings().keys())
    patch = {k: v for k, v in data.items() if k in allowed}
    s = update_settings(patch)
    return jsonify({"ok": True, "settings": s})


@app.route("/api/weather/refresh", methods=["POST"])
def api_weather_refresh():
    line = refresh_weather()
    return jsonify({"ok": True, "weather_line": line})


@app.route("/api/start", methods=["POST"])
def api_start():
    start_ffmpeg("live")
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/test-pattern", methods=["POST"])
def api_test_pattern():
    update_settings({"local_test_mode": True, "active_preset": "test_pattern"})
    start_ffmpeg("test_pattern")
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/brb", methods=["POST"])
def api_brb():
    start_ffmpeg("brb")
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/live", methods=["POST"])
def api_live():
    start_ffmpeg("live")
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/stay-live", methods=["POST"])
def api_stay_live():
    return jsonify({"ok": True, "message": "BRB timer extension placeholder"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_ffmpeg()
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/disable-all", methods=["POST"])
def api_disable_all():
    global mode
    update_settings({"system_enabled": False})
    stop_ffmpeg()
    mode = "DISABLED"
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/enable-system", methods=["POST"])
def api_enable_system():
    global mode
    update_settings({"system_enabled": True})
    if mode == "DISABLED":
        mode = "OFFLINE"
    return jsonify({"ok": True, "mode": mode})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    kind = request.form.get("kind")
    f = request.files.get("file")
    if not f:
        return "missing file", 400

    filename = secure_filename(f.filename or "")
    if not filename:
        return "bad filename", 400

    if kind == "audio":
        if not filename.lower().endswith(".mp3"):
            return "MP3 only", 400
        target = AUDIO_DIR / filename
    elif kind == "brb":
        if not filename.lower().endswith(".mp4"):
            return "MP4 only", 400
        target = BRB_DIR / filename
    else:
        return "bad kind", 400

    target.parent.mkdir(parents=True, exist_ok=True)
    f.save(target)
    return jsonify({"ok": True, "file": filename})


# Login template fallback files are not loaded from route, but included separately.
if __name__ == "__main__":
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    BRB_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        refresh_weather()
    except Exception as e:
        log(f"Initial weather failed: {e}")
        render_weather_png("Weather not loaded")

    threading.Thread(target=watchdog_loop, daemon=True).start()

    app.run(host="0.0.0.0", port=8080)
