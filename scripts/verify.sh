#!/usr/bin/env bash
# verify.sh — smoke test of the whole chain: proxy health, 9Router model list,
# and (when a real token is registered) one live chat completion.
#
# Usage:
#   scripts/verify.sh [router_api_key]
# Env:
#   NINE_ROUTER_URL     (default http://127.0.0.1:20128)
#   FREEBUFF_PROXY_URL  (default http://127.0.0.1:3457)
#   FREEBUFF_MODEL      (default freebuff/z-ai/glm-5.3-flash)
#   NINE_ROUTER_DB      (default ~/.9router/db/data.sqlite)
set -uo pipefail

ROUTER="${NINE_ROUTER_URL:-http://127.0.0.1:20128}"
PROXY="${FREEBUFF_PROXY_URL:-${FREEBUCKS_PROXY_URL:-http://127.0.0.1:3457}}"
MODEL="${FREEBUFF_MODEL:-freebuff/z-ai/glm-5.3-flash}"
DB="${NINE_ROUTER_DB:-$HOME/.9router/db/data.sqlite}"
KEY="${1:-}"

python3 - "$ROUTER" "$PROXY" "$MODEL" "$KEY" "$DB" <<'PY'
import json, sqlite3, sys, urllib.error, urllib.request

router, proxy, model, key, db = sys.argv[1:6]
prefix = model.split("/")[0]
fail = False

def ok(msg):   print("   OK —", msg)
def bad(msg):  print("   FAIL —", msg)
def skip(msg): print("   SKIP —", msg)

# 1. proxy health
try:
    h = json.load(urllib.request.urlopen(proxy + "/healthz", timeout=10))
    ok(f"freebuff-proxy healthz (mode={h.get('mode')}, uptime={int(h.get('uptime_seconds', 0))}s)")
except Exception as e:
    bad(f"proxy healthz: {e} (systemctl status freebuff-proxy)"); fail = True

# 2. proxy catalog
try:
    ids = [m["id"] for m in json.load(urllib.request.urlopen(proxy + "/v1/models", timeout=15)).get("data", [])]
    ok(f"proxy catalog: {len(ids)} models")
    if not ids: bad("empty catalog"); fail = True
except Exception as e:
    bad(f"proxy /v1/models: {e}"); fail = True

# 3. router key (auto-resolve when not given)
if not key and db and __import__("os").path.exists(db):
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        row = con.execute("SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1").fetchone()
        con.close()
        key = row[0] if row else ""
    except Exception:
        pass

# 4. router model list
fb = []
try:
    req = urllib.request.Request(router + "/v1/models")
    if key: req.add_header("Authorization", "Bearer " + key)
    ids = [m["id"] for m in json.load(urllib.request.urlopen(req, timeout=25)).get("data", [])]
    fb = sorted(i for i in ids if i.startswith(prefix + "/"))
    ok(f"9Router lists {len(fb)} {prefix}/* models")
    if not fb: bad("no " + prefix + "/* models on 9Router"); fail = True
except Exception as e:
    bad(f"9Router /v1/models: {e}"); fail = True

# 5. live chat (skips cleanly when no valid token yet)
try:
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
                       "stream": False, "max_tokens": 16}).encode()
    req = urllib.request.Request(router + "/v1/chat/completions", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if key: req.add_header("Authorization", "Bearer " + key)
    out = json.load(urllib.request.urlopen(req, timeout=120))
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
    ok(f"live chat via {model}: {(text or '<empty>')[:80]!r}")
except urllib.error.HTTPError as e:
    msg = e.read()[:300].decode(errors="replace")
    if "upstream_auth_rejected" in msg or "upstream auth rejected" in msg or e.code in (401, 403):
        skip(f"no valid FreeBuff token registered yet (HTTP {e.code}) — finish the login flow")
    elif e.code in (429, 503) and ("reset after" in msg or "all accounts" in msg or "rate limited" in msg or "unavailable" in msg):
        skip(f"all FreeBuff accounts are currently rate-limited upstream ({msg.strip()})")
    else:
        bad(f"live chat HTTP {e.code}: {msg}"); fail = True
except Exception as e:
    bad(f"live chat: {e}"); fail = True

print()
print("ALL CHECKS PASSED" if not fail else "SOME CHECKS FAILED")
sys.exit(0 if not fail else 1)
PY
