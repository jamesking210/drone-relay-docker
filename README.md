# Drone Relay Docker V9

This is my Docker-based drone relay setup for streaming DJI Fly footage through `linuxbox2`, adding a simple drone/weather overlay, handling BRB fallback, and pushing the final stream to YouTube or Twitch when I want.

V9 is a cleaned-up full package. It includes the previous hotfixes, the cleaner dashboard, dry testing, scanner/AzuraCast audio options, and a safer encoder setup.

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

That is the clean deploy path.

The installer intentionally:

```text
Stops old Drone Relay containers only
Removes /opt/drone-relay
Downloads this GitHub repo as a public ZIP
Copies everything fresh
Copies .env.example to .env
Builds and starts Docker Compose
```

It does **not** stop AzuraCast, Portainer, DJMIXHUB, or my other Docker stacks.

---

## Admin page

```text
http://192.168.1.17:8589/admin
```

Default login is in `.env`:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
```

---

## Edit .env

All keys and private stream URLs live in `.env`, not in the admin page.

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

SCANNER_STREAM_URL=
AZURACAST_STREAM_URL=

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

```text
8589   Admin page
19350  RTMP ingest and RTMP program output
8888   HLS preview/output
8889   WebRTC preview/output
9997   MediaMTX API, host-local only
```

---

## Ingest and output URLs

### DJI Fly ingest

```text
rtmp://192.168.1.17:19350/live/drone
```

### Raw drone preview

```text
http://192.168.1.17:8888/live/drone/index.m3u8
http://192.168.1.17:8889/live/drone
```

### Final program output for VLC / OBS / desktop1

Use this first:

```text
http://192.168.1.17:8888/live/program/index.m3u8
```

RTMP program output:

```text
rtmp://192.168.1.17:19350/live/program
```

WebRTC browser preview:

```text
http://192.168.1.17:8889/live/program
```

---

## What this does

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

The final program can include:

```text
Drone video
Top weather bar
Live clock
Uploaded MP3 audio
Scanner feed audio
AzuraCast audio
BRB video if the drone feed drops
```

---

## Dry testing

Dry tests do not need DJI Fly ingest.

Dry tests do not push to YouTube or Twitch.

Buttons:

```text
Test Pattern
Test BRB
Test Audio
```

Use these while debugging in the house.

Then check:

```text
http://192.168.1.17:8888/live/program/index.m3u8
```

or:

```text
rtmp://192.168.1.17:19350/live/program
```

---

## Encoder behavior

`.env` has:

```env
ENCODER_MODE=auto
```

Auto mode tries Intel VAAPI first.

If FFmpeg dies right away from a VAAPI problem, the app retries with CPU `libx264`.

Options:

```env
ENCODER_MODE=auto
ENCODER_MODE=vaapi
ENCODER_MODE=cpu
```

Use `cpu` if VAAPI keeps being annoying and I just want the stream working.

---

## Audio

Audio source options on the admin page:

```text
Uploaded MP3
Scanner feed from .env
AzuraCast feed from .env
Drone audio
Silent
```

Scanner and AzuraCast links go in `.env`:

```env
SCANNER_STREAM_URL=
AZURACAST_STREAM_URL=
```

BRB MP4 audio has its own mute and volume controls.

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

---

## Home Assistant later

API endpoints:

```text
GET  /api/status
POST /api/start
POST /api/stop
POST /api/brb
POST /api/live
POST /api/stay-live
POST /api/test-pattern
POST /api/test-brb
POST /api/test-audio
POST /api/disable-all
POST /api/enable-system
```

Use header:

```text
X-Drone-Token: your DRONE_API_TOKEN
```

---

## Updating linuxbox2

For now, the installer is intentionally clean/destructive for this project folder.

To update from GitHub later:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

Because the installer resets `.env`, I need to put my real keys back in after a clean update.

Once the project is stable, I can change the installer to preserve `.env` and uploaded media.

---

## Useful commands

```bash
cd /opt/drone-relay
docker compose ps
docker compose logs -f drone-relay
docker compose logs -f mediamtx
tail -n 120 logs/ffmpeg.log
docker compose down
docker compose up -d --build
```

Test VAAPI inside the container:

```bash
cd /opt/drone-relay
docker compose exec drone-relay vainfo --display drm --device /dev/dri/renderD128
```

If that fails but the stream works, it probably fell back to CPU encoding.

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
