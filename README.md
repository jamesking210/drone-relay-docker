# Drone Relay Docker

This is my Docker-based drone relay setup for sending DJI Fly footage into `linuxbox2`, adding a simple drone/weather overlay, handling BRB fallback, and pushing the final stream to YouTube or Twitch when I want.

The admin page is meant to be a clean field control panel. API keys, stream keys, and Home Assistant tokens live in `.env`, not in the browser.

Target box:

```text
linuxbox2
IP: 192.168.1.17
Ubuntu Desktop 24.04
Intel i5-6500
24GB RAM
Intel HD Graphics 530
Docker / Portainer friendly
```

I already confirmed VAAPI hardware encoding works on this box.

---

## Quick start

### 1. Install or update the app

Run this on `linuxbox2`:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

This downloads the public GitHub ZIP and installs everything to:

```text
/opt/drone-relay
```

It does **not** use `git clone`, so it should not ask for a GitHub username, password, or token.

### 2. Edit the `.env` file

```bash
cd /opt/drone-relay
nano .env
```

Put my real keys/passwords in there.

At minimum, change these:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-now
FLASK_SECRET_KEY=make-this-long-and-random
DRONE_API_TOKEN=make-this-long-and-random-too
```

Add these when I am ready:

```env
OPENWEATHER_API_KEY=

YOUTUBE_RTMP_URL=rtmps://a.rtmps.youtube.com/live2
YOUTUBE_STREAM_KEY=

TWITCH_RTMP_URL=rtmp://live.twitch.tv/app
TWITCH_STREAM_KEY=

HOME_ASSISTANT_URL=http://192.168.1.3:8123
HOME_ASSISTANT_TOKEN=
HA_PHONE_ENTITY=device_tracker.s24
HA_ZIP_OVERRIDE_ENTITY=input_text.drone_overlay_zip
HA_NOTIFY_SERVICE=notify.mobile_app_s24
```

### 3. Restart after editing `.env`

```bash
cd /opt/drone-relay
docker compose up -d --build
```

### 4. Open the admin page

```text
http://192.168.1.17:8589/admin
```

---

## Future me commands

### Normal install/update

Use this most of the time. It preserves `.env`, uploaded media, settings, logs, and generated overlay files.

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

### Update and stop old Drone Relay containers first

Use this if I am testing and want the installer to stop/remove the old Drone Relay containers before starting the updated stack.

This does **not** stop AzuraCast, Portainer, DJMIXHUB, or my other containers.

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | CLEAN=1 bash
```

### Update and reset `.env` from `.env.example`

Use this when `.env.example` changed and I want the newest `.env` layout.

It backs up the old `.env` first.

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | RESET_ENV=1 bash
```

Then edit my keys again:

```bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

### Hard reset for testing

Use this only if the install is messy and I want a clean app folder.

It backs up local data first, stops the old Drone Relay stack, removes `/opt/drone-relay`, reinstalls from GitHub, resets `.env`, and starts fresh.

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | RESET_APP=1 RESET_ENV=1 bash
```

Then edit:

```bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

Backups are stored in:

```text
~/drone-relay-backups/
```

---

## What this does

Basic flow:

```text
DJI Fly app / phone
        ↓ RTMP
linuxbox2
        ↓
MediaMTX receives the drone stream
        ↓
FFmpeg builds the final program feed
        ↓
Local preview + optional YouTube/Twitch output
```

The final stream can include:

```text
Drone video
Top weather bar
Live clock
Looping background MP3
BRB video if the drone feed drops
```

If the drone feed drops:

```text
Wait 5 seconds
Switch to BRB
Notify Home Assistant / my S24 if enabled
Keep BRB live for 5 minutes
End stream if the drone feed does not come back
```

---

## Ports

These ports avoid AzuraCast, DJMIXHUB, my existing OBS overlay, and Portainer.

