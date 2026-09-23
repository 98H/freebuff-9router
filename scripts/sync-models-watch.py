#!/usr/bin/env python3
"""
sync-models-watch.py — tiny watchdog that keeps the FreeBuff model surface
in perfect sync with the 9Router Web UI toggles, automatically.

Watches 9Router's SQLite DB (data.sqlite + its -wal) for writes; whenever the
disabledModels/customModels scopes change, runs scripts/sync-models.py to
reconcile aliases, purge stale injections, and invalidate Hermes's picker
cache so /model reflects the UI within ~1 second of the click.

Zero upstream cost: only local file mtimes + local HTTP + SQLite.

Run under systemd (see systemd/freebuff-model-sync.service) or standalone:
  python3 scripts/sync-models-watch.py
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SYNC = os.path.join(HERE, "sync-models.py")
DB = os.environ.get("NINE_ROUTER_DB", os.path.expanduser("~/.9router/db/data.sqlite"))
WATCHED = [DB, DB + "-wal", DB + "-shm"]
DEBOUNCE_S = 1.0
POLL_S = 0.5


def mtimes():
    out = []
    for p in WATCHED:
        try:
            out.append(os.path.getmtime(p))
        except OSError:
            out.append(None)
    return tuple(out)


def run_sync():
    r = subprocess.run(
        [sys.executable, SYNC], capture_output=True, text=True, timeout=60
    )
    line = (r.stdout or "").strip().splitlines()
    summary = line[-1] if line else "(no output)"
    print(f"[sync] {summary}", flush=True)
    if r.returncode != 0:
        print(f"[sync][warn] exit {r.returncode}: {r.stderr.strip()[:300]}", flush=True)


def main():
    print(f"[watch] watching {DB} for UI toggle changes…", flush=True)
    last = mtimes()
    run_sync()  # initial reconcile at boot
    pending_since = None
    while True:
        time.sleep(POLL_S)
        cur = mtimes()
        if cur != last:
            last = cur
            pending_since = time.time()
        if pending_since is not None and time.time() - pending_since >= DEBOUNCE_S:
            pending_since = None
            run_sync()


if __name__ == "__main__":
    main()
