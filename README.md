# Drone Relay Docker

This is my Docker-based drone relay setup for streaming DJI Fly footage through `linuxbox2`, adding a simple drone/weather overlay, handling BRB fallback, and pushing the final stream to YouTube or Twitch when I want.

This version is cleaned up for testing. The installer removes the old Drone Relay setup, copies a fresh `.env.example` to `.env`, and starts the stack.

It only touches Drone Relay. It does not stop AzuraCast, Portainer, DJMIXHUB, or my other Docker stacks.

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

---

## Quick deploy

Upload this repo to:

```text
https://github.com/jamesking210/drone-relay-docker
```

Then run this on `linuxbox2`:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

That is the whole deploy path.

The installer does this:

```text
Stops old Drone Relay containers only
Removes /opt/drone-relay
Downloads this GitHub repo as a public ZIP
Copies everything fresh
Copies .env.example to .env
Builds and starts Docker Compose
```

---

## Open the admin page

```text
http://192.168.1.17:8589/admin
```

Default login is set in `.env`:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
```

Change it later before exposing the admin page outside my LAN.

---

## Edit .env

All keys live in `.env`, not the admin page.

```bash
cd /opt/drone-relay
nano .env
```

Important values:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
FLASK_SECRET_KEY=make-this-random
DRONE_API_TOKEN=make-this-random

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

Restart after editing:

```bash
docker compose up -d --build
```

---

## Ports

These ports were picked to avoid AzuraCast, DJMIXHUB, my existing overlay container, and Portainer.

```text
8589   Admin page
19350  RTMP ingest and RTMP program output
8888   HLS preview/output
8889   WebRTC preview/output
9997   MediaMTX API, bound to localhost on the host
```

---

## Ingest and output URLs

### DJI Fly ingest

Use this in DJI Fly custom RTMP:

```text
rtmp://192.168.1.17:19350/live/drone
```

### Raw drone preview

Use this to see what DJI Fly is sending:

```text
http://192.168.1.17:8888/live/drone/index.m3u8
```

### Final program output

This is the finished local program feed.

Use this in VLC or OBS:

```text
http://192.168.1.17:8888/live/program/index.m3u8
```

RTMP program output:

```text
rtmp://192.168.1.17:19350/live/program
```

WebRTC program output:

```text
http://192.168.1.17:8889/live/program
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

---

## Test Pattern mode

If nothing is streaming from DJI Fly, press:

```text
Test Pattern
```

This starts a local 1080p test pattern with the overlay and clock.

Test Pattern is local-only. It does not push to YouTube or Twitch.

Use it to test:

```text
FFmpeg
VAAPI encode
weather overlay
clock overlay
MP3 audio
final program output URL
OBS/VLC preview
```

---

## Local Test Mode

Local Test Mode blocks external output.

When Local Test Mode is on:

```text
Final program preview works
YouTube output is blocked
Twitch output is blocked
```

This is the safest setting while testing.

---

## Disable All

Disable All is the panic switch.

It:

```text
Stops FFmpeg
Turns streaming off
Prevents restart
Sets mode to DISABLED
```

Use Enable System to recover.

---

## YouTube and Twitch

Stream keys live in `.env`.

```env
YOUTUBE_STREAM_KEY=
TWITCH_STREAM_KEY=
```

The admin page only has simple on/off toggles.

If Local Test Mode is on, nothing external is pushed even if YouTube/Twitch are on.

---

## Weather overlay

OpenWeather key lives in `.env`.

```env
OPENWEATHER_API_KEY=
```

The admin page shows the current weather line at the top.

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

The clock is drawn live by FFmpeg so it does not freeze like a screenshot.

---

## Home Assistant later

Home Assistant API token lives in `.env`.

```env
DRONE_API_TOKEN=
```

Endpoints for later:

```text
POST /api/start
POST /api/stop
POST /api/brb
POST /api/live
POST /api/stay-live
POST /api/test-pattern
POST /api/disable-all
POST /api/enable-system
GET  /api/status
```

---

## Useful commands

```bash
cd /opt/drone-relay
docker compose ps
docker compose logs -f drone-relay
docker compose logs -f mediamtx
docker compose down
docker compose up -d --build
```

---

## Test without DJI Fly from command line

The admin Test Pattern button is easier, but this also works:

```bash
ffmpeg -re \
  -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=440:sample_rate=44100 \
  -c:v libx264 -preset veryfast -b:v 3000k \
  -c:a aac -b:a 128k \
  -f flv rtmp://127.0.0.1:19350/live/drone
```

Then press Start Stream in the admin page.

---

## Do not commit secrets

Do not commit real values in:

```text
.env
config/settings.json
```

Good files to commit:

```text
README.md
install.sh
docker-compose.yml
.env.example
config/settings.example.json
config/mediamtx.yml
app/
media/*/README.txt
logs/.gitkeep
overlay/.gitkeep
```
