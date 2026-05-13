import json
import os
import re
import shlex
import signal
import subprocess
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

BASE = Path('/app')
CONFIG_DIR = BASE / 'config'
MEDIA_DIR = BASE / 'media'
BRB_DIR = MEDIA_DIR / 'brb'
AUDIO_DIR = MEDIA_DIR / 'audio'
OVERLAY_DIR = BASE / 'overlay'
LOG_DIR = BASE / 'logs'
SETTINGS_PATH = CONFIG_DIR / 'settings.json'
DEFAULT_SETTINGS_PATH = CONFIG_DIR / 'settings.example.json'
WEATHER_TEXT_PATH = OVERLAY_DIR / 'weather.txt'
STATUS_PATH = LOG_DIR / 'status.json'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REGULAR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

for directory in [CONFIG_DIR, BRB_DIR, AUDIO_DIR, OVERLAY_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-me')

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'change-me-now')
API_TOKEN = os.environ.get('DRONE_API_TOKEN', 'change-this-api-token')
TZ_NAME = os.environ.get('TZ', 'America/Chicago')
INPUT_RTMP = os.environ.get('INPUT_RTMP', 'rtmp://mediamtx:1935/live/drone')
PROGRAM_RTMP = os.environ.get('PROGRAM_RTMP', 'rtmp://mediamtx:1935/live/program')
MEDIAMTX_API = os.environ.get('MEDIAMTX_API', 'http://mediamtx:9997')

# V3: secrets and service URLs live in .env, not in the admin page.
OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY', '').strip()
YOUTUBE_RTMP_URL = os.environ.get('YOUTUBE_RTMP_URL', 'rtmps://a.rtmps.youtube.com/live2').strip().rstrip('/')
YOUTUBE_STREAM_KEY = os.environ.get('YOUTUBE_STREAM_KEY', '').strip()
TWITCH_RTMP_URL = os.environ.get('TWITCH_RTMP_URL', 'rtmp://live.twitch.tv/app').strip().rstrip('/')
TWITCH_STREAM_KEY = os.environ.get('TWITCH_STREAM_KEY', '').strip()
HA_URL = os.environ.get('HOME_ASSISTANT_URL', 'http://192.168.1.3:8123').strip().rstrip('/')
HA_TOKEN = os.environ.get('HOME_ASSISTANT_TOKEN', '').strip()
HA_PHONE_ENTITY = os.environ.get('HA_PHONE_ENTITY', 'device_tracker.s24').strip()
HA_ZIP_OVERRIDE_ENTITY = os.environ.get('HA_ZIP_OVERRIDE_ENTITY', 'input_text.drone_overlay_zip').strip()
HA_NOTIFY_SERVICE = os.environ.get('HA_NOTIFY_SERVICE', 'notify.mobile_app_s24').strip()

SECRET_KEYS = {'openweather_api_key', 'token', 'youtube_stream_key', 'twitch_stream_key'}

DEFAULT_SETTINGS = {
    'system': {'enabled': True, 'local_test_mode': False},
    'streaming': False,
    'mode': 'OFFLINE',
    'active_preset': 'good_signal',
    'output': {'width': 1920, 'height': 1080, 'fps': 30, 'video_bitrate': '6500k', 'audio_bitrate': '160k', 'encoder': 'h264_vaapi'},
    'destinations': {
        'youtube_enabled': True,
        'twitch_enabled': False,
    },
    'ingest': {'public_url_hint': 'rtmp://192.168.1.17:19350/live/drone', 'tailscale_url_hint': ''},
    'weather': {
        'enabled': True,
        'units': 'imperial',
        'refresh_seconds': 30,
        'location_mode': 'fallback_zip',
        'fallback_zip': '60148',
        'fallback_country': 'US',
        'manual_zip': '',
        'manual_zip_enabled': False,
        'display_label': 'DuPage County, IL',
        'clock_timezone': 'America/Chicago',
        'show_gusts': True,
        'show_visibility': True,
    },
    'home_assistant': {
        'enabled': False,
        'notifications_enabled': False,
    },
    'audio': {'drone_audio_enabled': False, 'mp3_enabled': True, 'mp3_volume': 0.35, 'active_mp3': ''},
    'brb': {'active_mp4': '', 'delay_seconds': 5, 'end_timeout_seconds': 300, 'auto_return_live': True},
}

PRESETS = {
    'good_signal': {
        'label': 'Good Signal',
        'output': {'video_bitrate': '7000k'},
        'audio': {'mp3_enabled': True, 'mp3_volume': 0.35, 'drone_audio_enabled': False},
        'brb': {'delay_seconds': 5, 'end_timeout_seconds': 300},
    },
    'low_signal': {
        'label': 'Low Signal',
        'output': {'video_bitrate': '4500k'},
        'audio': {'mp3_enabled': True, 'mp3_volume': 0.25, 'drone_audio_enabled': False},
        'brb': {'delay_seconds': 5, 'end_timeout_seconds': 420},
    },
    'silent': {
        'label': 'Silent Stream',
        'audio': {'mp3_enabled': False, 'drone_audio_enabled': False},
    },
    'music': {
        'label': 'Music Stream',
        'audio': {'mp3_enabled': True, 'mp3_volume': 0.35, 'drone_audio_enabled': False},
    },
    'windy_day': {
        'label': 'Windy Day',
        'output': {'video_bitrate': '6000k'},
        'audio': {'mp3_enabled': True, 'mp3_volume': 0.25, 'drone_audio_enabled': False},
        'weather': {'show_gusts': True, 'show_visibility': True},
    },
    'test_mode': {
        'label': 'Local Test Mode',
        'system': {'local_test_mode': True},
        'streaming': False,
        'audio': {'mp3_enabled': False, 'drone_audio_enabled': False},
    },
}

