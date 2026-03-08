#!/usr/bin/env bash
set -euo pipefail

: "${APP_IMAGE_TAG:?APP_IMAGE_TAG is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${GHCR_TOKEN:?GHCR_TOKEN is required}"
: "${IMAGE_PREFIX:?IMAGE_PREFIX is required}"

export REGISTRY="${REGISTRY:-ghcr.io}"
export IMAGE_PREFIX
export APP_IMAGE_TAG

echo "$GHCR_TOKEN" | docker login "$REGISTRY" -u "$GHCR_USERNAME" --password-stdin

docker compose -f docker-compose.prod.yml pull api worker migrate

docker compose -f docker-compose.prod.yml run --rm migrate

docker compose -f docker-compose.prod.yml up -d api worker

docker image prune -f

echo "Deploy finished for image tag: $APP_IMAGE_TAG"
