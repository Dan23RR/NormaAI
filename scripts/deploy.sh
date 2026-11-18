#!/usr/bin/env bash
# ============================================================================
# NormaAI - deploy one commit of main on the production server.
#
# Run as the non-root deploy user (scripts/bootstrap_hetzner.sh creates it,
# docs/DEPLOY_CHECKLIST.md step 6), never as root:
#
#   bash scripts/deploy.sh <commit> <image>   the image GitHub built and tested,
#                                             ghcr.io/<owner>/<repo>@sha256:<digest>
#   bash scripts/deploy.sh <commit> build     fallback: build the image here
#
# From GitHub (.github/workflows/deploy.yml) the deploy key may run nothing
# else: its line in ~deploy/.ssh/authorized_keys has
#   restrict,command="bash /opt/normaai/scripts/deploy.sh --ssh"
# and the words GitHub sends ("deploy <commit> <image|build> <user>") arrive in
# SSH_ORIGINAL_COMMAND; a token to read the image from GHCR arrives on stdin.
#
# What it does, in this order, and why the outage is short:
#   1. checks that the commit is on origin/main (a stolen key can deploy only
#      what is already on GitHub's main) and checks it out, exactly;
#   2. the image: pulled by digest, while the old app keeps serving, and
#      checked: its labels must name the commit and the EMBEDDING_MODEL of
#      .env (an image without the configured model cannot start offline);
#      with "build", built here as before (2.1 GB of model with e5, minutes);
#   3. migrations as the owner of the schema, in the one-shot `migrate`
#      service, while the old app keeps serving (they are additive);
#   4. recreates the app container alone (docker compose up --no-deps): the
#      API is down from here until the new container is healthy, the time it
#      takes to load the model (31-90 s with e5);
#   5. waits for the container's healthcheck; when the new app does not become
#      healthy, puts the previous image back and fails;
#   6. writes NORMAAI_IMAGE to .env (what `docker compose up` runs from now
#      on), reloads Caddy when infra/Caddyfile changed, removes old images.
#
# Settings (environment): APP_DIR (default: this checkout), DEPLOY_HEALTH_TIMEOUT
# (seconds, default 420), APP_CONTAINER (default normaai-app).
# Exit status: 0 when the new commit serves, 1 otherwise.
# ============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
APP_CONTAINER="${APP_CONTAINER:-normaai-app}"
HEALTH_TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-420}"
LOCAL_IMAGE="normaai-app"
# The model the code uses when .env names none (src/config.py).
DEFAULT_EMBEDDING_MODEL="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

# The commit to put back when the deploy fails after the checkout moved.
RESTORE_SHA=""

log() { printf '[deploy] %s\n' "$*"; }
die() {
  printf '[deploy] FAIL: %s\n' "$*" >&2
  exit 1
}

# The value of one setting in .env, as compose reads it (the last line wins).
env_value() {
  local line
  line="$(grep -E "^$1=" .env 2> /dev/null | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  printf '%s' "$line"
}

# Writes NAME=VALUE in .env, replacing the line when there is one.
set_env_value() { # <name> <value>
  local tmp
  tmp="$(mktemp .env.XXXXXX)"
  grep -v -E "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" .env
}

# ghcr.io/<owner>/<repo>, lowercase, from the origin of this checkout: the only
# image repository a deploy may pull from.
image_repository() {
  local url path
  url="$(git remote get-url origin)"
  path="${url%.git}"
  path="${path#*github.com[:/]}"
  printf 'ghcr.io/%s' "$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')"
}

label() { # <image> <label>
  docker image inspect -f "{{ index .Config.Labels \"$2\" }}" "$1" 2> /dev/null || true
}

health() {
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "$APP_CONTAINER" 2> /dev/null || echo missing
}

