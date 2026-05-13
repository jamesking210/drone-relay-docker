#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/drone-relay}"
REPO_URL="${REPO_URL:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker first, then rerun this script." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is not available. Install docker compose first." >&2
  exit 1
fi

if [ -n "$REPO_URL" ]; then
  if [ ! -d "$APP_DIR/.git" ]; then
    sudo mkdir -p "$(dirname "$APP_DIR")"
    sudo chown "$USER":"$USER" "$(dirname "$APP_DIR")"
    git clone "$REPO_URL" "$APP_DIR"
  else
    cd "$APP_DIR"
    git pull
  fi
else
  if [ ! -f "docker-compose.yml" ]; then
    echo "Run this script from the project folder, or set REPO_URL=https://github.com/jamesking210/drone-relay-docker.git" >&2
    exit 1
  fi
  APP_DIR="$(pwd)"
fi

cd "$APP_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
  echo "IMPORTANT: edit .env and change ADMIN_PASSWORD, FLASK_SECRET_KEY, and DRONE_API_TOKEN."
fi

mkdir -p config media/brb media/audio overlay logs

docker compose up -d --build

echo
echo "Drone Relay deployed."
echo "Admin: http://192.168.1.17:8589/admin"
echo "DJI Fly ingest: rtmp://192.168.1.17:19350/live/drone"
echo "Logs: docker compose logs -f drone-relay"
