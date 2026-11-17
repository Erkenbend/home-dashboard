#!/usr/bin/env bash
# Build the arm64 image locally (WSL), ship it to the Pi via SSH and (re)start it there.
#
# Usage: scripts/deploy.sh [user@host]      (default: $DEPLOY_HOST)
#
# Prerequisites:
#   - local: Docker with buildx and arm64 emulation
#       (once: docker run --privileged --rm tonistiigi/binfmt --install arm64)
#   - Pi: Docker + compose plugin, SSH key login, user in group "docker"
#
# Configuration: if a local config.yaml exists (gitignored), it is validated and uploaded to
# ~/home-dashboard/config.yaml on the Pi, overwriting the remote one. Without a local config.yaml the
# remote one is kept and must exist.
set -euo pipefail

HOST="${1:-${DEPLOY_HOST:-}}"
if [[ -z "$HOST" ]]; then
  echo "usage: scripts/deploy.sh user@host   (or set DEPLOY_HOST=user@host)" >&2
  exit 2
fi
REMOTE_DIR="home-dashboard"   # relative to the remote user's home
PORT=3274

cd "$(dirname "$0")/.."

TAG="$(git rev-parse --short HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then
  TAG="${TAG}-dirty"
  echo "warning: working tree has uncommitted changes, deploying as ${TAG}" >&2
fi
IMAGE="home-dashboard:${TAG}"

if [[ -f config.yaml ]]; then
  echo "==> Validating local config.yaml"
  uv run --quiet home-dashboard check-config config.yaml
  UPLOAD_CONFIG=1
  REMOTE_CHECK="true"
else
  echo "==> No local config.yaml, keeping the one on the Pi"
  UPLOAD_CONFIG=0
  REMOTE_CHECK="test -f ${REMOTE_DIR}/config.yaml"
fi

echo "==> Checking remote prerequisites on ${HOST}"
ssh "$HOST" "docker compose version >/dev/null && mkdir -p ${REMOTE_DIR} && ${REMOTE_CHECK}" || {
  echo "error: remote needs docker compose and ~/${REMOTE_DIR}/config.yaml (see config.example.yaml)" >&2
  exit 1
}

echo "==> Building ${IMAGE} for linux/arm64"
docker buildx build --platform linux/arm64 --tag "$IMAGE" --tag home-dashboard:latest --load .

echo "==> Transferring image"
docker save "$IMAGE" home-dashboard:latest | gzip -1 | ssh "$HOST" "gunzip | docker load"

if [[ "$UPLOAD_CONFIG" == 1 ]]; then
  echo "==> Uploading config.yaml"
  scp -q config.yaml "${HOST}:${REMOTE_DIR}/config.yaml.new"
  ssh "$HOST" "chmod 600 ${REMOTE_DIR}/config.yaml.new && mv ${REMOTE_DIR}/config.yaml.new ${REMOTE_DIR}/config.yaml"
fi

echo "==> Starting container"
scp -q compose.yaml "${HOST}:${REMOTE_DIR}/compose.yaml"
# --force-recreate: the config is only read at startup, so always start a fresh container
ssh "$HOST" "cd ${REMOTE_DIR} && TAG=${TAG} docker compose up -d --force-recreate --remove-orphans && docker image prune -f >/dev/null"

echo "==> Waiting for health check"
REMOTE_ADDR="${HOST#*@}"
for _ in $(seq 1 30); do
  if curl -fsS "http://${REMOTE_ADDR}:${PORT}/healthz" >/dev/null 2>&1; then
    echo "==> Deployed ${TAG}: http://${REMOTE_ADDR}:${PORT}/"
    exit 0
  fi
  sleep 2
done
echo "error: health check failed, see: ssh ${HOST} 'cd ${REMOTE_DIR} && docker compose logs'" >&2
exit 1