wait_healthy() {
  local waited=0 status
  while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
    status="$(health)"
    case "$status" in
      healthy) return 0 ;;
      unhealthy | missing) [ "$waited" -lt 30 ] || return 1 ;;
    esac
    sleep 5
    waited=$((waited + 5))
  done
  return 1
}

pull_image() { # <image> <github user or empty>
  local token="" config
  if [ ! -t 0 ]; then
    IFS= read -r -t 10 token || true
    token="${token%$'\r'}"
  fi
  if [ -n "$token" ] && [ -n "$2" ]; then
    # A throwaway docker configuration: the token, valid only while the GitHub
    # job runs, is not written to the deploy user's own one.
    config="$(mktemp -d)"
    if ! printf '%s' "$token" | DOCKER_CONFIG="$config" docker login ghcr.io -u "$2" --password-stdin > /dev/null; then
      rm -rf "$config"
      die "cannot log in to ghcr.io with the job's token"
    fi
    DOCKER_CONFIG="$config" docker pull -q "$1" > /dev/null || {
      rm -rf "$config"
      die "cannot pull $1"
    }
    rm -rf "$config"
  else
    docker pull -q "$1" > /dev/null || die "cannot pull $1 (a private package needs the job's token)"
  fi
}

remove_old_images() { # <image to keep> <previous image, kept for a rollback>
  local reference
  docker image prune -f > /dev/null || true
  while IFS= read -r reference; do
    case "$reference" in
      "$1" | "$2" | '' | *'<none>'*) ;;
      *) docker image rm "$reference" > /dev/null 2>&1 || true ;;
    esac
  done < <(
    docker image ls --digests --format '{{.Repository}}@{{.Digest}}' "$(image_repository)" 2> /dev/null || true
    docker image ls --format '{{.Repository}}:{{.Tag}}' "$LOCAL_IMAGE" 2> /dev/null || true
  )
}

