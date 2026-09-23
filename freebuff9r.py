#!/usr/bin/env python3
"""
freebuff9r — register the FreeBuff provider (freebucks-proxy) inside 9Router.

Adds an `openai-compatible` provider node + one provider connection per
FreeBuff account token directly into 9Router's SQLite database
(~/.9router/db/data.sqlite), exactly the same rows the 9Router dashboard
writes when you use "Providers -> Add OpenAI Compatible".

Why SQLite and not the dashboard REST API?
  * the dashboard API rejects Bearer API-key auth (401), so scripted
    setup would need screen-scraping;
  * rows written here are the same shape the dashboard itself writes,
    so the dashboard can later manage/edit them normally;
  * 9Router re-reads providerConnections from SQLite on every
    /v1/models request, so no restart is needed and the rows survive
    `npm i -g 9router` updates (the SQLite DB lives outside node_modules).

Subcommands:
  register   create/refresh the provider node (idempotent)
  add-token  mint or attach a FreeBuff account token as a new connection
  login-url  start a device login flow and print the approval URL
  wait-login poll a started login flow and register the token when done
  status     show node/connections and proxy health
  verify     end-to-end check: proxy health, 9Router model list, live chat
  remove     remove everything this tool added (node + connections + kv rows)

Examples:
  python3 freebuff9r.py register
  python3 freebuff9r.py add-token --token <FREEBUFF_TOKEN>
  python3 freebuff9r.py login-url
  python3 freebuff9r.py wait-login --fingerprint <FP> --hash <HASH> --expires-at <ISO>
  python3 freebuff9r.py verify --model freebuff/z-ai/glm-5.3-flash
  python3 freebuff9r.py remove
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

DEFAULT_DB = os.environ.get("NINE_ROUTER_DB", os.path.expanduser("~/.9router/db/data.sqlite"))
DEFAULT_PROXY = os.environ.get("FREEBUCKS_PROXY_URL", "http://127.0.0.1:3457")
DEFAULT_PREFIX = os.environ.get("FREEBUFF_PREFIX", "freebuff")
DEFAULT_NAME = os.environ.get("FREEBUFF_NODE_NAME", "FreeBuff (freebucks-proxy)")
UPSTREAM_BASE = os.environ.get("FREEBUFF_UPSTREAM", "https://www.codebuff.com")
LOGIN_UA = "ai-sdk/openai-compatible/1.0.0/codebuff"  # CLI-parity UA (fingerprintable surface)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def http_json(url: str, method: str = "GET", body: dict | None = None,
              headers: dict | None = None, timeout: int = 15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "freebuff-9router/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def open_db(path: str) -> sqlite3.Connection:
    if not os.path.exists(path):
        sys.exit(f"9Router database not found at {path} — is 9Router installed?")
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def backup_db(path: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.freebuff-backup-{stamp}"
    with open(path, "rb") as src, open(bak, "wb") as dst:
        dst.write(src.read())
    os.chmod(bak, 0o600)
    return bak


def find_node(con: sqlite3.Connection, prefix: str):
    """Locate our provider node by its prefix in providerNodes.data."""
    for row in con.execute("SELECT id, type, name, data FROM providerNodes WHERE type='openai-compatible'"):
        try:
            data = json.loads(row["data"] or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("prefix") == prefix:
            return row["id"], data, row["name"]
    return None, None, None


def node_connection_ids(con: sqlite3.Connection, node_id: str):
    return [r["id"] for r in con.execute(
        "SELECT id FROM providerConnections WHERE provider=?", (node_id,))]


def connection_rows(con: sqlite3.Connection, node_id: str):
    out = []
    for row in con.execute(
            "SELECT id, name, priority, isActive, data, createdAt, updatedAt "
            "FROM providerConnections WHERE provider=? ORDER BY priority IS NULL, priority", (node_id,)):
        try:
            data = json.loads(row["data"] or "{}")
        except json.JSONDecodeError:
            data = {}
        out.append({
            "id": row["id"], "name": row["name"], "priority": row["priority"],
            "isActive": bool(row["isActive"]),
            "email": data.get("email") or "",
            "token_set": bool(data.get("apiKey")),
            "testStatus": data.get("testStatus", ""),
        })
    return out


# --------------------------------------------------------------------------- register
def cmd_register(args):
    con = open_db(args.db)
    base_url = args.proxy_url.rstrip("/") + "/v1"
    node_id, node_data, node_name = find_node(con, args.prefix)
    created = False

    if node_id is None:
        node_id = f"openai-compatible-chat-{args.prefix}"
        con.execute(
            "INSERT INTO providerNodes(id, type, name, data, createdAt, updatedAt) "
            "VALUES(?,?,?,?,?,?)",
            (node_id, "openai-compatible", args.name,
             json.dumps({"prefix": args.prefix, "apiType": "chat", "baseUrl": base_url}),
             now_iso(), now_iso()))
        created = True
        print(f"[+] created providerNode  id={node_id}")
    else:
        # refresh in case the proxy URL moved
        con.execute("UPDATE providerNodes SET data=?, updatedAt=? WHERE id=?",
                    (json.dumps({"prefix": args.prefix, "apiType": "chat", "baseUrl": base_url}),
                     now_iso(), node_id))
        print(f"[=] providerNode exists    id={node_id} (baseUrl refreshed)")

    # Optional seed connection so models appear before the first token exists.
    # In bridge mode the proxy does not validate /v1/models auth, so a
    # placeholder Bearer is enough for the live model list; chat stays gated
    # on a real token (add-token).
    if not node_connection_ids(con, node_id):
        conn_id = str(uuid.uuid4())
        data = {
            "apiKey": args.placeholder_key or "freebuff-bridge-pending",
            "providerSpecificData": {
                "prefix": args.prefix,
                "apiType": "chat",
                "baseUrl": base_url,
                "nodeName": args.name,
                "connectionProxyEnabled": False,
                "connectionProxyUrl": "",
                "connectionNoProxy": "",
            },
            "testStatus": "active",
        }
        con.execute(
            "INSERT INTO providerConnections(id, provider, authType, name, email, priority, "
            "isActive, data, createdAt, updatedAt) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (conn_id, node_id, "apikey", f"{args.prefix} account 1", None, 1, 1,
             json.dumps(data), now_iso(), now_iso()))
        print(f"[+] created seed connection id={conn_id} (placeholder token — run add-token)")

    # Mirror the proxy catalog into customModels kv rows so the dashboard's
    # provider page lists models with per-model toggles like every other
    # provider (same pattern as the ChatGPT/Qwen/Meta web bridges).
    try:
        res = sync_models(con, args.prefix, args.proxy_url)
        if "error" not in res:
            print(f"[+] synced {len(res['imported'])} models into customModels "
                  f"(GUI → Providers → {args.prefix} shows them like any other provider)")
            if res["skipped_unavailable"]:
                print(f"    unavailable upstream (not imported): {', '.join(res['skipped_unavailable'])}")
    except Exception as e:
        print(f"[!] model sync skipped ({e}) — run `sync-models` later")

    con.commit()
    con.close()

    print(f"[✓] provider '{args.prefix}' ready — baseUrl={base_url}")
    print(f"    models appear as {args.prefix}/<upstream-model-id> on 9Router /v1/models")
    if created:
        print("[i] no restart needed: 9Router re-reads connections per request")


# --------------------------------------------------------------------------- login flow
def cmd_login_url(args):
    fp = "enhanced-" + os.urandom(32).hex()[:43].replace("+", "-").replace("/", "_")
    body = {"fingerprintId": fp}
    try:
        resp = http_json(f"{UPSTREAM_BASE}/api/auth/cli/code", method="POST", body=body,
                         headers={"User-Agent": LOGIN_UA})
    except urllib.error.HTTPError as e:
        sys.exit(f"login start failed: HTTP {e.code} {e.read()[:200]}")
    login_url = resp.get("loginUrl")
    if not login_url:
        sys.exit(f"no loginUrl in response: {json.dumps(resp)[:300]}")
    print(json.dumps({
        "fingerprint": fp,
        "fingerprintHash": resp.get("fingerprintHash", ""),
        "expiresAt": resp.get("expiresAt", ""),
        "loginUrl": login_url,
        "note": "open loginUrl in a browser (GitHub login of the account you want a token for), then run wait-login",
    }, indent=2))


def cmd_wait_login(args):
    con = open_db(args.db)
    node_id, node_data, node_name = find_node(con, args.prefix)
    if node_id is None:
        sys.exit("provider node not found — run `register` first")
    base_url = node_data["baseUrl"]
    qs = urllib.parse.urlencode({
        "fingerprintId": args.fingerprint,
        "fingerprintHash": args.hash,
        "expiresAt": args.expires_at,
    })
    url = f"{UPSTREAM_BASE}/api/auth/cli/status?{qs}"
    deadline = time.time() + args.timeout
    print(f"polling {url.split('?')[0]} ... (up to {args.timeout}s)")
    token = None
    user_email = ""
    user_name = ""
    while time.time() < deadline:
        try:
            resp = http_json(url, headers={"User-Agent": LOGIN_UA}, timeout=20)
        except urllib.error.HTTPError as e:
            if e.code in (401, 404):
                time.sleep(args.interval)
                continue
            sys.exit(f"status poll failed: HTTP {e.code}")
        user = resp.get("user") or {}
        token = user.get("authToken")
        if token:
            user_email = user.get("email", "")
            user_name = user.get("name", "")
            break
        time.sleep(args.interval)
    if not token:
        sys.exit("login did not complete in time — rerun login-url + wait-login")

    # find a free priority slot
    rows = connection_rows(con, node_id)
    existing = [r for r in rows if r["email"] and r["email"] == user_email]
    if existing and not args.replace:
        print(f"[=] token for {user_email or user_name} already registered as connection "
              f"{existing[0]['id']} — nothing to do")
        con.close()
        return
    # replace the placeholder seed connection when present (one connection
    # per real account, exactly like the web-bridge pattern)
    seed = next((r for r in rows if _is_placeholder(con, node_id, r["id"])), None)
    if seed:
        con.execute("DELETE FROM providerConnections WHERE id=?", (seed["id"],))
        print(f"[-] removed placeholder seed connection {seed['id']}")
        prio = 1
        rows = [r for r in rows if r["id"] != seed["id"]]
    else:
        prio = (max([r["priority"] or 0 for r in rows] or [0])) + 1
    label = user_email or user_name or f"{args.prefix} account {prio}"
    if existing and args.replace:
        conn_id = existing[0]["id"]
        con.execute("UPDATE providerConnections SET data=?, name=?, updatedAt=? WHERE id=?",
                    (json.dumps(_conn_data(token, base_url, args.prefix, node_name, user_email)),
                     label, now_iso(), conn_id))
        print(f"[~] refreshed connection {conn_id} for {label}")
    else:
        conn_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO providerConnections(id, provider, authType, name, email, priority, "
            "isActive, data, createdAt, updatedAt) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (conn_id, node_id, "apikey", label, user_email or None, prio, 1,
             json.dumps(_conn_data(token, base_url, args.prefix, node_name, user_email)),
             now_iso(), now_iso()))
        print(f"[+] token registered: connection {conn_id} ({label}) priority={prio}")
    con.commit()
    con.close()
    print(f"[✓] done — models at {args.prefix}/* are now usable end-to-end")


def _conn_data(token: str, base_url: str, prefix: str, node_name: str, email: str) -> dict:
    data = {
        "apiKey": token,
        "providerSpecificData": {
            "prefix": prefix,
            "apiType": "chat",
            "baseUrl": base_url,
            "nodeName": node_name,
            "connectionProxyEnabled": False,
            "connectionProxyUrl": "",
            "connectionNoProxy": "",
        },
        "testStatus": "active",
    }
    if email:
        data["email"] = email
    return data


# --------------------------------------------------------------------------- add-token (paste)
def cmd_add_token(args):
    con = open_db(args.db)
    node_id, node_data, node_name = find_node(con, args.prefix)
    if node_id is None:
        sys.exit("provider node not found — run `register` first")
    base_url = node_data["baseUrl"]
    rows = connection_rows(con, node_id)
    prio = (max([r["priority"] or 0 for r in rows] or [0])) + 1
    label = args.label or f"{args.prefix} account {prio}"
    # replace the seed connection when it still carries the placeholder
    seed = next((r for r in rows if not r["token_set"] or r["id"] and _is_placeholder(con, node_id, r["id"])), None)
    if seed and args.replace_seed:
        conn_id = seed["id"]
        con.execute("UPDATE providerConnections SET data=?, name=?, updatedAt=? WHERE id=?",
                    (json.dumps(_conn_data(args.token, base_url, args.prefix, node_name, "")),
                     label, now_iso(), conn_id))
        print(f"[~] replaced seed connection {conn_id} with real token ({label})")
    else:
        conn_id = str(uuid.uuid4())
        con.execute(
            "INSERT INTO providerConnections(id, provider, authType, name, email, priority, "
            "isActive, data, createdAt, updatedAt) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (conn_id, node_id, "apikey", label, None, prio, 1,
             json.dumps(_conn_data(args.token, base_url, args.prefix, node_name, "")),
             now_iso(), now_iso()))
        print(f"[+] token registered: connection {conn_id} ({label}) priority={prio}")
    con.commit()
    con.close()
    print("[✓] done")


def _is_placeholder(con, node_id, conn_id):
    row = con.execute("SELECT data FROM providerConnections WHERE id=?", (conn_id,)).fetchone()
    try:
        return (json.loads(row["data"] or "{}").get("apiKey") or "").startswith("freebuff-bridge-pending")
    except Exception:
        return False


# --------------------------------------------------------------------------- status
def cmd_status(args):
    con = open_db(args.db)
    node_id, node_data, node_name = find_node(con, args.prefix)
    if node_id is None:
        print("provider node: NOT REGISTERED")
        con.close()
        return
    print(f"provider node : {node_id}")
    print(f"  name        : {node_name}")
    print(f"  baseUrl     : {node_data.get('baseUrl')}")
    print(f"  prefix      : {node_data.get('prefix')}")
    conns = connection_rows(con, node_id)
    print(f"  connections : {len(conns)}")
    for c in conns:
        state = "token ✓" if c["token_set"] and not c["token_set"] == "pending" else "PLACEHOLDER"
        if c["token_set"]:
            state = "token ✓"
        print(f"    - {c['id']} prio={c['priority']} active={c['isActive']} "
              f"name={c['name']!r} {state} test={c['testStatus']}")
    con.close()
    # proxy health
    try:
        health = http_json(f"{DEFAULT_PROXY}/healthz", timeout=5)
        print(f"proxy healthz : OK ({health})")
    except Exception as e:
        print(f"proxy healthz : FAIL ({e})")
    try:
        models = http_json(f"{DEFAULT_PROXY}/v1/models", timeout=10)
        print(f"proxy models  : {len(models.get('data', []))}")
    except Exception as e:
        print(f"proxy models  : FAIL ({e})")


# --------------------------------------------------------------------------- verify
def cmd_verify(args):
    ok = True
    # 1. proxy health
    try:
        http_json(f"{DEFAULT_PROXY}/healthz", timeout=5)
        print("[✓] freebucks-proxy healthz 200")
    except Exception as e:
        print(f"[✗] freebucks-proxy healthz failed: {e}")
        return 1
    # 2. proxy model catalog
    try:
        models = [m["id"] for m in http_json(f"{DEFAULT_PROXY}/v1/models", timeout=10).get("data", [])]
        print(f"[✓] proxy catalog: {len(models)} models")
    except Exception as e:
        print(f"[✗] proxy /v1/models failed: {e}")
        return 1
    # 3. 9Router model list contains prefixed ids
    router = args.router_url.rstrip("/")
    key = args.router_key
    try:
        req = urllib.request.Request(f"{router}/v1/models")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=20) as resp:
            rmodels = [m["id"] for m in json.loads(resp.read()).get("data", [])]
    except Exception as e:
        print(f"[✗] 9Router /v1/models failed: {e}")
        return 1
    prefixed = [m for m in rmodels if m.startswith(f"{args.prefix}/")]
    print(f"[{'✓' if prefixed else '✗'}] 9Router lists {len(prefixed)} {args.prefix}/* models")
    if not prefixed:
        ok = False
    # 4. live chat (optional — needs a real token)
    if args.model and args.prompt is not None:
        body = {"model": args.model, "messages": [{"role": "user", "content": args.prompt}],
                "stream": False, "max_tokens": 64}
        try:
            req = urllib.request.Request(f"{router}/v1/chat/completions",
                                         data=json.dumps(body).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())
            text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
            print(f"[✓] live chat via {args.model}: {text[:120]!r}")
        except urllib.error.HTTPError as e:
            print(f"[✗] live chat failed: HTTP {e.code} {e.read()[:200]}")
            ok = False
        except Exception as e:
            print(f"[✗] live chat failed: {e}")
            ok = False
    return 0 if ok else 1


# --------------------------------------------------------------------------- remove
def cmd_remove(args):
    con = open_db(args.db)
    node_id, _, _ = find_node(con, args.prefix)
    if node_id is None:
        print("nothing to remove")
        con.close()
        return
    bak = backup_db(args.db)
    print(f"[i] db backup written: {bak}")
    n = con.execute("DELETE FROM providerConnections WHERE provider=?", (node_id,)).rowcount
    con.execute("DELETE FROM providerNodes WHERE id=?", (node_id,))
    con.execute("DELETE FROM kv WHERE scope='disabledModels' AND key=?", (args.prefix,))
    con.execute("DELETE FROM kv WHERE scope='customModels' AND key LIKE ?", (f"{args.prefix}|%",))
    con.commit()
    con.close()
    print(f"[✓] removed node {node_id} + {n} connection(s) + kv rows")
    print("[i] restart 9Router if a model list still shows stale entries")


# --------------------------------------------------------------------------- models sync
def sync_models(con, prefix: str, proxy_url: str, include_unavailable: bool = False) -> dict:
    """Mirror the proxy catalog into 9Router's customModels kv rows.

    This is what makes the provider page in the 9Router dashboard behave like
    every other provider (per-model enable/disable toggles, aliases, test
    buttons): the GUI lists models from the customModels kv rows keyed
    `<alias>|<model-id>|llm` — the same rows the dashboard's own
    "Add model" / "Import models" buttons write. The ChatGPT/Qwen/Meta web
    bridges use exactly this pattern.
    """
    try:
        data = http_json(proxy_url.rstrip("/") + "/v1/models", timeout=15)
    except Exception as e:
        return {"error": f"proxy catalog fetch failed: {e}"}
    all_models = [m for m in data.get("data", []) if m.get("id")]
    keep = [m for m in all_models if include_unavailable or m.get("available", True)]
    keep_ids = {m["id"] for m in keep}
    now = now_iso()
    added, removed = [], []
    for m in keep:
        aliases_to_register = [prefix, f"openai-compatible-chat-{prefix}"]
        for p_alias in aliases_to_register:
            key = f"{p_alias}|{m['id']}|llm"
            val = json.dumps({"providerAlias": p_alias, "id": m["id"], "type": "llm", "name": m["id"]})
            cur = con.execute("SELECT value FROM kv WHERE scope='customModels' AND key=?", (key,)).fetchone()
            if cur is None or cur["value"] != val:
                con.execute(
                    "INSERT INTO kv(scope, key, value) VALUES('customModels', ?, ?) "
                    "ON CONFLICT(scope, key) DO UPDATE SET value=excluded.value",
                    (key, val))
                if cur is None and p_alias == prefix:
                    added.append(m["id"])
    for p_alias in [prefix, f"openai-compatible-chat-{prefix}"]:
        for row in con.execute("SELECT key FROM kv WHERE scope='customModels' AND key LIKE ?", (f"{p_alias}|%",)):
            parts = row["key"].split("|")
            if len(parts) >= 2:
                mid = parts[1]
                if mid not in keep_ids:
                    con.execute("DELETE FROM kv WHERE scope='customModels' AND key=?", (row["key"],))
                    if p_alias == prefix:
                        removed.append(mid)
    return {"imported": [m["id"] for m in keep], "added": added, "removed": removed,
            "skipped_unavailable": sorted({m["id"] for m in all_models} - keep_ids)}


def cmd_sync_models(args):
    con = open_db(args.db)
    node_id, node_data, _ = find_node(con, args.prefix)
    if node_id is None:
        sys.exit("provider node not found — run `register` first")
    res = sync_models(con, args.prefix, args.proxy_url, include_unavailable=args.all)
    con.commit()
    con.close()
    if "error" in res:
        sys.exit(res["error"])
    print(f"[✓] customModels synced for '{args.prefix}': "
          f"{len(res['imported'])} imported, +{len(res['added'])} new, -{len(res['removed'])} removed")
    if res["skipped_unavailable"]:
        print(f"    unavailable upstream (not imported): {', '.join(res['skipped_unavailable'])}")
    print("    dashboard → Providers → freebuff now lists these models like any other provider")


# --------------------------------------------------------------------------- helpers
def cmd_print_key(args):
    """Print the first active 9Router API key (for scripts/verify.sh)."""
    con = open_db(args.db)
    row = con.execute("SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1").fetchone()
    con.close()
    if row:
        print(row["key"])


# --------------------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser(prog="freebuff9r", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DEFAULT_DB, help=f"9Router SQLite path (default {DEFAULT_DB})")
    p.add_argument("--prefix", default=DEFAULT_PREFIX, help=f"provider prefix (default {DEFAULT_PREFIX})")
    p.add_argument("--name", default=DEFAULT_NAME, help="provider node display name")
    p.add_argument("--proxy-url", default=DEFAULT_PROXY, help=f"freebucks-proxy base URL (default {DEFAULT_PROXY})")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("register", help="create/refresh the provider node (+ seed connection)")
    s.add_argument("--placeholder-key", default=None,
                   help="seed connection apiKey (defaults to 'freebuff-bridge-pending')")
    s.set_defaults(fn=cmd_register)

    s = sub.add_parser("login-url", help="start a device login flow; prints the URL to open")
    s.set_defaults(fn=cmd_login_url)

    s = sub.add_parser("wait-login", help="poll a started login flow and register the token")
    s.add_argument("--fingerprint", required=True)
    s.add_argument("--hash", required=True)
    s.add_argument("--expires-at", required=True)
    s.add_argument("--timeout", type=int, default=600)
    s.add_argument("--interval", type=int, default=5)
    s.add_argument("--replace", action="store_true", help="refresh an existing connection for the same email")
    s.set_defaults(fn=cmd_wait_login)

    s = sub.add_parser("add-token", help="attach a pasted FreeBuff token as a new connection")
    s.add_argument("--token", required=True)
    s.add_argument("--label", default=None)
    s.add_argument("--replace-seed", action="store_true", default=True)
    s.set_defaults(fn=cmd_add_token)

    s = sub.add_parser("status", help="show registration + proxy health")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("verify", help="end-to-end verification")
    s.add_argument("--router-url", default=os.environ.get("NINE_ROUTER_URL", "http://127.0.0.1:20128"))
    s.add_argument("--router-key", default=os.environ.get("NINE_ROUTER_KEY", ""))
    s.add_argument("--model", default=None, help="model id for the live chat probe (e.g. freebuff/z-ai/glm-5.3-flash)")
    s.add_argument("--prompt", default=None, help="chat probe prompt (default: ping)")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("remove", help="remove node + connections + kv rows")
    s.set_defaults(fn=cmd_remove)

    s = sub.add_parser("sync-models", help="mirror the proxy catalog into customModels rows (GUI parity)")
    s.add_argument("--all", action="store_true", help="also import models upstream marks unavailable")
    s.set_defaults(fn=cmd_sync_models)

    s = sub.add_parser("_print_key", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_print_key)

    args = p.parse_args()
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