```text
8589   Drone Relay admin page
19350  DJI Fly RTMP ingest
8888   HLS preview
8889   WebRTC preview
9997   MediaMTX API, bound to localhost on the host
```

Local URLs:

```text
Admin page:
http://192.168.1.17:8589/admin

DJI Fly RTMP ingest:
rtmp://192.168.1.17:19350/live/drone

Raw drone HLS preview:
http://192.168.1.17:8888/live/drone/index.m3u8

Final program HLS preview:
http://192.168.1.17:8888/live/program/index.m3u8

Raw drone WebRTC preview:
http://192.168.1.17:8889/live/drone

Final program WebRTC preview:
http://192.168.1.17:8889/live/program
```

---

## Admin page

Open:

```text
http://192.168.1.17:8589/admin
```

The admin page is meant to be usable from my phone while I am out flying.

Main buttons:

```text
Start Stream
Test Pattern
Force BRB
Return Live
Stay Live
End Stream
Enable System
Disable All
```

The dark/light mode toggle is at the top right.

The admin page should not ask for API keys or stream keys. It should only show whether those keys exist in `.env`.

---

## Test Pattern mode

This is for testing when nothing is streaming from DJI Fly.

Press:

```text
Test Pattern
```

It starts a local 1080p test pattern with the weather overlay and clock.

Important:

```text
Test Pattern is always local-only.
It does not push to YouTube.
It does not push to Twitch.
It only publishes the final program preview locally.
```

Use this to test:

```text
FFmpeg
VAAPI encode
weather overlay
clock overlay
MP3 audio if selected
final program preview
```

---

## Local Test Mode

Local Test Mode blocks external output.

When this is on:

```text
Final program preview works
YouTube output is blocked
Twitch output is blocked
```

This is the safe mode for testing overlays, BRB, audio, and presets.

---

## Disable All

Disable All is the panic switch.

It does this:

```text
Stops FFmpeg
Turns streaming off
Prevents watchdog restart
Sets mode to DISABLED
```

To recover:

```text
Press Enable System
```

API endpoints for Home Assistant later:

```text
POST /api/disable-all
POST /api/enable-system
```

---

## DJI Fly setup

In DJI Fly, use custom RTMP streaming.

For local testing:

```text
rtmp://192.168.1.17:19350/live/drone
```

For remote use later, use Tailscale or a port-forwarded DNS name.

Tailscale example:

```text
rtmp://TAILSCALE-IP:19350/live/drone
```

Public DNS example later:

```text
rtmp://drone-ingest.example.com:19350/live/drone
```

---

## YouTube and Twitch

The stream keys live in `.env`:

```env
YOUTUBE_STREAM_KEY=
TWITCH_STREAM_KEY=
```

The admin page has simple toggles for YouTube and Twitch.

If Local Test Mode is on, nothing external is pushed no matter what the toggles say.

The goal is for linuxbox2 to output:

```text
1920x1080
30 FPS
H.264
AAC audio
```

If DJI Fly sends 720p because of weak cell service, linuxbox2 will upscale it into the 1080p program canvas.

---

## Weather overlay

OpenWeather key lives in `.env`:

```env
OPENWEATHER_API_KEY=
```

The admin page controls what gets displayed:

```text
Weather on/off
Location label
Fallback ZIP
Manual ZIP override
Home Assistant phone location mode
Refresh seconds
Show gusts
Show visibility
```

The overlay can show:

```text
Location label
Temp
Feels like
Wind
Gusts
Visibility
Conditions
Clock
```

The clock is drawn live by FFmpeg, so it does not freeze like a screenshot clock.

BRB mode does not use the weather overlay.

---

## Home Assistant

Home Assistant secrets live in `.env`:

```env
HOME_ASSISTANT_URL=http://192.168.1.3:8123
HOME_ASSISTANT_TOKEN=
HA_PHONE_ENTITY=device_tracker.s24
HA_ZIP_OVERRIDE_ENTITY=input_text.drone_overlay_zip
HA_NOTIFY_SERVICE=notify.mobile_app_s24
```

