#!/usr/bin/env python3
"""
sync-models.py — keep 9Router's /v1/models surface for FreeBuff in exact
1:1 sync with the model toggles in the 9Router Web UI.

How the pipeline works (verified against 9Router 0.5.86 source):

  UI toggle (dashboard/providers/<id> page)
      │  POST /api/models/disabled   {providerAlias, ids:[…]}   (disable)
      │  DELETE /api/models/disabled {providerAlias, id}        (enable)
      ▼
  kv table, scope='disabledModels', key=<providerAlias>, value=JSON array
      │
      ▼  (read fresh on EVERY request — no caching)
  buildModelsList() in /api/../v1/models
      │  m(alias, modelId) filter drops disabled rows
      ▼
  GET /v1/models  ← what /model pickers (Hermes, OpenCode, …) consume

Two things break that 1:1 mapping, and this script fixes both:

  1. STALE customModels ROWS. Rows in kv scope='customModels' whose
     providerAlias matches the FreeBuff node id ("openai-compatible-chat-freebuff")
     or its prefix ("freebuff") are force-injected into buildModelsList
     output WITHOUT passing through the disabledModels filter. They were
     written by older tooling before the proxy exposed a live /v1/models
     catalog. They must not exist — the proxy is the single source of
     truth for the catalog, and disabledModels is the single source of
     truth for user selection.

  2. STRAY PREFIX-KEY ROWS. The UI writes disabledModels under the provider
     NODE ID for openai-compatible providers ("openai-compatible-chat-freebuff"),
     while buildModelsList checks disabled under BOTH the node id AND the
     prefix ("freebuff"). A row under the prefix key silently overrides UI
     re-enables (the UI's DELETE only touches the node-id key). This script
     migrates any stray prefix-key entries into the canonical node-id key
     and removes the prefix row.

Usage:
  python3 scripts/sync-models.py            # audit + repair (idempotent)
  python3 scripts/sync-models.py --check    # read-only; exit 1 if drift

Zero cost: no upstream calls, no chat probes. Only local SQLite + the
local proxy catalog endpoint.
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request

DB = os.environ.get("NINE_ROUTER_DB", os.path.expanduser("~/.9router/db/data.sqlite"))
PROXY = os.environ.get("FREEBUFF_PROXY_URL", "http://127.0.0.1:3457")
NODE_ID = "openai-compatible-chat-freebuff"
PREFIX = "freebuff"


def get_db():
    return sqlite3.connect(DB)


def proxy_catalog():
    """Live catalog from freebuff-proxy (local, free)."""
    req = urllib.request.Request(f"{PROXY}/v1/models")
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode())
    return sorted(m["id"] for m in data.get("data", []))


def router_catalog(db):
    """What 9Router currently serves for freebuff/* (via local HTTP)."""
    key = db.execute("SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1").fetchone()
    if not key:
        return None
    req = urllib.request.Request(
        "http://127.0.0.1:20128/v1/models",
        headers={"Authorization": f"Bearer {key[0]}"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())
    return sorted(
        m["id"][len(PREFIX) + 1:]
        for m in data.get("data", [])
        if m["id"].startswith(f"{PREFIX}/")
    )


def get_disabled(db, key):
    row = db.execute(
        "SELECT value FROM kv WHERE scope='disabledModels' AND key=?", (key,)
    ).fetchone()
    return set(json.loads(row[0])) if row else set()


def set_disabled(db, key, ids):
    if ids:
        db.execute(
            "INSERT INTO kv(scope,key,value) VALUES('disabledModels',?,?) "
            "ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(sorted(ids))),
        )
    else:
        db.execute(
            "DELETE FROM kv WHERE scope='disabledModels' AND key=?", (key,)
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="read-only audit")
    args = ap.parse_args()
    db = get_db()
    problems = []

    # 1. Purge stale customModels for our aliases — they bypass the UI toggles.
    stale = db.execute(
        "SELECT key FROM kv WHERE scope='customModels' AND "
        "(key LIKE ? OR key LIKE ?)",
        (f"{PREFIX}|%", f"{NODE_ID}|%"),
    ).fetchall()
    if stale:
        problems.append(f"stale customModels rows: {len(stale)}")
        if not args.check:
            db.execute(
                "DELETE FROM kv WHERE scope='customModels' AND "
                "(key LIKE ? OR key LIKE ?)",
                (f"{PREFIX}|%", f"{NODE_ID}|%"),
            )

    # 2. Alias hygiene: the UI writes disabledModels ONLY under the node id
    #    ("openai-compatible-chat-freebuff"); buildModelsList checks BOTH the
    #    node id and the prefix ("freebuff"). A stale row under the prefix key
    #    would silently override a UI re-enable — it must NOT exist.
    d_prefix = get_disabled(db, PREFIX)
    if d_prefix:
        problems.append(f"stray disabledModels row under prefix key: {sorted(d_prefix)}")
        if not args.check:
            # Migrate anything found there into the canonical node-id key, then drop it.
            d_node = get_disabled(db, NODE_ID)
            set_disabled(db, NODE_ID, d_node | d_prefix)
            db.commit()
            set_disabled(db, PREFIX, set())

    if not args.check:
        db.commit()

    # 2b. Hermes-side propagation: the Hermes /model picker caches each
    #     provider's /v1/models response on disk for up to 1h
    #     ($HERMES_HOME/provider_models_cache.json). A UI toggle must show up
    #     immediately, not an hour later — drop any cache row whose stored
    #     catalog disagrees with the now-current router surface, so the next
    #     picker open re-fetches live.
    cache_path = os.path.expanduser("~/.hermes/provider_models_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cache = json.load(f)
            dirty = False
            served_now = router_catalog(db)
            if served_now is not None:
                for ckey, entry in list(cache.items()):
                    models = entry.get("models") if isinstance(entry, dict) else None
                    if not models:
                        continue
                    fb = sorted(
                        m[len(PREFIX) + 1:] for m in models
                        if isinstance(m, str) and m.startswith(f"{PREFIX}/")
                    )
                    if fb and fb != served_now:
                        del cache[ckey]
                        dirty = True
                        problems.append(f"invalidated stale Hermes model cache: {ckey}")
            if dirty and not args.check:
                with open(cache_path, "w") as f:
                    json.dump(cache, f)
        except Exception as e:
            print(f"[warn] could not reconcile Hermes cache: {e}")

    # 3. Verify the effective /v1/models surface equals catalog minus disabled.
    disabled = get_disabled(db, NODE_ID) | get_disabled(db, PREFIX)
    try:
        cat = proxy_catalog()
    except Exception as e:
        print(f"[warn] proxy catalog unreachable: {e}")
        cat = None
    try:
        served = router_catalog(db)
    except Exception as e:
        print(f"[warn] router /v1/models unreachable: {e}")
        served = None

    if cat is not None and served is not None:
        expected = sorted(m for m in cat if m not in disabled)
        if served != expected:
            problems.append(
                "served != catalog-disabled:\n"
                f"  unexpected: {sorted(set(served) - set(expected))}\n"
                f"  missing:    {sorted(set(expected) - set(served))}"
            )

    db.close()
    if problems:
        print("DRIFT DETECTED:" if args.check else "REPAIRED:")
        for p in problems:
            print(" -", p)
        if args.check:
            sys.exit(1)
    print("[ok] FreeBuff model surface is in 1:1 sync with the 9Router UI toggles.")
    if cat is not None and served is not None:
        print(f"     catalog={len(cat)} disabled={len(disabled)} served={len(served)}")


if __name__ == "__main__":
    main()
