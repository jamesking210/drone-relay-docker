# Drone Relay Docker

This is my Docker-based drone relay setup for streaming DJI Fly footage through my home server, adding a simple drone/weather overlay, handling BRB fallback, and pushing the final stream to YouTube.

This is being built for:

```text
linuxbox2
IP: 192.168.1.17
Ubuntu Desktop 24.04
Intel i5-6500
24GB RAM
Intel HD Graphics 530
Docker / Portainer friendly
```

I already confirmed Intel VAAPI hardware encoding works on this box, so the goal is to output a steady 1080p30 stream without beating up the CPU.

---

## What this does

The basic idea:

```text
DJI Fly app / phone
        ↓ RTMP
linuxbox2
        ↓
MediaMTX receives the drone stream
        ↓
FFmpeg builds the final stream
        ↓
YouTube Live
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

## Why Docker

I want this to be portable and easy to run next to my other stuff on `linuxbox2`, like AzuraCast, DJMIXHUB, Portainer, and other web projects.

This project is meant to be deployed with Docker Compose and managed from the browser.

---

## Ports

These ports were picked so they do not step on AzuraCast, DJMIXHUB, my existing OBS overlay, or Portainer.

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

This install does **not** use `git clone`.

That means it should not ask for a GitHub username, password, or token.

It downloads the public GitHub ZIP file and installs everything to:

```text
/opt/drone-relay
```

Run this on `linuxbox2`:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

Then open:

```text
http://192.168.1.17:8589/admin
```

---

## What the installer does

The installer:

```text
1. Installs curl, unzip, rsync, and Docker if needed
2. Downloads this GitHub repo as a public ZIP
3. Installs it to /opt/drone-relay
4. Creates .env if it does not already exist
5. Creates the needed media/config/log folders
6. Starts the Docker Compose stack
```

The installer preserves these during updates:

```text
.env
config/settings.json
media/
logs/
overlay/weather.png
```

So I can run the same installer again later to update the project without wiping my keys, uploaded MP3s, BRB videos, or settings.

---

## Updating later

Run the same command again:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
```

Then check the stack:

```bash
cd /opt/drone-relay
docker compose ps
```

---

## First-time setup

After the first install:

```bash
cd /opt/drone-relay
nano .env
```

Change these right away:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me-now
FLASK_SECRET_KEY=make-this-long-and-random
DRONE_API_TOKEN=make-this-long-and-random-too
```

Then restart:

```bash
docker compose up -d --build
```

Open the admin page:

```text
http://192.168.1.17:8589/admin
```

Default login comes from the `.env` file.

Do not expose this publicly until the password and tokens are changed.

---

## Docker commands

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

View logs:

```bash
cd /opt/drone-relay
docker compose logs -f drone-relay
```

MediaMTX logs:

```bash
cd /opt/drone-relay
docker compose logs -f mediamtx
```

See running containers:

```bash
cd /opt/drone-relay
docker compose ps
```

---

## Admin page

The admin page is meant to be usable from my phone while I am out flying.

Admin page:

```text
http://192.168.1.17:8589/admin
```

Things I want the admin page to handle:

```text
Start stream
Stop stream
Force BRB
Return to live
Stay live
View raw drone preview
View final program preview
Upload BRB .mp4 files
Upload background .mp3 files
Pick active BRB video
Pick active MP3
Mute drone audio
Mute MP3 audio
Change MP3 volume
Set BRB delay
Set auto-end timeout
Save YouTube stream key
Save Twitch stream key for later
Save OpenWeather API key
Save Home Assistant API settings
Change location mode
Use phone location
Use ZIP override
Reset back to phone location
Apply stream presets
```

---

## DJI Fly setup

In DJI Fly, use custom RTMP streaming.

For local testing at home:

```text
rtmp://192.168.1.17:19350/live/drone
```

For remote use later, I can use Tailscale or a port-forwarded DNS name.

Tailscale example:

```text
rtmp://TAILSCALE-IP:19350/live/drone
```

Public DNS example later:

```text
rtmp://drone-ingest.example.com:19350/live/drone
```

For now, the local LAN URL is the main test URL.

---

## YouTube output

The goal is for linuxbox2 to always output:

```text
1920x1080
30 FPS
H.264
AAC audio
```

If DJI Fly sends 1080p, great.

If DJI Fly has weak cell service and sends 720p, linuxbox2 will upscale it into the 1080p program canvas before sending it to YouTube.

This does not magically make 720p look like real 1080p, but it keeps the YouTube stream and overlay layout consistent.

---

## Overlay

The overlay is generated locally on linuxbox2.

It does not depend on `drone.jimkelsey.com`.

The top bar should show:

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

Example:

```text
DUPAGE COUNTY, IL | 72°F FEELS 74° | WIND 14 MPH GUSTS 27 MPH | VIS 10 MI | CLEAR | 10:42 AM
```

The weather info updates from OpenWeather.

The clock is drawn live into the stream so it does not freeze like a screenshot clock.

BRB mode does not need the weather overlay.

---

## Media uploads

The admin page should allow browser uploads for:

```text
BRB videos: .mp4
Background audio: .mp3
```

Files are stored in:

```text
/opt/drone-relay/media/brb/
/opt/drone-relay/media/audio/
```

The admin page should let me pick which files are active.

---

## BRB behavior

Default behavior:

```text
Drone feed disappears
Wait 5 seconds
Switch to BRB video
Send notification if Home Assistant is enabled
Keep stream alive for 5 minutes
End stream if the drone feed does not come back
```

I want the notification to have quick actions:

```text
Stay Live
End Stream
```

`Stay Live` keeps the BRB stream going longer.

`End Stream` stops the stream right away.

---

## Presets

The admin page should support presets so I am not changing a bunch of settings from my phone in the field.

Presets I want:

```text
Good Signal
Low Signal
Music Stream
Silent Stream
Windy Day
Test Mode
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
Longer BRB timeout if needed