state_lock = threading.RLock()
settings_lock = threading.RLock()
ffmpeg_proc: Optional[subprocess.Popen] = None
current_process_kind = 'OFFLINE'
last_source_seen: Optional[float] = None
source_missing_since: Optional[float] = None
brb_started_at: Optional[float] = None
end_deadline: Optional[float] = None
last_brb_notification_at: Optional[float] = None
last_timeout_notification_at: Optional[float] = None
last_weather_refresh = 0.0
last_weather_error = ''
last_weather_line = 'WEATHER WAITING FOR CONFIG'
last_weather_data: Dict[str, Any] = {}
last_ffmpeg_error = ''
status = {
    'mode': 'OFFLINE',
    'input_connected': False,
    'streaming_requested': False,
    'ffmpeg_running': False,
    'process_kind': 'OFFLINE',
    'offline_seconds': 0,
    'auto_end_seconds_remaining': None,
    'last_weather_line': last_weather_line,
    'last_weather_error': '',
    'last_ffmpeg_error': '',
    'active_preset': 'good_signal',
    'updated_at': '',
}


def deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_settings() -> Dict[str, Any]:
    with settings_lock:
        if not SETTINGS_PATH.exists():
            if DEFAULT_SETTINGS_PATH.exists():
                data = json.loads(DEFAULT_SETTINGS_PATH.read_text())
            else:
                data = deepcopy(DEFAULT_SETTINGS)
            SETTINGS_PATH.write_text(json.dumps(data, indent=2))
        try:
            raw = json.loads(SETTINGS_PATH.read_text())
        except Exception:
            raw = deepcopy(DEFAULT_SETTINGS)
        merged = deep_merge(deepcopy(DEFAULT_SETTINGS), raw)
        return merged


def save_settings(settings: Dict[str, Any]) -> None:
    with settings_lock:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2))


def sanitize_settings(obj: Any) -> Any:
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in SECRET_KEYS and value:
                result[key] = '********'
            else:
                result[key] = sanitize_settings(value)
        return result
    if isinstance(obj, list):
        return [sanitize_settings(x) for x in obj]
    return obj


def merge_posted_settings(current: Dict[str, Any], posted: Dict[str, Any]) -> Dict[str, Any]:
    def merge(cur: Dict[str, Any], new: Dict[str, Any]):
        for k, v in new.items():
            if isinstance(v, dict) and isinstance(cur.get(k), dict):
                merge(cur[k], v)
            else:
                if k in SECRET_KEYS and (v == '' or v == '********'):
                    continue
                cur[k] = v
    merged = deepcopy(current)
    merge(merged, posted)
    return merged


def allowed_file(filename: str, extensions: set[str]) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensions


def list_media() -> Dict[str, Any]:
    return {
        'brb': sorted([p.name for p in BRB_DIR.iterdir() if p.is_file() and p.suffix.lower() == '.mp4']),
        'audio': sorted([p.name for p in AUDIO_DIR.iterdir() if p.is_file() and p.suffix.lower() == '.mp3']),
    }


def login_ok() -> bool:
    return bool(session.get('logged_in'))


def api_ok() -> bool:
    header_token = request.headers.get('X-Drone-Token') or request.headers.get('Authorization', '').replace('Bearer ', '')
    return login_ok() or (API_TOKEN and header_token == API_TOKEN)


def require_api():
    if not api_ok():
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    return None


def write_weather_line(line: str):
    WEATHER_TEXT_PATH.write_text(line[:170] + '\n')


def shell_quote_list(cmd: list[str]) -> str:
    return ' '.join(shlex.quote(x) for x in cmd)


def log_line(name: str, line: str):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with (LOG_DIR / name).open('a', encoding='utf-8') as fh:
        fh.write(f'[{ts}] {line}\n')


