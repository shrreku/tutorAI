#!/usr/bin/env bash
set -euo pipefail

: "${APP_IMAGE_TAG:?APP_IMAGE_TAG is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${GHCR_TOKEN:?GHCR_TOKEN is required}"
: "${IMAGE_PREFIX:?IMAGE_PREFIX is required}"

export REGISTRY="${REGISTRY:-ghcr.io}"
export IMAGE_PREFIX
export IMAGE_PREFIX_LOWER="${IMAGE_PREFIX,,}"
export APP_IMAGE_TAG

if ! [[ "$APP_IMAGE_TAG" =~ ^[a-f0-9]{40}$|^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]]; then
	echo "APP_IMAGE_TAG must be a git SHA or semver-like release tag; got: $APP_IMAGE_TAG" >&2
	exit 1
fi

echo "$GHCR_TOKEN" | docker login "$REGISTRY" -u "$GHCR_USERNAME" --password-stdin

docker container prune -f
docker image prune -a -f
docker builder prune -a -f

docker compose -f docker-compose.prod.yml pull api worker migrate

docker compose -f docker-compose.prod.yml run --rm migrate

docker compose -f docker-compose.prod.yml up -d api worker

docker compose -f docker-compose.prod.yml ps

docker container prune -f
docker image prune -f
docker builder prune -f

echo "Deploy finished for image tag: $APP_IMAGE_TAG"
