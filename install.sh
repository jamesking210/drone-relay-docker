#!/usr/bin/env bash
set -euo pipefail

# Drone Relay Docker installer / updater
#
# Normal install/update:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | bash
#
# Reset .env from latest .env.example:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | RESET_ENV=1 bash
#
# Testing cleanup: stop/remove old drone-relay containers before reinstall:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | CLEAN=1 bash
#
# Hard reset for testing: stop stack, remove old app files, reinstall, reset .env:
#   curl -fsSL https://raw.githubusercontent.com/jamesking210/drone-relay-docker/main/install.sh | RESET_APP=1 RESET_ENV=1 bash
#
# This only targets APP_DIR, default /opt/drone-relay.
# It does not stop AzuraCast, Portainer, DJMIXHUB, or other Docker stacks.

OWNER="${OWNER:-jamesking210}"
REPO="${REPO:-drone-relay-docker}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/drone-relay}"

# Options:
# RESET_ENV=1    Backup .env and replace it with .env.example after download.
# CLEAN=1        Run docker compose down --remove-orphans before update.
# RESET_APP=1    Backup then delete APP_DIR before fresh install.
# NO_START=1     Install files but do not start containers.
# INSTALL_DOCKER=0 prevents auto Docker install.
RESET_ENV="${RESET_ENV:-0}"
CLEAN="${CLEAN:-0}"
RESET_APP="${RESET_APP:-0}"
NO_START="${NO_START:-0}"
INSTALL_DOCKER="${INSTALL_DOCKER:-1}"

ZIP_URL="https://github.com/${OWNER}/${REPO}/archive/refs/heads/${BRANCH}.zip"
TMP_DIR="$(mktemp -d)"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/drone-relay-backups}"
DOCKER_CMD="docker"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

say() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf '\n!! %s\n' "$*" >&2
}

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

compose_in_app() {
  if [ -f "${APP_DIR}/docker-compose.yml" ]; then
    (cd "$APP_DIR" && $DOCKER_CMD compose "$@")
  fi
}

backup_current_app_bits() {
  mkdir -p "$BACKUP_ROOT"

  if [ -d "$APP_DIR" ]; then
    local stamp
    stamp="$(date +%Y%m%d-%H%M%S)"
    local backup_file="${BACKUP_ROOT}/drone-relay-backup-${stamp}.tar.gz"

    say "Backing up current local data"
    echo "Backup: $backup_file"

    (
      cd "$APP_DIR"
      tar -czf "$backup_file" \
        .env \
        config \
        media \
        overlay \
        logs \
        2>/dev/null || true
    )
  fi
}

download_repo_zip() {
  say "Downloading project ZIP from public GitHub"
  echo "Repo:     ${OWNER}/${REPO}"
  echo "Branch:   ${BRANCH}"
  echo "ZIP URL:  ${ZIP_URL}"

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
    echo "Make sure the full project files are uploaded to the repo root, not nested inside another folder." >&2
    exit 1
  fi
}

install_host_packages() {
  say "Installing required host packages"
  run_root apt-get update -y
  run_root apt-get install -y ca-certificates curl unzip rsync tar
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    if [ "$INSTALL_DOCKER" = "1" ]; then
      say "Docker not found. Installing Docker using Docker's official installer."
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
    echo "Try adding your user to docker group, then log out/in:" >&2
    echo "  sudo usermod -aG docker $USER" >&2
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
}

stop_existing_stack_if_needed() {
  if [ -f "${APP_DIR}/docker-compose.yml" ]; then
    if [ "$CLEAN" = "1" ] || [ "$RESET_APP" = "1" ]; then
      say "Stopping old Drone Relay stack"
      compose_in_app down --remove-orphans || true
    else
      say "Leaving old stack running during file update"
      echo "Tip: use CLEAN=1 to stop/remove the old drone-relay containers before updating."
    fi
  fi
}

reset_app_dir_if_needed() {
  if [ "$RESET_APP" = "1" ] && [ -d "$APP_DIR" ]; then
    say "RESET_APP=1 set, removing old ${APP_DIR} after backup"
    run_root rm -rf "$APP_DIR"
  fi
}

install_files() {
  say "Installing/updating files in ${APP_DIR}"
  run_root mkdir -p "$APP_DIR"
  run_root chown -R "$USER":"$USER" "$APP_DIR"

  # Preserve local secrets/config/media/logs unless RESET_ENV handles .env below.
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
}

handle_env_file() {
  cd "$APP_DIR"

  if [ "$RESET_ENV" = "1" ]; then
    say "RESET_ENV=1 set, replacing .env from .env.example"
    if [ -f ".env" ]; then
      cp -a .env ".env.backup.$(date +%Y%m%d-%H%M%S)"
      echo "Old .env backed up inside ${APP_DIR}"
    fi
    cp -f .env.example .env
    warn "Your .env was reset. You must edit it and add real keys/passwords."
    NEED_ENV_EDIT=1
    return
  fi

  if [ ! -f ".env" ]; then
    say "No .env found. Creating one from .env.example"
    cp .env.example .env
    warn "New .env created. You must edit it and add real keys/passwords."
    NEED_ENV_EDIT=1
  else
    NEED_ENV_EDIT=0
  fi

  if [ ! -f "config/settings.json" ] && [ -f "config/settings.example.json" ]; then
    cp config/settings.example.json config/settings.json
  fi
}

start_stack() {
  cd "$APP_DIR"

  if [ "$NO_START" = "1" ]; then
    say "NO_START=1 set, not starting containers"
    return
  fi

  say "Starting Drone Relay Docker stack"
  $DOCKER_CMD compose up -d --build
}

print_done() {
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

  if [ "${NEED_ENV_EDIT:-0}" = "1" ]; then
    echo "NEXT STEP:"
    echo "  cd ${APP_DIR}"
    echo "  nano .env"
    echo
    echo "After editing .env:"
    echo "  ${DOCKER_CMD} compose up -d --build"
    echo
  fi
}

say "Drone Relay Docker installer"
echo "Install dir: ${APP_DIR}"
echo "Options: RESET_ENV=${RESET_ENV} CLEAN=${CLEAN} RESET_APP=${RESET_APP} NO_START=${NO_START}"

install_host_packages
ensure_docker
backup_current_app_bits
stop_existing_stack_if_needed
reset_app_dir_if_needed
download_repo_zip
install_files
handle_env_file
start_stack
print_done