def ffprobe_input(url: str, timeout: int = 4) -> bool:
    cmd = [
        'ffprobe', '-v', 'error', '-rw_timeout', '3000000',
        '-show_entries', 'stream=index', '-of', 'csv=p=0', url
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def ffprobe_has_audio(url: str, timeout: int = 5) -> bool:
    cmd = [
        'ffprobe', '-v', 'error', '-rw_timeout', '4000000',
        '-select_streams', 'a:0', '-show_entries', 'stream=codec_type',
        '-of', 'csv=p=0', url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode == 0 and 'audio' in proc.stdout
    except Exception:
        return False


def output_urls(settings: Dict[str, Any], local_only: bool = False) -> list[str]:
    # Always publish the final program back into MediaMTX for local preview.
    # Local Test Mode and Test Pattern Mode stop here and do NOT push to YouTube/Twitch.
    outs = [PROGRAM_RTMP]
    system = settings.get('system', {})
    if local_only or system.get('local_test_mode'):
        return outs

    dest = settings.get('destinations', {})
    if dest.get('youtube_enabled') and YOUTUBE_STREAM_KEY:
        outs.append(YOUTUBE_RTMP_URL + '/' + YOUTUBE_STREAM_KEY)
    if dest.get('twitch_enabled') and TWITCH_STREAM_KEY:
        outs.append(TWITCH_RTMP_URL + '/' + TWITCH_STREAM_KEY)
    return outs


def destination_summary(settings: Dict[str, Any]) -> Dict[str, Any]:
    system = settings.get('system', {})
    dest = settings.get('destinations', {})
    youtube_active = bool(dest.get('youtube_enabled') and YOUTUBE_STREAM_KEY)
    twitch_active = bool(dest.get('twitch_enabled') and TWITCH_STREAM_KEY)
    return {
        'system_enabled': bool(system.get('enabled', True)),
        'local_test_mode': bool(system.get('local_test_mode')),
        'youtube_enabled': bool(dest.get('youtube_enabled')),
        'youtube_ready': bool(YOUTUBE_STREAM_KEY),
        'twitch_enabled': bool(dest.get('twitch_enabled')),
        'twitch_ready': bool(TWITCH_STREAM_KEY),
        'openweather_ready': bool(OPENWEATHER_API_KEY),
        'home_assistant_ready': bool(HA_URL and HA_TOKEN),
        'external_outputs_active': bool(not system.get('local_test_mode') and (youtube_active or twitch_active)),
    }


def build_tee_arg(settings: Dict[str, Any], local_only: bool = False) -> str:
    parts = []
    for url in output_urls(settings, local_only=local_only):
        escaped = url.replace('|', '%7C')
        parts.append(f'[f=flv:onfail=ignore]{escaped}')
    return '|'.join(parts)


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def start_process(kind: str, cmd: list[str]):
    global ffmpeg_proc, current_process_kind, last_ffmpeg_error
    stop_ffmpeg()
    log_line('ffmpeg.log', f'START {kind}: {shell_quote_list(cmd)}')
    err_file = (LOG_DIR / 'ffmpeg-current.log').open('w', encoding='utf-8')
    try:
        env = os.environ.copy()
        try:
            env['TZ'] = load_settings().get('weather', {}).get('clock_timezone') or TZ_NAME
        except Exception:
            env['TZ'] = TZ_NAME
        ffmpeg_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_file, preexec_fn=os.setsid, env=env)
        current_process_kind = kind
        last_ffmpeg_error = ''
    except Exception as exc:
        last_ffmpeg_error = str(exc)
        log_line('ffmpeg.log', f'FAILED {kind}: {exc}')
        try:
            err_file.close()
        except Exception:
            pass


def stop_ffmpeg():
    global ffmpeg_proc, current_process_kind
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        try:
            os.killpg(os.getpgid(ffmpeg_proc.pid), signal.SIGTERM)
            ffmpeg_proc.wait(timeout=6)
        except Exception:
            try:
                os.killpg(os.getpgid(ffmpeg_proc.pid), signal.SIGKILL)
            except Exception:
                pass
    ffmpeg_proc = None
    current_process_kind = 'OFFLINE'


def common_video_filter(settings: Dict[str, Any], with_overlay: bool) -> str:
    out = settings.get('output', {})
    width = safe_int(out.get('width'), 1920)
    height = safe_int(out.get('height'), 1080)
    fps = safe_int(out.get('fps'), 30)
    base = (
        f'[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,'
        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    )
    if with_overlay:
        # Weather text reloads from disk, clock is live. Keep the clock on the right side.
        base += (
            ",drawbox=x=0:y=0:w=iw:h=52:color=black@0.68:t=fill"
            f",drawtext=fontfile={FONT_BOLD}:textfile={WEATHER_TEXT_PATH}:reload=1:x=18:y=13:fontcolor=white:fontsize=26"
            f",drawtext=fontfile={FONT_BOLD}:text='%{{localtime\\:%I\\\\:%M\\\\:%S %p}}':x=w-tw-18:y=13:fontcolor=white:fontsize=26"
        )
    base += ',format=nv12,hwupload[v]'
    return base


def build_live_cmd(settings: Dict[str, Any]) -> list[str]:
    out = settings.get('output', {})
    audio = settings.get('audio', {})
    video_bitrate = out.get('video_bitrate', '6500k')
    audio_bitrate = out.get('audio_bitrate', '160k')
    fps = safe_int(out.get('fps'), 30)
    mp3_enabled = bool(audio.get('mp3_enabled')) and bool(audio.get('active_mp3'))
    drone_audio_enabled = bool(audio.get('drone_audio_enabled'))
    mp3_path = AUDIO_DIR / audio.get('active_mp3', '')
    has_drone_audio = drone_audio_enabled and ffprobe_has_audio(INPUT_RTMP)

    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '2']
    cmd += ['-i', INPUT_RTMP]
    input_index = 1
    mp3_index = None
    silence_index = None
    if mp3_enabled and mp3_path.exists():
        cmd += ['-stream_loop', '-1', '-i', str(mp3_path)]
        mp3_index = input_index
        input_index += 1
    if not mp3_enabled and not has_drone_audio:
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        silence_index = input_index
        input_index += 1

    filters = [common_video_filter(settings, with_overlay=True)]
    map_audio = None
    if mp3_index is not None and has_drone_audio:
        vol = safe_float(audio.get('mp3_volume'), 0.35)
        filters.append(f'[0:a]volume=1.0[a0];[{mp3_index}:a]volume={vol}[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=2[a]')
        map_audio = '[a]'
    elif mp3_index is not None:
        vol = safe_float(audio.get('mp3_volume'), 0.35)
        filters.append(f'[{mp3_index}:a]volume={vol}[a]')
        map_audio = '[a]'
    elif has_drone_audio:
        map_audio = '0:a:0'
    elif silence_index is not None:
        map_audio = f'{silence_index}:a:0'

    cmd += ['-filter_complex', ';'.join(filters), '-map', '[v]']
    if map_audio:
        cmd += ['-map', map_audio]
    cmd += [
        '-c:v', 'h264_vaapi', '-b:v', video_bitrate, '-maxrate', video_bitrate,
        '-bufsize', '12000k', '-g', str(fps * 2), '-bf', '0',
        '-c:a', 'aac', '-b:a', audio_bitrate, '-ar', '44100', '-ac', '2',
        '-f', 'tee', build_tee_arg(settings)
    ]
    return cmd


