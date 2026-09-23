#!/usr/bin/env bash
# install.sh — end-to-end installer for freebuff-9router.
#
# What it does:
#   1. checks prerequisites (go, node, 9Router, systemd)
#   2. clones + builds freebuff-proxy from the pinned upstream tag
#   3. installs the binary + a hardened systemd service (loopback-only, bridge mode)
#   4. backs up 9Router's SQLite DB and registers the `freebuff` provider node
#   5. starts the FreeBuff device login and prints the approval URL
#
# Idempotent: safe to re-run after 9Router/proxy updates or to change settings.
#
# Configuration via environment variables:
#   FREEBUFF_UPSTREAM_TAG   upstream release tag          (default v1.18.2)
#   FREEBUFF_LISTEN         proxy listen address          (default 127.0.0.1:3457)
#   FREEBUFF_PREFIX         9Router model prefix          (default freebuff)
#   NINE_ROUTER_DB          9Router SQLite path           (default ~/.9router/db/data.sqlite)
#   SKIP_BUILD=1            reuse an already-installed binary
#
set -euo pipefail

FREEBUFF_UPSTREAM_REPO="${FREEBUFF_UPSTREAM_REPO:-trefeon/freebucks-proxy}"
FREEBUFF_UPSTREAM_TAG="${FREEBUFF_UPSTREAM_TAG:-v1.18.2}"
FREEBUFF_LISTEN="${FREEBUFF_LISTEN:-127.0.0.1:3457}"
FREEBUFF_PREFIX="${FREEBUFF_PREFIX:-freebuff}"
NINE_ROUTER_DB="${NINE_ROUTER_DB:-$HOME/.9router/db/data.sqlite}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${BUILD_DIR:-/tmp/freebuff-proxy-build}"