deploy() { # <commit> <image|build> [<github user>]
  local sha="$1" target="$2" user="${3:-}" repo previous previous_sha image built_from model expected
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "the commit must be a full SHA (40 hexadecimal characters)"
  [[ -z "$user" || "$user" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}(\[bot\])?$ ]] || die "unexpected GitHub user name"
  [ "$(id -u)" -ne 0 ] || [ "${DEPLOY_ALLOW_ROOT:-0}" = "1" ] ||
    die "run as the deploy user, not root: sudo -u deploy -H bash $APP_DIR/scripts/deploy.sh $*"
  cd "$APP_DIR"
  [ -f .env ] || die "no .env in $APP_DIR: run scripts/bootstrap_hetzner.sh first"
  export GIT_SHA="${sha:0:7}"
  if [ "$target" = "build" ]; then
    image="$LOCAL_IMAGE:$GIT_SHA"
  else
    # Only an image of this repository, and only by digest: a tag can move.
    repo="$(image_repository)"
    case "$target" in
      "$repo@sha256:"*) ;;
      *) die "the image must be $repo@sha256:<digest>, got: $target" ;;
    esac
    [[ "${target#"$repo@sha256:"}" =~ ^[0-9a-f]{64}$ ]] || die "not a sha256 digest: $target"
    image="$target"
  fi

  if command -v flock > /dev/null 2>&1; then
    exec 9> "${TMPDIR:-/tmp}/normaai-deploy.lock"
    flock -n 9 || die "another deploy is running"
  fi

  # ── 1. The commit ──
  git fetch -q --prune origin
  git cat-file -e "$sha^{commit}" 2> /dev/null || die "commit $sha is not in origin"
  git merge-base --is-ancestor "$sha" origin/main || die "commit $sha is not on origin/main"
  previous_sha="$(git rev-parse HEAD)"
  git reset -q --hard "$sha"
  # From here a failure puts the checkout back: the compose files must match
  # the image that keeps serving.
  RESTORE_SHA="$previous_sha"
  log "code at $GIT_SHA (was ${previous_sha:0:7})"

  # ── 2. The image ──
  previous="$(env_value NORMAAI_IMAGE)"
  # Without NORMAAI_IMAGE compose ran the image built here (docker-compose.prod.yml).
  previous="${previous:-$LOCAL_IMAGE:local}"
  model="$(env_value EMBEDDING_MODEL)"
  model="${model:-$DEFAULT_EMBEDDING_MODEL}"
  if [ "$target" = "build" ]; then
    log "building $image here (fallback; the model is downloaded again when the lock changed)"
    NORMAAI_IMAGE="$image" docker compose build app < /dev/null || die "the image did not build"
  else
    log "pulling $image"
    pull_image "$image" "$user"
  fi
  built_from="$(label "$image" org.opencontainers.image.revision)"
  [ "${#built_from}" -ge 7 ] && [ "${sha#"$built_from"}" != "$sha" ] ||
    die "the image was built from '${built_from:-?}', not from $GIT_SHA"
  expected="$(label "$image" org.normaai.embedding-model)"
  [ "$expected" = "$model" ] ||
    die "the image holds the model '${expected:-?}', .env asks for '$model' (rebuild it with that EMBEDDING_MODEL, or deploy with: build)"
  export NORMAAI_IMAGE="$image"

  # ── 3. Migrations, as the owner ──
  log "migrations (alembic upgrade head) as the owner of the schema"
  docker compose run --rm -T migrate < /dev/null || die "the migrations failed: the old app is still serving"

  # ── 4-5. The app, alone ──
  local started=$SECONDS
  log "recreating $APP_CONTAINER"
  docker compose up -d --no-deps --no-build app < /dev/null || die "cannot recreate the app"
  if ! wait_healthy; then
    docker logs --tail 60 "$APP_CONTAINER" >&2 || true
    if [ -n "$previous" ] && [ "$previous" != "$image" ]; then
      log "the new app is not healthy: back to $previous"
      git reset -q --hard "$previous_sha" || true
      NORMAAI_IMAGE="$previous" docker compose up -d --no-deps --no-build app < /dev/null || true
    fi
    die "the app on $GIT_SHA did not become healthy within ${HEALTH_TIMEOUT}s"
  fi
  log "healthy after $((SECONDS - started))s of restart"

  # ── 6. Bookkeeping ──
  RESTORE_SHA=""
  set_env_value NORMAAI_IMAGE "$image"
  docker compose up -d --no-deps caddy < /dev/null || die "cannot start Caddy"
  if ! git diff --quiet "$previous_sha" "$sha" -- infra/Caddyfile; then
    log "infra/Caddyfile changed: reloading Caddy"
    docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile < /dev/null ||
      die "Caddy did not take the new Caddyfile"
  fi
  remove_old_images "$image" "$previous"
  log "deployed $GIT_SHA ($image)"
}

main() {
  local words=()
  if [ "${1:-}" = "--ssh" ]; then
    # The forced command of the deploy key: only "deploy <commit> <image|build> [<user>]".
    read -r -a words <<< "${SSH_ORIGINAL_COMMAND:-}"
    [ "${words[0]:-}" = "deploy" ] && [ "${#words[@]}" -ge 3 ] && [ "${#words[@]}" -le 4 ] ||
      die "this key may only run: deploy <commit> <image|build> [<github user>]"
    deploy "${words[@]:1}"
  else
    [ "$#" -ge 2 ] && [ "$#" -le 3 ] || die "usage: bash scripts/deploy.sh <commit> <image|build> (see --help)"
    deploy "$@"
  fi
}

on_exit() {
  local code=$?
  if [ "$code" -ne 0 ] && [ -n "$RESTORE_SHA" ]; then
    git -C "$APP_DIR" reset -q --hard "$RESTORE_SHA" && log "checkout back at ${RESTORE_SHA:0:7}"
  fi
}

case "${1:-}" in
  -h | --help) sed -n '3,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *)
    trap on_exit EXIT
    main "$@"
    ;;
esac