def build_brb_cmd(settings: Dict[str, Any]) -> Optional[list[str]]:
    out = settings.get('output', {})
    audio = settings.get('audio', {})
    brb = settings.get('brb', {})
    video_bitrate = out.get('video_bitrate', '6500k')
    audio_bitrate = out.get('audio_bitrate', '160k')
    fps = safe_int(out.get('fps'), 30)
    brb_path = BRB_DIR / brb.get('active_mp4', '')
    mp3_path = AUDIO_DIR / audio.get('active_mp3', '')
    mp3_enabled = bool(audio.get('mp3_enabled')) and bool(audio.get('active_mp3')) and mp3_path.exists()

    if brb_path.exists():
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'info', '-stream_loop', '-1', '-re', '-i', str(brb_path)]
    else:
        # Built-in fallback if no BRB video has been uploaded yet.
        cmd = [
            'ffmpeg', '-hide_banner', '-loglevel', 'info', '-re', '-f', 'lavfi',
            '-i', 'color=c=black:s=1920x1080:r=30',
            '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100'
        ]

    input_index = 1 if brb_path.exists() else 2
    mp3_index = None
    silence_index = None
    if mp3_enabled:
        cmd += ['-stream_loop', '-1', '-i', str(mp3_path)]
        mp3_index = input_index
        input_index += 1
    elif brb_path.exists():
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        silence_index = input_index
        input_index += 1
    else:
        silence_index = 1

    filters = [common_video_filter(settings, with_overlay=False)]
    map_audio = None
    if mp3_index is not None:
        vol = safe_float(audio.get('mp3_volume'), 0.35)
        filters.append(f'[{mp3_index}:a]volume={vol}[a]')
        map_audio = '[a]'
    elif silence_index is not None:
        map_audio = f'{silence_index}:a:0'
    else:
        map_audio = '0:a:0'

    cmd += ['-filter_complex', ';'.join(filters), '-map', '[v]', '-map', map_audio]
    cmd += [
        '-c:v', 'h264_vaapi', '-b:v', video_bitrate, '-maxrate', video_bitrate,
        '-bufsize', '12000k', '-g', str(fps * 2), '-bf', '0',
        '-c:a', 'aac', '-b:a', audio_bitrate, '-ar', '44100', '-ac', '2',
        '-f', 'tee', build_tee_arg(settings)
    ]
    return cmd



def build_test_pattern_cmd(settings: Dict[str, Any]) -> list[str]:
    out = settings.get('output', {})
    audio = settings.get('audio', {})
    width = safe_int(out.get('width'), 1920)
    height = safe_int(out.get('height'), 1080)
    fps = safe_int(out.get('fps'), 30)
    video_bitrate = out.get('video_bitrate', '6500k')
    audio_bitrate = out.get('audio_bitrate', '160k')
    mp3_path = AUDIO_DIR / audio.get('active_mp3', '')
    mp3_enabled = bool(audio.get('mp3_enabled')) and bool(audio.get('active_mp3')) and mp3_path.exists()

    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'info', '-re',
        '-f', 'lavfi', '-i', f'testsrc2=size={width}x{height}:rate={fps}',
    ]
    if mp3_enabled:
        cmd += ['-stream_loop', '-1', '-i', str(mp3_path)]
        audio_filter = f'[1:a]volume={safe_float(audio.get("mp3_volume"), 0.35)}[a]'
        map_audio = '[a]'
    else:
        cmd += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        audio_filter = ''
        map_audio = '1:a:0'

    filters = [common_video_filter(settings, with_overlay=True)]
    if audio_filter:
        filters.append(audio_filter)

    cmd += ['-filter_complex', ';'.join(filters), '-map', '[v]', '-map', map_audio]
    cmd += [
        '-c:v', 'h264_vaapi', '-b:v', video_bitrate, '-maxrate', video_bitrate,
        '-bufsize', '12000k', '-g', str(fps * 2), '-bf', '0',
        '-c:a', 'aac', '-b:a', audio_bitrate, '-ar', '44100', '-ac', '2',
        '-f', 'tee', build_tee_arg(settings, local_only=True)
    ]
    return cmd


def switch_to_test_pattern():
    settings = load_settings()
    if not settings.get('system', {}).get('enabled', True):
        set_mode('DISABLED')
        return
    # Test pattern is always local preview only. It never pushes to YouTube/Twitch.
    settings['streaming'] = False
    settings.setdefault('system', {})['local_test_mode'] = True
    save_settings(settings)
    refresh_weather(force=True)
    start_process('TEST_PATTERN', build_test_pattern_cmd(settings))
    set_mode('TEST_PATTERN')
    log_line('events.log', 'Started local TEST_PATTERN with overlay')


def set_mode(mode: str):
    with state_lock:
        status['mode'] = mode


def request_start():
    settings = load_settings()
    if not settings.get('system', {}).get('enabled', True):
        raise RuntimeError('Drone Relay is disabled. Turn the master switch back on first.')
    settings['streaming'] = True
    save_settings(settings)
    log_line('events.log', 'Streaming requested ON')


