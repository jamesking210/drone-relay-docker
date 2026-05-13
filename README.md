# Drone Relay Docker

Docker-based drone stream relay for `linuxbox2`.

This package receives an RTMP stream from DJI Fly, builds a 1080p30 program feed with a local weather/clock top bar, loops optional MP3 background audio, switches to a BRB video when the drone feed drops, and pushes the final program to YouTube with optional Twitch support later.

Confirmed target host:

```text
linuxbox2: 192.168.1.17
i5-6500 / 24GB RAM / Ubuntu Desktop 24.04
Intel HD Graphics 530
VAAPI hardware H.264 encoding working
Docker / Portainer friendly
```

## Final ports

These were chosen to avoid your current AzuraCast, DJMIXHUB, OBS overlay, and Portainer ports.

```text
8589   Drone Relay admin page
19350  DJI Fly RTMP ingest
8888   HLS preview
8889   WebRTC preview
9997   MediaMTX API, bound to 127.0.0.1 only by default
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

## What this package includes

```text
mediamtx
  RTMP ingest from DJI Fly
  HLS/WebRTC preview outputs
  RTMP program preview path

drone-relay
  Mobile-first admin page
  Browser upload for BRB .mp4 files
  Browser upload for background .mp3 files
  File selectors for active BRB and active MP3
  OpenWeather settings
  Home Assistant API settings
  YouTube stream key field
  Twitch stream key field for later
  Presets
  S24/Home Assistant notification support
  Watchdog for feed drop / BRB / auto-end
  FFmpeg VAAPI 1080p30 output
```

## One-line deploy after you upload this repo to GitHub

Replace the repo URL with your real GitHub repo.

```bash
REPO_URL=https://github.com/YOUR_GITHUB/drone-relay-docker.git APP_DIR=/opt/drone-relay bash -c "curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB/drone-relay-docker/main/deploy.sh | bash"
```

If you clone manually instead:

```bash
git clone https://github.com/YOUR_GITHUB/drone-relay-docker.git /opt/drone-relay
cd /opt/drone-relay
cp .env.example .env
nano .env
docker compose up -d --build
```

## Deploy from the ZIP manually

```bash
sudo mkdir -p /opt/drone-relay
sudo chown $USER:$USER /opt/drone-relay
unzip drone-relay-docker.zip -d /opt/drone-relay-temp
cp -a /opt/drone-relay-temp/drone-relay-docker/. /opt/drone-relay/
cd /opt/drone-relay
cp .env.example .env
nano .env
docker compose up -d --build
```

Open:

```text
http://192.168.1.17:8589/admin
```

Default login comes from `.env`:

```text
admin / change-me-now
```

Change it before exposing the page through port forwarding, Cloudflare Tunnel, or Tailscale Funnel.

## First-time setup checklist

### 1. Edit `.env`

```bash
cd /opt/drone-relay
nano .env
```

Change these:

```env
ADMIN_PASSWORD=make-this-private
FLASK_SECRET_KEY=make-this-long-and-random
DRONE_API_TOKEN=make-this-long-and-random-too
```

### 2. Start containers

```bash
docker compose up -d --build
```

### 3. Watch logs

```bash
docker compose logs -f drone-relay
```

### 4. Open admin page

```text
http://192.168.1.17:8589/admin
```

### 5. Add OpenWeather key

Admin page → Quick Settings → OpenWeather API Key → Save Settings → Refresh Weather.

### 6. Upload media

Admin page → Media Uploads:

```text
Upload BRB .mp4
Upload background .mp3
Select active BRB
Select active MP3
```

### 7. Add YouTube stream key

Admin page → Destinations:

```text
YouTube enabled: on
YouTube RTMP URL: rtmps://a.rtmps.youtube.com/live2
YouTube Stream Key: your-key-here
```

Save.

## DJI Fly setup

In DJI Fly, use custom RTMP streaming and enter:

```text
rtmp://192.168.1.17:19350/live/drone
```

For remote field use, use either:

```text
rtmp://TAILSCALE-IP:19350/live/drone
```

or a port-forwarded/public DNS name later:

```text
rtmp://your-domain-or-public-ip:19350/live/drone
```

## Recommended stream presets

The admin page includes these presets:

```text
Good Signal
Low Signal
Silent Stream
Music Stream
Windy Day
Test Mode
```

Suggested use:

```text
Good Signal: DJI sends 1080p, NUC outputs 1080p30 around 7000k
Low Signal: DJI sends 720p, NUC upscales to 1080p30 around 4500k
Music Stream: drone audio muted, MP3 loop on
Silent Stream: drone audio muted, MP3 muted
Windy Day: gusts emphasized in weather overlay
```

## What happens when the drone feed drops

Default behavior:

```text
Drone feed missing for 5 seconds
→ switch to BRB
→ send S24/Home Assistant actionable notification if enabled
→ keep BRB live for 5 minutes
→ send warning near final 60 seconds
→ auto-end stream if no action is taken
```

Buttons supported through Home Assistant notification automation:

```text
Stay Live
End Stream
```

`Stay Live` extends the BRB timer.

`End Stream` stops FFmpeg and ends YouTube/Twitch output immediately.

## Home Assistant integration

The drone relay exposes API endpoints for Home Assistant.

Use the `DRONE_API_TOKEN` value from `.env`.

### REST commands

Add something like this to Home Assistant `configuration.yaml` or split package file:

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

  drone_relay_preset_low_signal:
    url: "http://192.168.1.17:8589/api/preset/low_signal"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_preset_good_signal:
    url: "http://192.168.1.17:8589/api/preset/good_signal"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token

  drone_relay_weather_refresh:
    url: "http://192.168.1.17:8589/api/weather/refresh"
    method: POST
    headers:
      X-Drone-Token: !secret drone_relay_api_token
```

