#!/usr/bin/env bash
# Deploy the film page as one static container behind the host's reverse proxy (decision 0009).
#   deploy/deploy.sh              build HEAD from a clean `git archive` plus the measured videos, run it, install the route, verify
#   deploy/deploy.sh --rollback   run the previous image again (held by the stopped `sampan-river-site-undur` container)
#   deploy/deploy.sh --status     container, tags, rollback image and the public health code
# The videos come from MEDIA_DIR; tools/site.py stops the build when a file's sha256 differs from docs/MEASURED.md.
# Verification: /healthz through the public URL (retried), then deploy/check_page.py (WebKit iPhone 13, Chromium desktop
# and 320 px) against the public URL. A failed browser check rolls back. Host values live in deploy/hos.env (not
# tracked; see deploy/hos.env.example). The container holds no keys.
set -euo pipefail
# The script calls itself again to roll back, after moving into deploy/: keep a path that still works from there.
SELF="$(realpath "$0")"
cd "$(dirname "$SELF")"
[ -r hos.env ] || { echo "deploy/hos.env missing (copy hos.env.example)"; exit 1; }
# shellcheck disable=SC1091
. ./hos.env
: "${SITE_NETWORK:?}" "${SITE_DOMAIN:?}" "${PROXY_CONTAINER:?}" "${PROXY_DYNAMIC_DIR:?}" "${CERT_RESOLVER:?}" "${MEDIA_DIR:?}"
BUILD_CMD=${BUILD_CMD:-docker build}
MIN_FREE_GB=${MIN_FREE_GB:-20}
BROWSER_CMD=${BROWSER_CMD:-}
CHECK_OUT=${CHECK_OUT:-}
export SITE_NETWORK
DC="docker compose -f compose.yaml"
URL="https://$SITE_DOMAIN"
NAME=sampan-river
SERVICE=sampan-river-site
HOLDER="$SERVICE-undur"

# Certificates use the HTTP-01 challenge: a name that does not resolve fails it.
dns_ok() { getent ahosts "$SITE_DOMAIN" >/dev/null; }
health_code() { curl -s -m 20 -o /dev/null -w '%{http_code}' "$URL/healthz" || true; }

hold_previous() {  # $1 = image ID the replaced container ran: keep it by ID in a stopped container
  local prev id=${1:-}
  prev=$(cat PREVIOUS_TAG 2>/dev/null) || { echo "note: first deploy, no rollback image yet"; return 0; }
  [ -n "$id" ] || id=$(docker image inspect -f '{{.Id}}' "$NAME:$prev" 2>/dev/null) || id=""
  [ -n "$id" ] || { echo "WARNING: rollback image $NAME:$prev not found; --rollback will fail" >&2; return 1; }
  docker rm -fv "$HOLDER" >/dev/null 2>&1 || true
  docker tag "$id" "$NAME:$prev"
  docker create --name "$HOLDER" --network none --restart no --label "sasateguh.tag=$prev" "$NAME:$prev" >/dev/null
  echo "rollback image held: $NAME:$prev (${id:7:12})"
}

browser_check() {  # read-only checks, two engines, against the public URL
  local args=("$URL")
  [ -z "$CHECK_OUT" ] || args+=(--out "$CHECK_OUT")
  (cd .. && $BROWSER_CMD python3 deploy/check_page.py "${args[@]}")
}

mode=${1:-deploy}
case "$mode" in
  --status)
    $DC ps
    echo "current $(cat CURRENT_TAG 2>/dev/null || echo -) · previous $(cat PREVIOUS_TAG 2>/dev/null || echo -)"
    docker inspect -f 'rollback holder: {{index .Config.Labels "sasateguh.tag"}}' "$HOLDER" 2>/dev/null || echo "rollback holder: none"
    echo "public /healthz $(health_code)"; exit 0 ;;
  --rollback)
    dns_ok || { echo "$SITE_DOMAIN does not resolve, nothing was changed"; exit 1; }
    TAG=$(cat PREVIOUS_TAG 2>/dev/null) || { echo "no PREVIOUS_TAG"; exit 1; }
    if ! docker image inspect "$NAME:$TAG" >/dev/null 2>&1; then
      id=$(docker inspect -f '{{.Image}}' "$HOLDER" 2>/dev/null) || { echo "image $NAME:$TAG is gone"; exit 1; }
      docker tag "$id" "$NAME:$TAG"
    fi
    [ -r CURRENT_TAG ] && cp CURRENT_TAG PREVIOUS_TAG ;;
  deploy)
    dns_ok || { echo "$SITE_DOMAIN does not resolve: create the DNS record first, nothing was changed"; exit 1; }
    [ -z "$(git -C .. status --porcelain)" ] || { echo "working tree not clean: commit first (the image is built from HEAD)"; exit 1; }
    free=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
    [ "$free" -ge "$MIN_FREE_GB" ] || { echo "less than ${MIN_FREE_GB} GB free on /, stopping"; exit 1; }
    TAG=$(git -C .. rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M)
    ctx=$(mktemp -d); trap 'rm -rf "$ctx"' EXIT
    git -C .. archive HEAD | tar -x -C "$ctx"   # clean tree: untracked and ignored files never reach the image
    python3 "$ctx/tools/site.py" --root "$ctx" --media "$MEDIA_DIR" --out "$ctx/public"
    $BUILD_CMD -t "$NAME:$TAG" -f "$ctx/deploy/Dockerfile" "$ctx"
    [ -r CURRENT_TAG ] && cp CURRENT_TAG PREVIOUS_TAG ;;
  *) echo "usage: deploy.sh [--rollback|--status]"; exit 2 ;;
esac

old_id=$(docker inspect -f '{{.Image}}' "$SERVICE" 2>/dev/null || true)
SITE_TAG=$TAG $DC up -d --force-recreate "$SERVICE"
echo "$TAG" > CURRENT_TAG

route=$(mktemp)
sed -e "s|@DOMAIN@|$SITE_DOMAIN|g" -e "s|@CERT_RESOLVER@|$CERT_RESOLVER|g" traefik.yaml.tmpl > "$route"
chmod 644 "$route"
docker cp "$route" "$PROXY_CONTAINER:$PROXY_DYNAMIC_DIR/$NAME.yaml"; rm -f "$route"

for _ in $(seq 30); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$SERVICE")" = healthy ] && break; sleep 3; done
no_rollback=0; [ "$mode" = --rollback ] || hold_previous "$old_id" || no_rollback=1

# Keep only the current and previous images of this project; the host disk is shared.
docker images "$NAME" --format '{{.Tag}}' | grep -vxF -e "$TAG" -e "$(cat PREVIOUS_TAG 2>/dev/null || echo -)" \
  | sed "s/^/$NAME:/" | xargs -r docker rmi >/dev/null 2>&1 || true

# A new route or certificate can take a little while: wait and retry before calling it a failure.
code=000
for _ in $(seq 9); do code=$(health_code); [ "$code" = 200 ] && break; sleep 10; done
echo "tag $TAG · public /healthz $code"
[ "$code" = 200 ] || { echo "public health is not 200: check the certificate and route; undo with deploy/deploy.sh --rollback"; exit 1; }

if [ "$mode" = deploy ] && ! browser_check; then
  if [ -r PREVIOUS_TAG ] && [ "$no_rollback" = 0 ]; then echo "browser check failed: rolling back"; exec "$SELF" --rollback; fi
  echo "browser check failed and there is no previous image to return to"; exit 1
fi
[ "$no_rollback" = 0 ] || { echo "live, but no rollback image is held (warning above)"; exit 1; }