def request_stop():
    global source_missing_since, brb_started_at, end_deadline
    settings = load_settings()
    settings['streaming'] = False
    settings['mode'] = 'OFFLINE'
    save_settings(settings)
    stop_ffmpeg()
    source_missing_since = None
    brb_started_at = None
    end_deadline = None
    set_mode('OFFLINE')
    log_line('events.log', 'Streaming stopped')



def disable_all():
    global source_missing_since, brb_started_at, end_deadline
    settings = load_settings()
    settings.setdefault('system', {})['enabled'] = False
    settings['streaming'] = False
    settings['mode'] = 'DISABLED'
    save_settings(settings)
    stop_ffmpeg()
    source_missing_since = None
    brb_started_at = None
    end_deadline = None
    set_mode('DISABLED')
    log_line('events.log', 'MASTER DISABLE ALL requested')


def enable_system():
    settings = load_settings()
    settings.setdefault('system', {})['enabled'] = True
    if settings.get('mode') == 'DISABLED':
        settings['mode'] = 'OFFLINE'
    save_settings(settings)
    set_mode('OFFLINE')
    log_line('events.log', 'Master system enabled')

def switch_to_live():
    settings = load_settings()
    if not settings.get('system', {}).get('enabled', True):
        set_mode('DISABLED')
        return
    start_process('LIVE', build_live_cmd(settings))
    set_mode('LIVE')
    log_line('events.log', 'Switched to LIVE')


def switch_to_brb(notify: bool = True):
    global brb_started_at, end_deadline, last_brb_notification_at
    settings = load_settings()
    if not settings.get('system', {}).get('enabled', True):
        set_mode('DISABLED')
        return
    cmd = build_brb_cmd(settings)
    if cmd:
        start_process('BRB', cmd)
    now = time.time()
    brb_started_at = now
    end_deadline = now + safe_int(settings.get('brb', {}).get('end_timeout_seconds'), 300)
    set_mode('BRB')
    log_line('events.log', 'Switched to BRB')
    if notify:
        send_ha_notification(
            'Drone feed dropped',
            'BRB is now live.',
            tag='drone_relay_brb',
            actions=[
                {'action': 'DRONE_STAY_LIVE', 'title': 'Stay Live'},
                {'action': 'DRONE_END_STREAM', 'title': 'End Stream'},
            ],
        )
        last_brb_notification_at = now


def stay_live():
    global end_deadline
    settings = load_settings()
    end_deadline = time.time() + safe_int(settings.get('brb', {}).get('end_timeout_seconds'), 300)
    log_line('events.log', 'Stay Live requested; deadline extended')
    return end_deadline


def ha_headers(token: str) -> Dict[str, str]:
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def get_ha_state(entity: str) -> Optional[Dict[str, Any]]:
    settings = load_settings()
    ha = settings.get('home_assistant', {})
    if not ha.get('enabled') or not HA_URL or not HA_TOKEN or not entity:
        return None
    url = HA_URL + f'/api/states/{entity}'
    try:
        res = requests.get(url, headers=ha_headers(HA_TOKEN), timeout=5)
        if res.ok:
            return res.json()
    except Exception as exc:
        log_line('events.log', f'HA state error for {entity}: {exc}')
    return None


def send_ha_notification(title: str, message: str, tag: str, actions: list[Dict[str, str]]):
    settings = load_settings()
    ha = settings.get('home_assistant', {})
    if not ha.get('enabled') or not ha.get('notifications_enabled') or not HA_TOKEN or not HA_URL:
        return
    service = HA_NOTIFY_SERVICE
    if '.' not in service:
        return
    domain, svc = service.split('.', 1)
    url = HA_URL + f'/api/services/{domain}/{svc}'
    payload = {'title': title, 'message': message, 'data': {'tag': tag, 'actions': actions}}
    try:
        res = requests.post(url, headers=ha_headers(HA_TOKEN), json=payload, timeout=5)
        log_line('events.log', f'HA notify {title}: HTTP {res.status_code}')
    except Exception as exc:
        log_line('events.log', f'HA notify error: {exc}')


def resolve_weather_location(settings: Dict[str, Any]) -> Dict[str, Any]:
    weather = settings.get('weather', {})
    ha = settings.get('home_assistant', {})
    country = weather.get('fallback_country', 'US')

    if weather.get('manual_zip_enabled') and weather.get('manual_zip'):
        return {'type': 'zip', 'zip': weather.get('manual_zip'), 'country': country, 'label': weather.get('display_label', '')}

    mode = weather.get('location_mode')
    if mode in ('home_assistant', 'phone') and ha.get('enabled'):
        zip_entity = HA_ZIP_OVERRIDE_ENTITY
        if zip_entity:
            zip_state = get_ha_state(zip_entity)
            z = (zip_state or {}).get('state')
            if z and re.match(r'^\d{5}$', z):
                return {'type': 'zip', 'zip': z, 'country': country, 'label': weather.get('display_label', '')}
        phone = get_ha_state(HA_PHONE_ENTITY)
        attrs = (phone or {}).get('attributes', {})
        lat = attrs.get('latitude')
        lon = attrs.get('longitude')
        if lat is not None and lon is not None:
            return {'type': 'latlon', 'lat': lat, 'lon': lon, 'label': weather.get('display_label', 'Moving Location')}

    return {'type': 'zip', 'zip': weather.get('fallback_zip', '60148'), 'country': country, 'label': weather.get('display_label', '')}