c()  { printf '\033[36m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m%s\033[0m\n' "$*"; }
warn(){ printf '\033[33m%s\033[0m\n' "$*"; }
err(){ printf '\033[31m%s\033[0m\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { err "run as root (sudo ./install.sh)"; exit 1; }

c "==> 1/5 prerequisites"
command -v curl >/dev/null || apt-get update >/dev/null 2>&1 && apt-get install -y curl ca-certificates >/dev/null
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  if ! command -v go >/dev/null 2>&1 || ! go version | grep -q "go1.2[6-9]"; then
    GO_VER="$(curl -s --max-time 20 'https://go.dev/VERSION?m=text' | head -n1)"
    [ -n "$GO_VER" ] || GO_VER="go1.27.1"
    c "    installing $GO_VER"
    curl -sL --max-time 300 -o /tmp/go.tgz "https://go.dev/dl/${GO_VER}.linux-amd64.tar.gz"
    rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tgz
    ln -sf /usr/local/go/bin/go /usr/local/bin/go
  fi
  command -v node >/dev/null || { err "node >= 20 required for the frontend build"; exit 1; }
fi
[ -f "$NINE_ROUTER_DB" ] || { err "9Router DB not found at $NINE_ROUTER_DB — install/start 9Router first"; exit 1; }

c "==> 2/5 building freebuff-proxy ($FREEBUFF_UPSTREAM_TAG)"
PROXY_BIN="/usr/local/bin/freebuff-proxy"
if [ "${SKIP_BUILD:-0}" = "1" ] && [ -x "$PROXY_BIN" ]; then
  ok "    using existing $PROXY_BIN (SKIP_BUILD=1)"
else
  rm -rf "$BUILD_DIR"
  git clone --depth 1 --branch "$FREEBUFF_UPSTREAM_TAG" \
    "https://github.com/$FREEBUFF_UPSTREAM_REPO.git" "$BUILD_DIR" >/dev/null 2>&1 \
    || { err "clone failed — check the tag ($FREEBUFF_UPSTREAM_TAG) and network"; exit 1; }
  # apply our patches (idempotent; each is documented in patches/)
  for PATCH in "$REPO_DIR"/patches/*.patch; do
    [ -e "$PATCH" ] || continue
    if git -C "$BUILD_DIR" apply --check "$PATCH" 2>/dev/null; then
      git -C "$BUILD_DIR" apply "$PATCH"
      ok "    applied $(basename "$PATCH")"
    elif git -C "$BUILD_DIR" apply --reverse --check "$PATCH" 2>/dev/null; then
      ok "    $(basename "$PATCH") already applied"
    else
      err "    $(basename "$PATCH") does not apply to $FREEBUFF_UPSTREAM_TAG — the upstream may have fixed it; try removing the patch file or picking a newer tag"
      exit 1
    fi
  done
  npm --prefix "$BUILD_DIR/frontend" ci --no-audit --no-fund >/dev/null
  npm --prefix "$BUILD_DIR/frontend" run build >/dev/null
  (cd "$BUILD_DIR" && go build -o "$PROXY_BIN" ./backend/cmd/freebucks-proxy)
  chmod 0755 "$PROXY_BIN"
  ln -sf "$PROXY_BIN" /usr/local/bin/freebucks-proxy
  ok "    built $PROXY_BIN"
fi

c "==> 3/5 systemd service (loopback-only, bridge mode)"
id -u freebuff-proxy >/dev/null 2>&1 || useradd --system --home-dir /var/lib/freebuff-proxy --shell /usr/sbin/nologin freebuff-proxy
mkdir -p /etc/freebuff-proxy /var/lib/freebuff-proxy
if [ ! -f /etc/freebuff-proxy/env ]; then
  ADMIN_TOKEN="$(openssl rand -hex 24)"
  cat > /etc/freebuff-proxy/env <<EOF
# freebuff-proxy — managed by freebuff-9router/install.sh
# Bridge mode: AUTH_TOKENS stays empty. Each request's Bearer IS the upstream
# FreeBuff token (relayed from the 9Router connection). Tokens live only in
# 9Router's SQLite, never here.
LISTEN_ADDR=${FREEBUFF_LISTEN}
UPSTREAM_BASE_URL=https://www.codebuff.com
SAFE_MODE=true
COST_MODE=free
AUTH_TOKENS=
ADMIN_TOKEN=${ADMIN_TOKEN}
LOG_LEVEL=info
LOG_ACCESS=true
EOF
  chown root:freebuff-proxy /etc/freebuff-proxy/env && chmod 640 /etc/freebuff-proxy/env
  ok "    wrote /etc/freebuff-proxy/env (ADMIN_TOKEN generated — keep a copy: sudo cat /etc/freebuff-proxy/env)"
else
  warn "    /etc/freebuff-proxy/env already exists — left untouched"
fi
install -m 0644 "$REPO_DIR/systemd/freebuff-proxy.service" /etc/systemd/system/freebuff-proxy.service
chown -R freebuff-proxy:freebuff-proxy /var/lib/freebuff-proxy
systemctl daemon-reload
systemctl enable --now freebuff-proxy >/dev/null 2>&1 || systemctl restart freebuff-proxy
sleep 2
systemctl is-active --quiet freebuff-proxy && ok "    service active" || { err "service failed — journalctl -u freebuff-proxy -n 50"; exit 1; }
curl -sf "http://${FREEBUFF_LISTEN#*:}/healthz" >/dev/null 2>&1 || curl -sf "http://${FREEBUFF_LISTEN}/healthz" >/dev/null || { err "healthz failed"; exit 1; }
ok "    healthz OK"

c "==> 4/5 registering provider in 9Router (prefix: ${FREEBUFF_PREFIX})"
cp "$NINE_ROUTER_DB" "$NINE_ROUTER_DB.freebuff-pre-$(date +%Y%m%d-%H%M%S)"
chmod 600 "$NINE_ROUTER_DB".freebuff-pre-* 2>/dev/null || true
python3 "$REPO_DIR/freebuff9r.py" --prefix "$FREEBUFF_PREFIX" --proxy-url "http://${FREEBUFF_LISTEN%:*}:${FREEBUFF_LISTEN#*:}" register

c "==> 4.1/5 applying high-grade UI/UX patch to 9Router"
if [ -f "$REPO_DIR/patch-9router-ui.py" ]; then
    python3 "$REPO_DIR/patch-9router-ui.py" || warn "    UI patch encountered non-critical issue"
fi

if command -v systemctl &>/dev/null && systemctl is-active --quiet 9router; then
    systemctl restart 9router
    ok "    9Router restarted"
fi

c "==> 4.2/5 installing model-sync watchdog (dashboard toggles -> /model pickers)"
install -m 0644 "$REPO_DIR/systemd/freebuff-model-sync.service" /etc/systemd/system/freebuff-model-sync.service
systemctl daemon-reload
systemctl enable --now freebuff-model-sync >/dev/null 2>&1 || systemctl restart freebuff-model-sync
systemctl is-active --quiet freebuff-model-sync && ok "    freebuff-model-sync active" || warn "    model-sync watchdog failed — journalctl -u freebuff-model-sync -n 30"
python3 "$REPO_DIR/scripts/sync-models.py" || warn "    initial model reconcile reported drift (see output above)"

c "==> 5/5 FreeBuff account login"
python3 "$REPO_DIR/freebuff9r.py" --prefix "$FREEBUFF_PREFIX" login-url > /tmp/freebuff-login-flow.json
python3 - <<'PY'
import json
f = json.load(open('/tmp/freebuff-login-flow.json'))
print()
print("  ┌─────────────────────────────────────────────────────────────┐")
print("  │  OPEN THIS URL AND SIGN IN WITH YOUR GITHUB ACCOUNT:        │")
print("  └─────────────────────────────────────────────────────────────┘")
print()
print("  " + f["loginUrl"])
print()
print("  then run:")
print(f'  python3 freebuff9r.py wait-login --fingerprint "{f["fingerprint"]}" \\')
print(f'      --hash "{f["fingerprintHash"]}" --expires-at "{f["expiresAt"]}"')
print()
print("  (or re-run install.sh — it detects an unregistered token and waits for you)")
PY
ok "done. verify with: python3 freebuff9r.py status"