The admin page only has simple toggles:

```text
Use Home Assistant
S24 Notifications
```

The API token for Home Assistant REST commands is:

```env
DRONE_API_TOKEN=
```

---

## Home Assistant REST commands

Example:

```yaml
rest_command:
  drone_relay_start:
    url: "http://192.168.1.17:8589/api/start"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_stop:
    url: "http://192.168.1.17:8589/api/stop"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_brb:
    url: "http://192.168.1.17:8589/api/brb"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_live:
    url: "http://192.168.1.17:8589/api/live"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_stay_live:
    url: "http://192.168.1.17:8589/api/stay-live"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_test_pattern:
    url: "http://192.168.1.17:8589/api/test-pattern"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_disable_all:
    url: "http://192.168.1.17:8589/api/disable-all"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_enable_system:
    url: "http://192.168.1.17:8589/api/enable-system"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token
```

In `secrets.yaml`:

```yaml
drone_relay_api_token: your-token-from-env
```

---

## S24 actionable notifications

The goal:

```text
Drone feed drops
BRB starts
S24 notification appears
I can tap Stay Live or End Stream
```

Automation example:

```yaml
alias: Drone Relay - Handle Notification Actions
mode: parallel

trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: DRONE_STAY_LIVE

  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: DRONE_END_STREAM

action:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'DRONE_STAY_LIVE' }}"
        sequence:
          - service: rest_command.drone_relay_stay_live

      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'DRONE_END_STREAM' }}"
        sequence:
          - service: rest_command.drone_relay_stop
```

---

## Test without DJI Fly

The easy way is the admin page:

```text
Test Pattern
```

That does not require DJI Fly at all.

If I want to test raw ingest anyway, I can publish a fake stream:

```bash
ffmpeg -re \
  -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=440:sample_rate=44100 \
  -c:v libx264 -preset veryfast -b:v 3000k \
  -c:a aac -b:a 128k \
  -f flv rtmp://127.0.0.1:19350/live/drone
```

Then open:

```text
http://192.168.1.17:8589/admin
```

Press Start Stream.

---

## Useful Docker commands

Start or update:

```bash
cd /opt/drone-relay
docker compose up -d --build
```

Stop:

```bash
cd /opt/drone-relay
docker compose down
```

Logs:

```bash
cd /opt/drone-relay
docker compose logs -f drone-relay
```

MediaMTX logs:

```bash
cd /opt/drone-relay
docker compose logs -f mediamtx
```

Status:

```bash
cd /opt/drone-relay
docker compose ps
```

---

## Hardware checks

Check Intel GPU device:

```bash
ls -lah /dev/dri
```

Good result includes:

```text
renderD128
```

Check VAAPI:

```bash
vainfo
```

Check FFmpeg encoders:

```bash
ffmpeg -hide_banner -encoders | grep -E "h264_vaapi|h264_qsv"
```

Good result includes:

```text
h264_vaapi
h264_qsv
```

Docker passthrough test:

```bash
docker run --rm -it \
  --device /dev/dri:/dev/dri \
  ubuntu:24.04 \
  bash
```

Inside the container:

```bash
ls -lah /dev/dri
exit
```

---

## Check port conflicts

Before installing:

```bash
sudo ss -ltnp | grep -E ':8589|:19350|:8888|:8889|:9997'
```

No output means the ports are clear.

---

## Do not commit secrets

Do not commit real values in:

```text
.env
config/settings.json
```

Do not commit real:

```text
YouTube stream keys
Twitch stream keys
OpenWeather API key
Home Assistant token
Drone API token
Admin password
```

Good files to commit:

```text
docker-compose.yml
Dockerfile
install.sh
README.md
.env.example
config/settings.example.json
app files
scripts
templates
static files
```
