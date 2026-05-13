#!/usr/bin/env bash
set -euo pipefail

# Drone Relay Docker - public GitHub ZIP installer
# No git clone. No GitHub username. No GitHub token.
#
# Default one-line install:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
#
# Optional overrides:
#   OWNER=jamesking210 REPO=drone-relay-docker BRANCH=main APP_DIR=/opt/drone-relay bash install.sh

OWNER="${OWNER:-jamesking210}"
REPO="${REPO:-drone-relay-docker}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/drone-relay}"
INSTALL_DOCKER="${INSTALL_DOCKER:-1}"

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

say "Drone Relay Docker installer"
echo "Repo:        ${OWNER}/${REPO}"
echo "Branch:      ${BRANCH}"
echo "Install dir: ${APP_DIR}"
echo "Download:    ${ZIP_URL}"

say "Installing required host packages"
run_root apt-get update -y
run_root apt-get install -y ca-certificates curl unzip rsync

if ! command -v docker >/dev/null 2>&1; then
  if [ "$INSTALL_DOCKER" = "1" ]; then
    say "Docker not found. Installing Docker using Docker's official convenience installer."
    curl -fsSL https://get.docker.com | run_root sh
  else
    echo "Docker is not installed and INSTALL_DOCKER=0 was set." >&2
    exit 1
  fi
fi

if docker ps >/dev/null 2>&1; then
  DOCKER_CMD="docker"
elif sudo docker ps >/dev/null 2>&1; then
  DOCKER_CMD="sudo docker"
else
  echo "Docker exists, but this user cannot run docker and sudo docker failed." >&2
  exit 1
fi

if ! $DOCKER_CMD compose version >/dev/null 2>&1; then
  say "Docker Compose plugin missing. Installing docker-compose-plugin if available."
  run_root apt-get install -y docker-compose-plugin || true
fi

if ! $DOCKER_CMD compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is still not available." >&2
  echo "Try: sudo apt-get install -y docker-compose-plugin" >&2
  exit 1
fi

say "Downloading project ZIP from public GitHub"
curl -fL "$ZIP_URL" -o "$TMP_DIR/source.zip"
unzip -q "$TMP_DIR/source.zip" -d "$TMP_DIR"

SRC_DIR="$TMP_DIR/${REPO}-${BRANCH}"

if [ ! -d "$SRC_DIR" ]; then
  echo "Downloaded ZIP did not contain expected folder: ${REPO}-${BRANCH}" >&2
  echo "Check OWNER, REPO, and BRANCH." >&2
  exit 1
fi

if [ ! -f "$SRC_DIR/docker-compose.yml" ]; then
  echo "Could not find docker-compose.yml in downloaded repo." >&2
  echo "Make sure the full project files are uploaded to GitHub root, not nested inside another folder." >&2
  exit 1
fi

say "Installing/updating files in ${APP_DIR}"
run_root mkdir -p "$APP_DIR"
run_root chown -R "$USER":"$USER" "$APP_DIR"

# Preserve local secrets/config/media/logs across updates.
rsync -a --delete \
  --exclude ".git/" \
  --exclude ".env" \
  --exclude "config/settings.json" \
  --exclude "media/" \
  --exclude "logs/" \
  --exclude "overlay/weather.png" \
  "$SRC_DIR/" "$APP_DIR/"

cd "$APP_DIR"

mkdir -p config media/brb media/audio overlay logs

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    say "Created .env from .env.example"
  else
    echo "WARNING: .env.example was not found. You may need to create .env manually." >&2
  fi
fi

if [ ! -f "config/settings.json" ] && [ -f "config/settings.example.json" ]; then
  cp config/settings.example.json config/settings.json
fi

say "Starting Docker stack"
$DOCKER_CMD compose up -d --build

say "Deployment complete"
echo
echo "Admin page:"
echo "  http://192.168.1.17:8589/admin"
echo
echo "DJI Fly RTMP ingest:"
echo "  rtmp://192.168.1.17:19350/live/drone"
echo
echo "Useful commands:"
echo "  cd ${APP_DIR}"
echo "  ${DOCKER_CMD} compose ps"
echo "  ${DOCKER_CMD} compose logs -f drone-relay"
echo
echo "Default admin login comes from .env:"
echo "  admin / change-me-now"
echo
echo "IMPORTANT:"
echo "  Edit ${APP_DIR}/.env and change ADMIN_PASSWORD, FLASK_SECRET_KEY, and DRONE_API_TOKEN."
echo "  Then run: cd ${APP_DIR} && ${DOCKER_CMD} compose up -d --build"