def refresh_weather(force: bool = False):
    global last_weather_refresh, last_weather_error, last_weather_line, last_weather_data
    settings = load_settings()
    weather = settings.get('weather', {})
    if not weather.get('enabled'):
        line = 'WEATHER OFF'
        write_weather_line(line)
        last_weather_line = line
        last_weather_error = ''
        last_weather_data = {'enabled': False, 'line': line}
        last_weather_refresh = time.time()
        return

    now = time.time()
    refresh_seconds = max(10, safe_int(weather.get('refresh_seconds'), 30))
    if not force and now - last_weather_refresh < refresh_seconds:
        return

    api_key = OPENWEATHER_API_KEY
    if not api_key:
        line = 'OPENWEATHER API KEY NEEDED IN .env'
        write_weather_line(line)
        last_weather_line = line
        last_weather_error = 'Missing OPENWEATHER_API_KEY in /opt/drone-relay/.env. Add it, then restart the stack.'
        last_weather_data = {'enabled': True, 'key_saved': False, 'line': line, 'error': last_weather_error}
        last_weather_refresh = now
        return

    loc = resolve_weather_location(settings)
    params = {'appid': api_key, 'units': weather.get('units', 'imperial')}
    if loc['type'] == 'latlon':
        params.update({'lat': loc['lat'], 'lon': loc['lon']})
    else:
        params.update({'zip': f"{loc.get('zip')},{loc.get('country', 'US')}"})

    try:
        res = requests.get('https://api.openweathermap.org/data/2.5/weather', params=params, timeout=8)
        if not res.ok:
            msg = res.text[:240]
            raise RuntimeError(f'OpenWeather HTTP {res.status_code}: {msg}')
        data = res.json()
        main = data.get('main', {})
        wind = data.get('wind', {})
        wx = (data.get('weather') or [{}])[0]
        label = loc.get('label') or data.get('name') or 'Drone Location'
        temp = round(float(main.get('temp', 0)))
        feels = round(float(main.get('feels_like', temp)))
        wind_speed = round(float(wind.get('speed', 0)))
        gust = wind.get('gust')
        humidity = main.get('humidity')
        pressure = main.get('pressure')
        vis_miles = None
        if data.get('visibility') is not None:
            vis_miles = round(float(data['visibility']) / 1609.344, 1)
        condition = (wx.get('main') or wx.get('description') or 'Weather').upper()
        updated = datetime.now().strftime('%I:%M %p').lstrip('0')
        parts = [
            label.upper(),
            f'{temp}°F FEELS {feels}°',
            f'WIND {wind_speed} MPH',
        ]
        if weather.get('show_gusts') and gust is not None:
            parts.append(f'GUSTS {round(float(gust))} MPH')
        if weather.get('show_visibility') and vis_miles is not None:
            parts.append(f'VIS {vis_miles:g} MI')
        parts.append(condition)
        parts.append(f'WX {updated}')
        line = '  |  '.join(parts)
        write_weather_line(line)
        last_weather_line = line
        last_weather_error = ''
        last_weather_data = {
            'enabled': True,
            'key_saved': True,
            'location_label': label,
            'source_location_name': data.get('name'),
            'location_type': loc.get('type'),
            'zip': loc.get('zip'),
            'lat': loc.get('lat'),
            'lon': loc.get('lon'),
            'temp': temp,
            'feels_like': feels,
            'wind_speed': wind_speed,
            'wind_gust': None if gust is None else round(float(gust)),
            'visibility_miles': vis_miles,
            'humidity': humidity,
            'pressure': pressure,
            'condition': condition,
            'updated': updated,
            'line': line,
            'error': '',
        }
        last_weather_refresh = now
    except Exception as exc:
        last_weather_error = str(exc)
        line = "WEATHER ERROR - USING LAST DATA"
        if not WEATHER_TEXT_PATH.exists():
            write_weather_line(line)
            last_weather_line = line
        last_weather_data = {
            **(last_weather_data or {}),
            'enabled': True,
            'key_saved': True,
            'error': last_weather_error,
            'line': last_weather_line,
        }
        log_line('events.log', f'Weather error: {exc}')
        last_weather_refresh = now


def update_status(input_connected: bool):
    global last_ffmpeg_error
    settings = load_settings()
    now = time.time()
    mode = status.get('mode', 'OFFLINE')
    offline_seconds = 0
    remaining = None
    if source_missing_since:
        offline_seconds = int(now - source_missing_since)
    if end_deadline:
        remaining = max(0, int(end_deadline - now))
    running = bool(ffmpeg_proc and ffmpeg_proc.poll() is None)
    if ffmpeg_proc and ffmpeg_proc.poll() is not None and settings.get('streaming'):
        last_ffmpeg_error = 'FFmpeg process exited. See logs/ffmpeg-current.log.'
    with state_lock:
        status.update({
            'mode': mode,
            'input_connected': input_connected,
            'streaming_requested': bool(settings.get('streaming')),
            'ffmpeg_running': running,
            'process_kind': current_process_kind,
            'offline_seconds': offline_seconds,
            'auto_end_seconds_remaining': remaining,
            'last_weather_line': last_weather_line,
            'last_weather_error': last_weather_error,
            'current_weather': last_weather_data,
            'weather_key_saved': bool(OPENWEATHER_API_KEY),
            'last_weather_age_seconds': None if not last_weather_refresh else int(time.time() - last_weather_refresh),
            'last_ffmpeg_error': last_ffmpeg_error,
            'active_preset': settings.get('active_preset', 'good_signal'),
            'destination_summary': destination_summary(settings),
            'config_summary': {
                'openweather_key': bool(OPENWEATHER_API_KEY),
                'youtube_key': bool(YOUTUBE_STREAM_KEY),
                'twitch_key': bool(TWITCH_STREAM_KEY),
                'home_assistant_token': bool(HA_TOKEN),
                'home_assistant_url': bool(HA_URL),
                'ha_phone_entity': HA_PHONE_ENTITY,
                'ha_zip_override_entity': HA_ZIP_OVERRIDE_ENTITY,
                'ha_notify_service': HA_NOTIFY_SERVICE,
                'youtube_url': YOUTUBE_RTMP_URL,
                'twitch_url': TWITCH_RTMP_URL,
            },
            'system_enabled': bool(settings.get('system', {}).get('enabled', True)),
            'local_test_mode': bool(settings.get('system', {}).get('local_test_mode')),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'media': list_media(),
            'settings': sanitize_settings(settings),
            'preview': {
                'raw_hls': f"http://{request_host_guess()}:8888/live/drone/index.m3u8",
                'program_hls': f"http://{request_host_guess()}:8888/live/program/index.m3u8",
                'raw_webrtc': f"http://{request_host_guess()}:8889/live/drone",
                'program_webrtc': f"http://{request_host_guess()}:8889/live/program",
            }
        })
    try:
        STATUS_PATH.write_text(json.dumps(status, indent=2))
    except Exception:
        pass


