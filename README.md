# Drone Relay Docker

Docker-based drone relay for `linuxbox2` at `192.168.1.17`.

This receives a DJI Fly RTMP stream, builds a final 1080p program feed with weather/clock overlay, supports BRB fallback, and can push to YouTube/Twitch when I turn that on.

V7 focus:

```text
Cleaner phone/PC dashboard
Dry testing without DJI ingest
Working WebRTC preview if MediaMTX has a program stream
Scanner audio URL from .env
AzuraCast audio URL from .env
Program output URL for VLC/OBS
```

---

## Deploy clean on linuxbox2

Upload this repo to GitHub, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

The installer removes the old Drone Relay setup only. It does not stop AzuraCast, Portainer, DJMIXHUB, or other Docker stacks.

---

## Add keys and audio links in `.env`

```bash
cd /opt/drone-relay
nano .env
```

Important values:

```env
OPENWEATHER_API_KEY=
YOUTUBE_STREAM_KEY=
TWITCH_STREAM_KEY=

# Optional audio sources
SCANNER_STREAM_URL=
AZURACAST_STREAM_URL=
```

Scanner example later:

```env
SCANNER_STREAM_URL=http://192.168.1.7/something.mp3
```

AzuraCast example later:

```env
AZURACAST_STREAM_URL=http://192.168.1.17/listen/djmixhub/radio.mp3
```

Restart after editing:

```bash
docker compose up -d --build
```

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

## Dry testing

These do not need DJI Fly ingest and do not push to YouTube/Twitch:

```text
Test Pattern
Test BRB
Test Audio
```

Use them first inside the house.

Start with:

```text
1. Upload/select BRB MP4
2. Upload/select MP3 or select Scanner/AzuraCast source
3. Keep Local Test Mode ON
4. Press Test Pattern
5. Press Test BRB
6. Press Test Audio
```

---

## Preview / VLC / OBS URLs

DJI Fly ingest:

```text
rtmp://192.168.1.17:19350/live/drone
```

Raw drone preview:

```text
http://192.168.1.17:8889/live/drone
http://192.168.1.17:8888/live/drone/index.m3u8
```

Final program preview/output:

```text
http://192.168.1.17:8889/live/program
http://192.168.1.17:8888/live/program/index.m3u8
rtmp://192.168.1.17:19350/live/program
```

For OBS on `desktop1`, use this first as a Media Source or VLC source:

```text
http://192.168.1.17:8888/live/program/index.m3u8
```

If the embedded admin preview is blank, press a dry-test button first, wait a few seconds, then hit Reload Previews.

---

## Audio source options

The dashboard has one main Program Audio source selector:

```text
Uploaded MP3
Scanner feed from .env
AzuraCast feed from .env
Silent
```

The URLs stay in `.env`, not the browser.

BRB MP4 audio has its own mute/volume controls.

---

## Local Test Mode

Keep this ON while testing.

When ON:

```text
Final program preview works
YouTube output is blocked
Twitch output is blocked
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