In `secrets.yaml`:

```yaml
drone_relay_api_token: your-token-from-env
```

### Status sensor

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

### Actionable notification handler

The drone relay can send the notification through Home Assistant if you enter your HA URL, long-lived token, and notify service in the admin page.

Add this automation so the S24 notification buttons do something:

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

## Home Assistant dashboard idea

Use button cards or entities for:

```text
Mode
Input status
Offline seconds
Active preset
Start
Stop
Force BRB
Return Live
Stay Live
Good Signal preset
Low Signal preset
Refresh Weather
```

Because Home Assistant is already accessible remotely, this becomes your field dashboard.

## Test without DJI Fly

You can publish a fake test stream into MediaMTX from linuxbox2:

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

Press `Start`.

## Check hardware passthrough

You already confirmed this on linuxbox2, but the useful commands are:

```bash
ls -lah /dev/dri
vainfo
ffmpeg -hide_banner -encoders | grep -E "h264_vaapi|h264_qsv"
```

Expected:

```text
renderD128 exists
h264_vaapi exists
```

Docker passthrough test:

```bash
docker run --rm -it --device /dev/dri:/dev/dri ubuntu:24.04 bash
ls -lah /dev/dri
exit
```

## Check port conflicts

```bash
sudo ss -ltnp | grep -E ':8589|:19350|:8888|:8889|:9997'
```

No output means the ports are clear.

## Notes and limits for v1

- The final program always targets 1080p30.
- If DJI sends 720p, FFmpeg scales/pads it into the 1080p program canvas.
- The BRB video does not get the weather overlay.
- Weather text updates from OpenWeather on the NUC, not from `drone.jimkelsey.com`.
- The clock is drawn live by FFmpeg, so it does not freeze like a screenshot clock.
- `9997` is bound to `127.0.0.1` on the host by default for safety.
- Do not commit `.env` or `config/settings.json` to GitHub with real keys.

## Useful commands

```bash
cd /opt/drone-relay

docker compose ps
docker compose logs -f drone-relay
docker compose logs -f mediamtx
docker compose restart drone-relay
docker compose down
docker compose up -d --build
```