def request_host_guess() -> str:
    # Default for linuxbox2; browser JS also replaces this with location.hostname.
    return os.environ.get('PUBLIC_HOST', '192.168.1.17')


def watchdog_loop():
    global last_source_seen, source_missing_since, brb_started_at, end_deadline, last_timeout_notification_at
    write_weather_line('DRONE RELAY STARTING')
    while True:
        try:
            settings = load_settings()
            if not settings.get('system', {}).get('enabled', True):
                if ffmpeg_proc and ffmpeg_proc.poll() is None:
                    stop_ffmpeg()
                set_mode('DISABLED')
                update_status(False)
                time.sleep(3)
                continue
            refresh_weather(force=False)
            input_connected = ffprobe_input(INPUT_RTMP)
            now = time.time()
            if status.get('mode') == 'TEST_PATTERN':
                # Keep local test pattern running until Stop or Disable All is pressed.
                if not ffmpeg_proc or ffmpeg_proc.poll() is not None:
                    switch_to_test_pattern()
                update_status(input_connected)
                time.sleep(3)
                continue
            if input_connected:
                last_source_seen = now
                source_missing_since = None
                if settings.get('streaming') and status.get('mode') in ('OFFLINE', 'BRB') and settings.get('brb', {}).get('auto_return_live', True):
                    switch_to_live()
            else:
                if source_missing_since is None:
                    source_missing_since = now
                if settings.get('streaming'):
                    delay = safe_int(settings.get('brb', {}).get('delay_seconds'), 5)
                    if status.get('mode') == 'LIVE' and now - source_missing_since >= delay:
                        switch_to_brb(notify=True)
                    elif status.get('mode') == 'OFFLINE':
                        switch_to_brb(notify=True)
                    elif status.get('mode') == 'BRB':
                        remaining = int((end_deadline or now) - now)
                        if remaining <= 60 and (last_timeout_notification_at is None or now - last_timeout_notification_at > 120):
                            send_ha_notification(
                                'Drone feed still missing',
                                'Stream will end in about 60 seconds.',
                                tag='drone_relay_timeout',
                                actions=[
                                    {'action': 'DRONE_STAY_LIVE', 'title': 'Stay Live'},
                                    {'action': 'DRONE_END_STREAM', 'title': 'End Stream'},
                                ],
                            )
                            last_timeout_notification_at = now
                        if end_deadline and now >= end_deadline:
                            request_stop()
            if not settings.get('streaming') and status.get('mode') not in ('OFFLINE', 'TEST_PATTERN'):
                request_stop()
            if settings.get('streaming') and status.get('mode') == 'LIVE' and (not ffmpeg_proc or ffmpeg_proc.poll() is not None) and input_connected:
                switch_to_live()
            if settings.get('streaming') and status.get('mode') == 'BRB' and (not ffmpeg_proc or ffmpeg_proc.poll() is not None):
                switch_to_brb(notify=False)
            update_status(input_connected)
        except Exception as exc:
            log_line('events.log', f'Watchdog error: {exc}')
        time.sleep(3)


