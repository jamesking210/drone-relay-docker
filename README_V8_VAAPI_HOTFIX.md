# V8 VAAPI Hotfix

This hotfix fixes the current problem where Test Pattern starts, but FFmpeg crashes with:

```text
Failed to initialise VAAPI connection
Failed to set value '/dev/dri/renderD128' for option 'vaapi_device'
```

Your logs show DJI/phone ingest is working. MediaMTX says:

```text
[path live/drone] stream is available and online, 2 tracks (H264, MPEG-4 Audio)
```

The broken part is the final program output because FFmpeg inside the `drone-relay` container cannot initialize VAAPI.

## Files changed

Upload these two files to GitHub:

```text
app/Dockerfile
docker-compose.yml
```

## Deploy

```bash
curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
cd /opt/drone-relay
nano .env
docker compose up -d --build
```

## Test VAAPI inside the container

After rebuild:

```bash
cd /opt/drone-relay
docker compose exec drone-relay vainfo --display drm --device /dev/dri/renderD128
```

If that works, press:

```text
Test Pattern
```

Then open:

```text
http://192.168.1.17:8888/live/program/index.m3u8
```

or:

```text
rtmp://192.168.1.17:19350/live/program
```

## Notes

The `curl -i -X POST /api/test-pattern` returning 401 is normal unless you include the API token or are logged in through the browser.

The MediaMTX API returning authentication error is not the main issue for program output. The main issue from the logs is VAAPI failing inside the app container.
