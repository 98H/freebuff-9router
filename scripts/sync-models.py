#!/usr/bin/env python3
"""
sync-models.py — keep the FreeBuff model surface in exact 1:1 sync with the
9Router Web UI toggles, in BOTH directions:

  ┌─ Dashboard provider page (per-model toggle switches)
  │     toggle LIST  = kv scope='customModels' rows (`<alias>|<model-id>|llm`)
  │     toggle STATE = kv scope='disabledModels' (key = node id)
  └─ /v1/models (what /model pickers serve)
        = proxy live catalog ∪ customModels rows, MINUS disabledModels
          (the disabled filter applies to the merged set — customModels rows
           do NOT bypass it; verified against 9Router 0.5.86 buildModelsList)

This script reconciles the drift sources that break the 1:1 mapping:

  1. CATALOG DRIFT — upstream adds/retires a model. The customModels rows
     (the UI's toggle list) are re-mirrored from the proxy's live
     /v1/models so every current model appears as a toggle and retired
     ones disappear. This script is the ONLY writer of customModels rows.

  2. STRAY PREFIX-KEY disabledModels ROWS — the UI writes disabled state
     under the node id key only, while buildModelsList also checks the bare
     prefix key. A row there would silently override a UI re-enable, so it
     is migrated into the canonical node-id key and removed.

  3. HERMES PICKER CACHE — Hermes caches each provider's /v1/models on
     disk for up to 1h (~/.hermes/provider_models_cache.json). A UI toggle
     must show up immediately: any cache row whose freebuff/* subset
     disagrees with the current router surface is dropped so the next
     picker open re-fetches live.

It never touches the canonical disabledModels state (the user's selection
belongs to the dashboard alone) beyond the stray-prefix-key migration.

Usage:
  python3 scripts/sync-models.py            # reconcile (idempotent)
  python3 scripts/sync-models.py --check    # read-only audit, exit 1 on drift

Zero cost: local SQLite + local HTTP only; no upstream calls, no chat probes.
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request

DB = os.environ.get("NINE_ROUTER_DB", os.path.expanduser("~/.9router/db/data.sqlite"))
PROXY = os.environ.get("FREEBUFF_PROXY_URL", "http://127.0.0.1:3457")
ROUTER = os.environ.get("NINE_ROUTER_URL", "http://127.0.0.1:20128")
NODE_ID = "openai-compatible-chat-freebuff"
PREFIX = "freebuff"
ALIASES = [PREFIX, NODE_ID]


def proxy_catalog():
    req = urllib.request.Request(f"{PROXY}/v1/models")
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode())
    return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


def router_catalog(db):
    key = db.execute("SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1").fetchone()
    if not key:
        return None
    req = urllib.request.Request(
        f"{ROUTER}/v1/models", headers={"Authorization": f"Bearer {key[0]}"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())
    return sorted(
        m["id"][len(PREFIX) + 1:]
        for m in data.get("data", [])
        if m["id"].startswith(f"{PREFIX}/")
    )


def get_disabled(db, key):
    row = db.execute(
        "SELECT value FROM kv WHERE scope='disabledModels' AND key=?",
        (key,)).fetchone()
    return set(json.loads(row[0])) if row else set()


def mirror_custom_models(db, catalog):
    """Make the UI toggle list == live proxy catalog (under both alias keys)."""
    problems = []
    desired_keys = set()
    for alias in ALIASES:
        for mid in catalog:
            key = f"{alias}|{mid}|llm"
            desired_keys.add(key)
            val = json.dumps({"providerAlias": alias, "id": mid,
                              "type": "llm", "name": mid})
            cur = db.execute(
                "SELECT value FROM kv WHERE scope='customModels' AND key=?",
                (key,)).fetchone()
            if cur is None or cur[0] != val:
                problems.append(f"customModels upsert: {key}")
                db.execute(
                    "INSERT INTO kv(scope,key,value) VALUES('customModels',?,?) "
                    "ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value",
                    (key, val))
    for alias in ALIASES:
        for (key,) in db.execute(
                "SELECT key FROM kv WHERE scope='customModels' AND key LIKE ?",
                (f"{alias}|%",)).fetchall():
            if key not in desired_keys:
                problems.append(f"customModels retire: {key}")
                db.execute(
                    "DELETE FROM kv WHERE scope='customModels' AND key=?",
                    (key,))
    return problems


def reconcile_hermes_cache(served_now):
    problems = []
    cache_path = os.path.expanduser("~/.hermes/provider_models_cache.json")
    if not os.path.exists(cache_path) or served_now is None:
        return problems
    try:
        with open(cache_path) as f:
            cache = json.load(f)
        dirty = False
        for ckey, entry in list(cache.items()):
            models = entry.get("models") if isinstance(entry, dict) else None
            if not models:
                continue
            fb = sorted(m[len(PREFIX) + 1:] for m in models
                        if isinstance(m, str) and m.startswith(f"{PREFIX}/"))
            if fb and fb != served_now:
                del cache[ckey]
                dirty = True
                problems.append(f"invalidated stale Hermes picker cache: {ckey}")
        if dirty:
            with open(cache_path, "w") as f:
                json.dump(cache, f)
    except Exception as e:
        print(f"[warn] could not reconcile Hermes cache: {e}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="read-only audit")
    args = ap.parse_args()
    db = sqlite3.connect(DB)
    problems = []

    try:
        catalog = proxy_catalog()
    except Exception as e:
        print(f"[warn] proxy catalog unreachable: {e}")
        catalog = None

    # 1. UI toggle list mirrors the live catalog.
    if catalog is not None:
        if args.check:
            desired = {f"{a}|{m}|llm" for a in ALIASES for m in catalog}
            existing = {r[0] for r in db.execute(
                "SELECT key FROM kv WHERE scope='customModels' AND (key LIKE ? OR key LIKE ?)",
                (f"{PREFIX}|%", f"{NODE_ID}|%")).fetchall()}
            if existing != desired:
                problems.append(
                    f"customModels drift: +{len(desired - existing)} missing, "
                    f"-{len(existing - desired)} stale")
        else:
            problems.extend(mirror_custom_models(db, catalog))

    # 2. Stray prefix-key disabledModels rows must not exist (they would
    #    override UI re-enables); migrate into the canonical node-id key.
    d_prefix = get_disabled(db, PREFIX)
    if d_prefix:
        problems.append(
            f"stray disabledModels row under prefix key: {sorted(d_prefix)}")
        if not args.check:
            d_node = get_disabled(db, NODE_ID)
            merged = sorted(d_node | d_prefix)
            db.execute(
                "INSERT INTO kv(scope,key,value) VALUES('disabledModels',?,?) "
                "ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value",
                (NODE_ID, json.dumps(merged)))
            db.execute(
                "DELETE FROM kv WHERE scope='disabledModels' AND key=?",
                (PREFIX,))

    if not args.check:
        db.commit()

    # 3. Effective surface check: served == catalog − UI-disabled.
    disabled = get_disabled(db, NODE_ID) | get_disabled(db, PREFIX)
    served = None
    if catalog is not None:
        try:
            served = router_catalog(db)
        except Exception as e:
            print(f"[warn] router /v1/models unreachable: {e}")
        if served is not None:
            expected = sorted(m for m in catalog if m not in disabled)
            if served != expected:
                problems.append(
                    "served != catalog-disabled:\n"
                    f"  unexpected: {sorted(set(served) - set(expected))}\n"
                    f"  missing:    {sorted(set(expected) - set(served))}")

    # 4. Hermes picker cache must not pin a stale list.
    if not args.check:
        problems.extend(reconcile_hermes_cache(served))

    db.close()
    if problems:
        print("DRIFT:" if args.check else "REPAIRED:")
        for p in problems:
            print(" -", p)
        if args.check:
            sys.exit(1)
    print("[ok] FreeBuff UI toggles ⇆ /model surface in 1:1 sync.")
    if catalog is not None and served is not None:
        print(f"     catalog={len(catalog)} ui-disabled={len(disabled)} served={len(served)}")


if __name__ == "__main__":
    main()