@app.route('/')
def root():
    return redirect(url_for('admin'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        error = 'Invalid login'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin')
def admin():
    if not login_ok():
        return redirect(url_for('login'))
    return render_template('admin.html', presets=PRESETS)


@app.route('/api/status')
def api_status():
    auth = require_api()
    if auth:
        return auth
    update_status(status.get('input_connected', False))
    return jsonify({'ok': True, **status})


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    auth = require_api()
    if auth:
        return auth
    if request.method == 'GET':
        return jsonify({'ok': True, 'settings': sanitize_settings(load_settings()), 'media': list_media(), 'presets': PRESETS})
    current = load_settings()
    posted = request.get_json(force=True, silent=True) or {}
    new_settings = merge_posted_settings(current, posted)
    save_settings(new_settings)
    refresh_weather(force=True)
    return jsonify({'ok': True, 'settings': sanitize_settings(new_settings)})



@app.route('/api/weather/test', methods=['POST'])
def api_weather_test():
    auth = require_api()
    if auth:
        return auth
    refresh_weather(force=True)
    return jsonify({
        'ok': not bool(last_weather_error),
        'weather': last_weather_line,
        'current_weather': last_weather_data,
        'error': last_weather_error,
    })


@app.route('/api/upload/<kind>', methods=['POST'])
def api_upload(kind: str):
    auth = require_api()
    if auth:
        return auth
    if kind not in ('brb', 'audio'):
        return jsonify({'ok': False, 'error': 'Invalid upload type'}), 400
    if 'file' not in request.files:
        return jsonify({'ok': False, 'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'ok': False, 'error': 'Missing filename'}), 400
    exts = {'mp4'} if kind == 'brb' else {'mp3'}
    if not allowed_file(file.filename, exts):
        return jsonify({'ok': False, 'error': f'Only {", ".join(exts)} allowed'}), 400
    filename = secure_filename(file.filename.lower().replace(' ', '-'))
    target_dir = BRB_DIR if kind == 'brb' else AUDIO_DIR
    target = target_dir / filename
    file.save(target)
    log_line('events.log', f'Uploaded {kind}: {filename}')
    return jsonify({'ok': True, 'filename': filename, 'media': list_media()})


@app.route('/api/media/select', methods=['POST'])
def api_media_select():
    auth = require_api()
    if auth:
        return auth
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get('kind')
    filename = data.get('filename', '')
    settings = load_settings()
    if kind == 'brb':
        if filename and not (BRB_DIR / filename).exists():
            return jsonify({'ok': False, 'error': 'BRB file not found'}), 404
        settings['brb']['active_mp4'] = filename
    elif kind == 'audio':
        if filename and not (AUDIO_DIR / filename).exists():
            return jsonify({'ok': False, 'error': 'Audio file not found'}), 404
        settings['audio']['active_mp3'] = filename
    else:
        return jsonify({'ok': False, 'error': 'Invalid kind'}), 400
    save_settings(settings)
    return jsonify({'ok': True, 'settings': sanitize_settings(settings)})


@app.route('/api/start', methods=['POST'])
def api_start():
    auth = require_api()
    if auth:
        return auth
    try:
        request_start()
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    return jsonify({'ok': True})



@app.route('/api/disable-all', methods=['POST'])
def api_disable_all():
    auth = require_api()
    if auth:
        return auth
    disable_all()
    return jsonify({'ok': True})


@app.route('/api/enable-system', methods=['POST'])
def api_enable_system():
    auth = require_api()
    if auth:
        return auth
    enable_system()
    return jsonify({'ok': True})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    auth = require_api()
    if auth:
        return auth
    request_stop()
    return jsonify({'ok': True})


@app.route('/api/test-pattern', methods=['POST'])
def api_test_pattern():
    auth = require_api()
    if auth:
        return auth
    switch_to_test_pattern()
    return jsonify({'ok': True})


@app.route('/api/brb', methods=['POST'])
def api_brb():
    auth = require_api()
    if auth:
        return auth
    settings = load_settings()
    settings['streaming'] = True
    save_settings(settings)
    switch_to_brb(notify=False)
    return jsonify({'ok': True})


@app.route('/api/live', methods=['POST'])
def api_live():
    auth = require_api()
    if auth:
        return auth
    settings = load_settings()
    settings['streaming'] = True
    save_settings(settings)
    switch_to_live()
    return jsonify({'ok': True})


@app.route('/api/stay-live', methods=['POST'])
def api_stay_live():
    auth = require_api()
    if auth:
        return auth
    deadline = stay_live()
    return jsonify({'ok': True, 'deadline': deadline})


@app.route('/api/weather/refresh', methods=['POST'])
def api_weather_refresh():
    auth = require_api()
    if auth:
        return auth
    refresh_weather(force=True)
    return jsonify({'ok': True, 'weather': last_weather_line, 'error': last_weather_error})


@app.route('/api/location/reset-phone', methods=['POST'])
def api_reset_phone():
    auth = require_api()
    if auth:
        return auth
    settings = load_settings()
    settings['weather']['manual_zip_enabled'] = False
    settings['weather']['location_mode'] = 'home_assistant'
    save_settings(settings)
    refresh_weather(force=True)
    return jsonify({'ok': True, 'settings': sanitize_settings(settings)})


@app.route('/api/preset/<name>', methods=['POST'])
def api_preset(name: str):
    auth = require_api()
    if auth:
        return auth
    if name not in PRESETS:
        return jsonify({'ok': False, 'error': 'Unknown preset'}), 404
    settings = load_settings()
    preset = deepcopy(PRESETS[name])
    label = preset.pop('label', None)
    deep_merge(settings, preset)
    settings['active_preset'] = name
    save_settings(settings)
    log_line('events.log', f'Preset applied: {name}')
    return jsonify({'ok': True, 'label': label, 'settings': sanitize_settings(settings)})


@app.route('/api/audio/mute-mp3', methods=['POST'])
def api_mute_mp3():
    auth = require_api()
    if auth:
        return auth
    settings = load_settings()
    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        settings['audio']['mp3_enabled'] = bool(data['enabled'])
    else:
        settings['audio']['mp3_enabled'] = not bool(settings['audio'].get('mp3_enabled'))
    save_settings(settings)
    return jsonify({'ok': True, 'mp3_enabled': settings['audio']['mp3_enabled']})


@app.route('/api/audio/mute-drone', methods=['POST'])
def api_mute_drone():
    auth = require_api()
    if auth:
        return auth
    settings = load_settings()
    data = request.get_json(silent=True) or {}
    if 'enabled' in data:
        settings['audio']['drone_audio_enabled'] = bool(data['enabled'])
    else:
        settings['audio']['drone_audio_enabled'] = not bool(settings['audio'].get('drone_audio_enabled'))
    save_settings(settings)
    return jsonify({'ok': True, 'drone_audio_enabled': settings['audio']['drone_audio_enabled']})


if __name__ == '__main__':
    threading.Thread(target=watchdog_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=8080, threaded=True)
