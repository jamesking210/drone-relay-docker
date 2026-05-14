#!/usr/bin/env bash
set -euo pipefail

# Drone Relay Docker V9 clean installer for linuxbox2.
#
# Deploy:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
#   cd /opt/drone-relay
#   nano .env
#   docker compose up -d --build
#
# This intentionally resets /opt/drone-relay for clean testing.
# It only touches the Drone Relay app folder/containers.
# It does NOT stop AzuraCast, Portainer, DJMIXHUB, or other Docker stacks.

OWNER="${OWNER:-jamesking210}"
REPO="${REPO:-drone-relay-docker}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/drone-relay}"
INSTALL_DOCKER="${INSTALL_DOCKER:-1}"
NO_START="${NO_START:-0}"

ZIP_URL="https://github.com/${OWNER}/${REPO}/archive/refs/heads/${BRANCH}.zip"
TMP_DIR="$(mktemp -d)"
DOCKER_CMD="docker"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

say() {
  printf '\n==> %s\n' "$*"
}

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

say "Drone Relay Docker V9 deploy"
echo "Repo:        ${OWNER}/${REPO}"
echo "Branch:      ${BRANCH}"
echo "Install dir: ${APP_DIR}"

say "Installing host requirements"
run_root apt-get update -y
run_root apt-get install -y ca-certificates curl unzip rsync tar

if ! command -v docker >/dev/null 2>&1; then
  if [ "$INSTALL_DOCKER" = "1" ]; then
    say "Docker not found. Installing Docker."
    curl -fsSL https://get.docker.com | run_root sh
  else
    echo "Docker not installed and INSTALL_DOCKER=0 was set." >&2
    exit 1
  fi
fi

if docker ps >/dev/null 2>&1; then
  DOCKER_CMD="docker"
elif sudo docker ps >/dev/null 2>&1; then
  DOCKER_CMD="sudo docker"
else
  echo "Docker exists but cannot be used by this user." >&2
  exit 1
fi

if ! $DOCKER_CMD compose version >/dev/null 2>&1; then
  run_root apt-get install -y docker-compose-plugin || true
fi

say "Stopping old Drone Relay containers only"
if [ -f "${APP_DIR}/docker-compose.yml" ]; then
  (cd "$APP_DIR" && $DOCKER_CMD compose down --remove-orphans) || true
fi

$DOCKER_CMD rm -f drone-relay drone-mediamtx >/dev/null 2>&1 || true

say "Removing old ${APP_DIR}"
run_root rm -rf "$APP_DIR"
run_root mkdir -p "$APP_DIR"
run_root chown -R "$USER":"$USER" "$APP_DIR"

say "Downloading public GitHub ZIP"
curl -fL "$ZIP_URL" -o "$TMP_DIR/source.zip"
unzip -q "$TMP_DIR/source.zip" -d "$TMP_DIR"

SRC_DIR="$TMP_DIR/${REPO}-${BRANCH}"

if [ ! -f "$SRC_DIR/docker-compose.yml" ]; then
  echo "Could not find docker-compose.yml in downloaded repo." >&2
  echo "Make sure the project files are at the root of the GitHub repo." >&2
  exit 1
fi

say "Copying project files"
rsync -a "$SRC_DIR/" "$APP_DIR/"

cd "$APP_DIR"

mkdir -p config media/brb media/audio overlay logs

say "Creating fresh .env from .env.example"
cp -f .env.example .env

if [ ! -f config/settings.json ] && [ -f config/settings.example.json ]; then
  cp config/settings.example.json config/settings.json
fi

if [ "$NO_START" = "1" ]; then
  say "NO_START=1 set. Files installed but containers not started."
else
  say "Building and starting Drone Relay"
  $DOCKER_CMD compose up -d --build
fi

say "Done"
echo
echo "Next:"
echo "  cd ${APP_DIR}"
echo "  nano .env"
echo "  ${DOCKER_CMD} compose up -d --build"
echo
echo "Admin:"
echo "  http://192.168.1.17:8589/admin"
echo
echo "DJI Fly ingest:"
echo "  rtmp://192.168.1.17:19350/live/drone"
echo
echo "Program output for VLC/OBS:"
echo "  http://192.168.1.17:8888/live/program/index.m3u8"
echo "  rtmp://192.168.1.17:19350/live/program"