Music Stream:
Drone audio muted
MP3 on

Silent Stream:
Drone audio muted
MP3 muted

Windy Day:
Gusts emphasized
Wind alerts enabled

Test Mode:
Use previews without worrying about a real YouTube stream
```

---

## Home Assistant integration

I want Home Assistant to be able to control this because I can access HA from anywhere.

The drone relay API should be available here:

```text
http://192.168.1.17:8589/api/status
```

The API token comes from:

```text
/opt/drone-relay/.env
```

Example:

```env
DRONE_API_TOKEN=make-this-long-and-random-too
```

---

## Home Assistant REST commands

Example `configuration.yaml` or package file:

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

  drone_relay_weather_refresh:
    url: "http://192.168.1.17:8589/api/weather/refresh"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_preset_good_signal:
    url: "http://192.168.1.17:8589/api/preset/good_signal"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_preset_low_signal:
    url: "http://192.168.1.17:8589/api/preset/low_signal"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token
```

In `secrets.yaml`:

```yaml
drone_relay_api_token: your-token-from-env
```

---

## Home Assistant status sensors

Example:

```yaml
rest:
  - resource: "http://192.168.1.17:8589/api/status"
    method: GET
    headers:
      X-Drone-Token: !secret drone_relay_api_token
    scan_interval: 10
    sensor:
      - name: Drone Relay Mode
        value_template: "{{ value_json.mode }}"
      - name: Drone Relay Input
        value_template: "{{ 'connected' if value_json.input_connected else 'missing' }}"
      - name: Drone Relay Offline Seconds
        value_template: "{{ value_json.offline_seconds }}"
      - name: Drone Relay Active Preset
        value_template: "{{ value_json.active_preset }}"
```

---

## S24 actionable notifications

I want this flow:

```text
Drone feed drops
BRB starts
S24 notification appears
I can tap Stay Live or End Stream
```

Example Home Assistant automation:

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

## Home Assistant dashboard idea

I want a simple HA dashboard with:

```text
Mode
Input status
Output status
Offline seconds
Active preset
Location
Weather age
Start button
Stop button
Force BRB button
Return Live button
Stay Live button
Good Signal preset
Low Signal preset
Mute MP3
Mute Drone Audio
Refresh Weather
Reset to Moving Phone
```

This gives me a backup control panel that works anywhere I can access Home Assistant.

---

## Test without DJI Fly

After the stack is running, I can publish a fake stream from linuxbox2:

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

Press Start.

---

## Hardware checks

These are the checks I used on linuxbox2.

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

Good result includes H.264 encode support like:

```text
VAProfileH264Main : VAEntrypointEncSlice
VAProfileH264High : VAEntrypointEncSlice
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

Test 1080p30 hardware encoding:

```bash
ffmpeg -hide_banner \
  -vaapi_device /dev/dri/renderD128 \
  -f lavfi -i testsrc2=size=1920x1080:rate=30 \
  -t 20 \
  -vf 'format=nv12,hwupload' \
  -c:v h264_vaapi \
  -b:v 6000k \
  -y /tmp/drone-vaapi-test.mp4
```

This worked on linuxbox2.

---

## Docker GPU passthrough check

```bash
docker run --rm -it \
  --device /dev/dri:/dev/dri \
  ubuntu:24.04 \
  bash
```

Inside the container:

```bash
ls -lah /dev/dri
```

Good result includes:

```text
card1
renderD128
```

Exit:

```bash
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

## Notes

Do not commit real secrets.

Do not commit:

```text
.env
config/settings.json with real keys
media files I do not want public
YouTube stream keys
Twitch stream keys
Home Assistant tokens
OpenWeather API keys
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

---

## Useful cleanup commands

Stop everything:

```bash
cd /opt/drone-relay
docker compose down
```

Rebuild:

```bash
cd /opt/drone-relay
docker compose up -d --build
```

View logs:

```bash
cd /opt/drone-relay
docker compose logs -f
```

Remove old test output:

```bash
rm -f /tmp/drone-vaapi-test.mp4
```

---

## Current plan

Use linuxbox2 as the main host.

Keep this separate from AzuraCast.

Use Docker so it is easy to move later if needed.

Start simple:

```text
RTMP ingest
Admin page
YouTube output
BRB fallback
MP3 loop
Weather overlay
Home Assistant controls
S24 actionable notifications
```

Then improve it after the first real test flight.
