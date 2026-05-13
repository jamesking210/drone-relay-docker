# Drone Relay Docker

This is my Docker-based drone relay setup for streaming DJI Fly footage through `linuxbox2`, adding a simple drone/weather overlay, handling BRB fallback, and pushing the final stream to YouTube and optionally Twitch.

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

I already confirmed Intel VAAPI hardware encoding works on this box.

---

## What this does

```text
DJI Fly app / phone
        ↓ RTMP
linuxbox2
        ↓
MediaMTX receives the drone stream
        ↓
FFmpeg builds the final program
        ↓
Local preview + YouTube/Twitch if enabled
```

The final program can include:

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

These avoid my AzuraCast, DJMIXHUB, existing OBS overlay, and Portainer ports.

```text
8589   Drone Relay admin page
19350  DJI Fly RTMP ingest
8888   HLS preview
8889   WebRTC preview
9997   MediaMTX API
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

## One-line install

This does **not** use `git clone`, so it should not ask for a GitHub username, password, or token.

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

Then open:

```text
http://192.168.1.17:8589/admin
```

---

## First-time setup

```bash
cd /opt/drone-relay
nano .env
```

Change these:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-now
FLASK_SECRET_KEY=make-this-long-and-random
DRONE_API_TOKEN=make-this-long-and-random-too
```

Restart:

```bash
docker compose up -d --build
```

---

## Updating later

Run the same one-liner again:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

The installer preserves:

```text
.env
config/settings.json
media/
logs/
overlay/weather.png
```

---

## Admin page

The admin page is designed to work from my phone while I am out flying.

Main features:

```text
Start stream
End stream
Force BRB
Return live
Stay live
Disable all
Enable system
Local test mode
Raw drone preview
Final program preview
Upload BRB .mp4 files
Upload background .mp3 files
Pick active BRB
Pick active MP3
Mute drone audio
Mute MP3 audio
Change MP3 volume
Set BRB delay
Set auto-end timeout
Save YouTube stream key
Save Twitch stream key
Save OpenWeather API key
Save Home Assistant settings
Use phone location
Use ZIP override
Reset back to phone location
Apply presets
```

---

## Important mode switches

### Local Test Mode

Local Test Mode still builds the final program and publishes it to the local preview path:

```text
rtmp://mediamtx:1935/live/program
```

But it does **not** push to YouTube or Twitch.

This is for testing overlays, audio, BRB, and previews without going live.

### Disable All

Disable All is the panic switch.

It stops FFmpeg, stops streaming, and prevents the watchdog from restarting anything.

It is exposed through the API so Home Assistant can control it later:

```text
POST /api/disable-all
POST /api/enable-system
```

---

## Weather

The weather overlay is generated locally on linuxbox2.

It does not depend on `drone.jimkelsey.com`.

The top bar shows:

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

The admin page also shows the current weather line at the top so I can immediately tell if the overlay has good data.

The OpenWeather call uses the current weather API:

```text
https://api.openweathermap.org/data/2.5/weather
```

With either:

```text
zip=60148,US
```

or:

```text
lat=...
lon=...
```

The API key is sent as:

```text
appid=YOUR_KEY
```

Units are sent as:

```text
units=imperial
```

### If weather says API key needed

Re-enter the OpenWeather key in the Weather section and hit **Save Weather**.

The page intentionally leaves secret fields blank after saving, so blank means “keep the saved value.”

Then hit **Test Weather**.

---

## YouTube and Twitch

YouTube and Twitch can both be configured in the admin page.

YouTube default RTMP URL:

```text
rtmps://a.rtmps.youtube.com/live2
```

Twitch default RTMP URL:

```text
rtmp://live.twitch.tv/app
```

If Local Test Mode is on, neither YouTube nor Twitch will receive the stream even if they are enabled.

---

## DJI Fly setup

In DJI Fly, use custom RTMP streaming:

```text
rtmp://192.168.1.17:19350/live/drone
```

For remote use later, I can use Tailscale or a port-forwarded DNS name.

---

## Presets

Presets included:

```text
Good Signal
Low Signal
Music Stream
Silent Stream
Windy Day
Local Test Mode
```

Suggested use:

```text
Good Signal:
DJI sends 1080p
Output 1080p30
Higher bitrate
MP3 on

Low Signal:
DJI sends 720p
Output still 1080p30
Lower bitrate

Music Stream:
Drone audio muted
MP3 on

Silent Stream:
Drone audio muted
MP3 muted

Windy Day:
Gusts shown/emphasized

Local Test Mode:
No YouTube/Twitch push
Local preview only
```

---

## Home Assistant API

Use the `DRONE_API_TOKEN` from `.env`.

Useful endpoints:

```text
GET  /api/status
POST /api/start
POST /api/stop
POST /api/brb
POST /api/live
POST /api/stay-live
POST /api/disable-all
POST /api/enable-system
POST /api/weather/refresh
POST /api/weather/test
POST /api/location/reset-phone
POST /api/preset/good_signal
POST /api/preset/low_signal
POST /api/preset/test_mode
POST /api/audio/mute-mp3
POST /api/audio/mute-drone
```

Example Home Assistant REST command:

```yaml
rest_command:
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

---

## Test without DJI Fly

After the stack is running, publish a fake stream from linuxbox2:

```bash
ffmpeg -re \
  -f lavfi -i testsrc2=size=1280x720:rate=30 \
  -f lavfi -i sine=frequency=440:sample_rate=44100 \
  -c:v libx264 -preset veryfast -b:v 3000k \
  -c:a aac -b:a 128k \
  -f flv rtmp://127.0.0.1:19350/live/drone
```

Open:

```text
http://192.168.1.17:8589/admin
```

Turn on Local Test Mode, then press Start.

---

## Useful Docker commands

```bash
cd /opt/drone-relay

docker compose ps
docker compose logs -f drone-relay
docker compose logs -f mediamtx
docker compose restart drone-relay
docker compose down
docker compose up -d --build
```

---

## Hardware checks

```bash
ls -lah /dev/dri
vainfo
ffmpeg -hide_banner -encoders | grep -E "h264_vaapi|h264_qsv"
```

Good result includes:

```text
renderD128
h264_vaapi
```

Docker passthrough test:

```bash
docker run --rm -it \
  --device /dev/dri:/dev/dri \
  ubuntu:24.04 \
  bash

ls -lah /dev/dri
exit
```

---

## Do not commit secrets

Do not commit real versions of:

```text
.env
config/settings.json
YouTube stream keys
Twitch stream keys
OpenWeather API key
Home Assistant token
```
