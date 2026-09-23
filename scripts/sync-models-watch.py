#!/usr/bin/env python3
"""
sync-models-watch.py — tiny watchdog that keeps the FreeBuff model surface
in perfect sync with the 9Router Web UI toggles, automatically.

Watches the 9Router SQLite DB for UI-driven changes (a user flipping a model
toggle in the dashboard writes to the kv table), then runs
scripts/sync-models.py to reconcile the toggle list with the live proxy
catalog and invalidate Hermes's picker cache — so /model reflects the UI
within ~1 second of the click.

Loop safety: 9Router writes to its DB almost constantly (request logging,
usage stats), so raw mtime watching would fire non-stop — and our own sync
writes would retrigger us. Instead we poll the actual toggle-relevant state
(disabledModels + customModels rows for the FreeBuff aliases) and only
reconcile when THAT content changes. Our own writes leave the content
unchanged (idempotent), so no self-trigger storm.

Zero upstream cost: local SQLite reads + local HTTP only.

Run under systemd (see systemd/freebuff-model-sync.service) or standalone:
  python3 scripts/sync-models-watch.py
"""
import os
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC = os.path.join(HERE, "sync-models.py")
DB = os.environ.get("NINE_ROUTER_DB", os.path.expanduser("~/.9router/db/data.sqlite"))
NODE_ID = "openai-compatible-chat-freebuff"
PREFIX = "freebuff"
POLL_S = 1.0


def toggle_state():
    """Fingerprint of the user-facing toggle state: (disabled, customModels keys)."""
    try:
        db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=2)
        try:
            row = db.execute(
                "SELECT value FROM kv WHERE scope='disabledModels' AND key=?",
                (NODE_ID,)).fetchone()
            disabled = row[0] if row else ""
            customs = tuple(sorted(
                r[0] for r in db.execute(
                    "SELECT key FROM kv WHERE scope='customModels' AND "
                    "(key LIKE ? OR key LIKE ?)",
                    (f"{PREFIX}|%", f"{NODE_ID}|%")).fetchall()))
            return (disabled, customs)
        finally:
            db.close()
    except Exception:
        return None  # DB busy/locked momentarily — skip this tick


def run_sync():
    r = subprocess.run(
        [sys.executable, SYNC], capture_output=True, text=True, timeout=60)
    lines = (r.stdout or "").strip().splitlines()
    print(f"[sync] {lines[-1] if lines else '(no output)'}", flush=True)
    if r.returncode != 0:
        print(f"[sync][warn] exit {r.returncode}: {r.stderr.strip()[:300]}",
              flush=True)


def main():
    print(f"[watch] watching FreeBuff toggle state in {DB}…", flush=True)
    run_sync()  # initial reconcile at boot
    last = toggle_state()
    while True:
        time.sleep(POLL_S)
        cur = toggle_state()
        if cur is not None and cur != last:
            last = cur
            print("[watch] toggle state changed — reconciling…", flush=True)
            run_sync()


if __name__ == "__main__":
    main()
