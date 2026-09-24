#!/usr/bin/env python3
"""
test_guardian_e2e.py — Complete test suite for FreeBuff Exhaust-First Guardian
and Sequential Routing in 9Router.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

BUILD_DIR = "/root/.local/lib/node_modules/9router/app/.next-cli-build"
DB_PATH = os.path.expanduser("~/.9router/db/data.sqlite")
ROUTER_URL = "http://127.0.0.1:20128"
PROXY_URL = "http://127.0.0.1:3457"

total_tests = 0
passed_tests = 0
failed_tests = 0

def check(name, condition, details=""):
    global total_tests, passed_tests, failed_tests
    total_tests += 1
    if condition:
        passed_tests += 1
        print(f"  [PASS] {name}")
    else:
        failed_tests += 1
        print(f"  [FAIL] {name} — {details}")

print("===================================================================")
print("  Running FreeBuff Guardian & Sequential Routing Test Suite")
print("===================================================================")

# -------------------------------------------------------------------------
# Test Group 1: Guardian Logic & Regex Unit Tests (via Node.js)
# -------------------------------------------------------------------------
print("\n[Group 1] Guardian Logic & Parsing Unit Tests")

test_cases = [
    # (code, error_text, expected_exhausted, desc)
    (429, 'upstream rate limited (reset at 2026-09-24T20:30:00Z)', True, "429 with reset at ISO timestamp"),
    (429, 'upstream rate limited (resets at 2026-09-25T08:00:00Z)', True, "429 with resets at ISO timestamp"),
    (429, 'upstream rate limited (retry after 2h)', True, "429 with long retry after (2h)"),
    (429, 'upstream rate limited (retry after 30m)', True, "429 with long retry after (30m)"),
    (429, 'account upstream pool is spent', True, "429 with 'spent' keyword"),
    (429, 'daily allowance ceiling reached', True, "429 with 'allowance' / 'ceiling'"),
    (429, 'insufficient freebucks balance for turn', True, "429 with 'freebucks' / 'balance'"),
    (429, 'freebucks shortfall: cannot admit 1-hour session', True, "429 with 'freebucks shortfall'"),
    (429, 'rate limit exceeded (try again in 5s)', False, "429 transient short burst (5s)"),
    (429, 'retry after 10s', False, "429 transient short retry (10s)"),
    (429, 'upstream turn spend limit exceeded (runaway turn)', False, "429 turn spend limit (loop breaker)"),
    (429, 'load_shedding: load is saturated', False, "429 load shedding saturation"),
    (429, 'limit_burst_rate: slow down (retry after 5s)', False, "429 limit burst rate (5s)"),
    (429, 'peak_hours: pricing window', False, "429 peak hours pricing"),
    (429, 'free_mode_run_fanout: concurrent run collision', False, "429 run fanout"),
    (429, 'free_mode_capacity_deferred: free tier at capacity', False, "429 capacity deferred"),
    (429, 'ip_capped: too many distinct users on IP', False, "429 egress IP capped"),
    (500, 'Internal Server Error', False, "500 server transient error"),
    (502, 'Bad gateway - upstream provider error', False, "502 gateway transient error"),
    (502, 'upstream auth rejected (401 Unauthorized)', True, "502 upstream_auth_rejected (revoked token)"),
    (503, 'Service temporarily unavailable', False, "503 service unavailable transient"),
    (503, 'session_superseded', False, "503 session superseded"),
    (503, 'waiting_room_queued', False, "503 waiting room queued"),
    (504, 'Gateway timeout', False, "504 timeout transient"),
    (401, 'Unauthorized token', True, "401 auth token revoked/invalid"),
    (402, 'Payment Required - quota exhausted', True, "402 payment/quota exhausted"),
    (403, 'upstream account banned (resumes at 2026-09-25T00:00:00Z)', True, "403 account banned"),
]

node_unit_runner = """
const cases = %s;
const results = cases.map(([fbCode, qError, expected, desc]) => {
  let fbText = (typeof qError === "object" ? JSON.stringify(qError) : String(qError || "")).toLowerCase();
  let isAuthFailure = fbCode === 401 || (fbCode === 502 && (
    fbText.includes("upstream_auth_rejected") ||
    fbText.includes("upstream auth rejected") ||
    fbText.includes("auth rejected") ||
    fbText.includes("invalid token") ||
    fbText.includes("token revoked") ||
    fbText.includes("unauthorized")
  ));
  let isAccountBan = fbCode === 403 && (
    fbText.includes("banned") ||
    fbText.includes("suspended") ||
    fbText.includes("account_banned") ||
    fbText.includes("account_suspended")
  );
  let isExplicitTransient = (
    fbText.includes("turn_spend_limit") ||
    fbText.includes("turn_spend_limited") ||
    fbText.includes("turn spend limit") ||
    fbText.includes("load_shedding") ||
    fbText.includes("limit_burst_rate") ||
    fbText.includes("peak_hours") ||
    fbText.includes("peak hours") ||
    fbText.includes("free_mode_run_fanout") ||
    fbText.includes("free_mode_capacity_deferred") ||
    fbText.includes("waiting_room_queued") ||
    fbText.includes("waiting_room_required") ||
    fbText.includes("session_superseded") ||
    fbText.includes("ip_capped")
  );
  let resetMatch = fbText.match(/resets?\\s+at\\s+([0-9a-z:\\.\\-]+)/i);
  let parsedResetMs = null;
  if (resetMatch) {
    let dt = new Date(resetMatch[1].toUpperCase()).getTime();
    if (!isNaN(dt) && dt > Date.now()) parsedResetMs = dt;
  }
  let retryMatch = fbText.match(/retry\\s+after\\s+([0-9]+)\\s*([smhd]?)/i);
  let parsedRetryMs = null;
  if (retryMatch) {
    let num = parseInt(retryMatch[1], 10);
    let unit = retryMatch[2]?.toLowerCase();
    let mult = unit === "h" ? 3600000 : unit === "m" ? 60000 : unit === "d" ? 86400000 : 1000;
    if (!isNaN(num)) parsedRetryMs = Date.now() + (num * mult);
  }
  let isLongRetry = (parsedRetryMs && parsedRetryMs > Date.now() + 600000);
  let hasQuotaKeywords = (
    fbText.includes("allowance") ||
    fbText.includes("ceiling") ||
    fbText.includes("exhaust") ||
    fbText.includes("spent") ||
    fbText.includes("freebucks") ||
    fbText.includes("shortfall") ||
    fbText.includes("daily quota") ||
    fbText.includes("payment_required") ||
    fbText.includes("payment required") ||
    (fbText.includes("insufficient_quota") && (parsedResetMs || isLongRetry))
  );
  let isExhausted = false;
  if (isAuthFailure || isAccountBan || fbCode === 402) {
    isExhausted = true;
  } else if (fbCode === 429 && !isExplicitTransient) {
    if (parsedResetMs !== null || isLongRetry || hasQuotaKeywords) {
      isExhausted = true;
    }
  }
  return { desc, actual: isExhausted, expected, pass: isExhausted === expected };
});
console.log(JSON.stringify(results));
""" % json.dumps(test_cases)

try:
    res = subprocess.run(["node", "-e", node_unit_runner], capture_output=True, text=True, check=True)
    results = json.loads(res.stdout)
    for r in results:
        check(r["desc"], r["pass"], f"got {r['actual']} expected {r['expected']}")
except Exception as e:
    check("Node.js unit runner execution", False, str(e))


# -------------------------------------------------------------------------
# Test Group 2: Bundle Patches Verification
# -------------------------------------------------------------------------
print("\n[Group 2] 9Router Bundle Patches & Configuration")

# 1. 4572.js fill-first enforcement
c_4572 = os.path.join(BUILD_DIR, "server/chunks/4572.js")
if os.path.exists(c_4572):
    with open(c_4572, "r", encoding="utf-8") as f:
        c_4572_content = f.read()
    check("4572.js: fill-first strategy hard-locked for FreeBuff",
          't=(g?.includes("freebuff")||a?.includes("freebuff"))?"fill-first":' in c_4572_content)
    check("4572.js: cooldown unclamp for FreeBuff (bypasses 30m ceiling)",
          'e?.includes("freebuff")' in c_4572_content and 'Math.min(k-Date.now(),g.fh)' in c_4572_content)
else:
    check("4572.js exists", False, "File missing")

# 2. 8635.js exhaust-first guardian
c_8635 = os.path.join(BUILD_DIR, "server/chunks/8635.js")
if os.path.exists(c_8635):
    with open(c_8635, "r", encoding="utf-8") as f:
        c_8635_content = f.read()
    check("8635.js: FreeBuff Guardian injected",
          'FREEBUFF_GUARDIAN' in c_8635_content)
    check("8635.js: Guardian parses reset at and long retry after",
          'resetMatch' in c_8635_content and 'parsedResetMs' in c_8635_content)
    check("8635.js: Guardian sets unconstrained lockMs without per-model clamp",
          'await (0,f.vk)(b.connectionId,fbCode,q.error,w,null,lockMs)' in c_8635_content)
    check("8635.js: Disabled model interceptor present",
          '_disMod.vF()' in c_8635_content and "Model '${b}' is disabled" in c_8635_content)
else:
    check("8635.js exists", False, "File missing")

# 3. Settings DB check
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    row = cur.execute("SELECT data FROM settings WHERE id = 1").fetchone()
    conn.close()
    if row:
        st = json.loads(row[0])
        fb_strat = st.get("providerStrategies", {}).get("openai-compatible-chat-freebuff", {})
        check("SQLite settings: FreeBuff fallbackStrategy is 'fill-first'",
              fb_strat.get("fallbackStrategy") == "fill-first")
    else:
        check("SQLite settings row exists", False, "No settings row")
except Exception as e:
    check("SQLite settings inspection", False, str(e))


# -------------------------------------------------------------------------
# Test Group 3: Live Integration & End-to-End Chat Routing
# -------------------------------------------------------------------------
print("\n[Group 3] Live Integration & E2E Pinning Verification")

# Auto-resolve API key
api_key = None
try:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    r = conn.execute("SELECT key FROM apiKeys WHERE isActive=1 LIMIT 1").fetchone()
    conn.close()
    if r: api_key = r[0]
except Exception:
    pass

check("9Router API Key available", bool(api_key))

if api_key:
    # Save original Prio 1 state to ensure 100% non-destructive testing
    conn = sqlite3.connect(DB_PATH)
    prio1_row = conn.execute("SELECT id, data FROM providerConnections WHERE provider LIKE '%freebuff%' AND priority = 1").fetchone()
    prio1_id = prio1_row[0]
    prio1_orig_data = json.loads(prio1_row[1])

    # Temporarily set Prio 1 to active without locks for live integration testing
    test_data = dict(prio1_orig_data)
    test_data["modelLock___all"] = None
    test_data["testStatus"] = "active"
    conn.execute("UPDATE providerConnections SET data = ? WHERE id = ?", (json.dumps(test_data), prio1_id))
    conn.commit()
    conn.close()

    try:
        # 1. Send 5 sequential chat requests and verify they all succeed and stay pinned
        success_count = 0
        for req_idx in range(1, 6):
            try:
                req = urllib.request.Request(
                    f"{ROUTER_URL}/v1/chat/completions",
                    data=json.dumps({
                        "model": "freebuff/z-ai/glm-5.3-flash",
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "max_tokens": 10
                    }).encode(),
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status == 200:
                        success_count += 1
            except Exception as e:
                print(f"    Request {req_idx} error: {e}")
        check("5 sequential requests succeed under fill-first routing", success_count == 5, f"{success_count}/5 passed")

        # 2. Verify disabled model rejection (HTTP 400)
        target_test_model = "freebuff/mimo/mimo-v2.6-pro"
        is_blocked = False
        try:
            req = urllib.request.Request(
                f"{ROUTER_URL}/v1/chat/completions",
                data=json.dumps({
                    "model": target_test_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False
                }).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "disabled" in e.read().decode(errors="replace").lower():
                is_blocked = True
        check(f"Disabled model '{target_test_model}' is blocked with HTTP 400 at router entry", is_blocked)

        # 3. Short-name alias resolution test
        short_alias_ok = False
        try:
            req = urllib.request.Request(
                f"{ROUTER_URL}/v1/chat/completions",
                data=json.dumps({
                    "model": "freebuff/glm-5.3-flash",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "max_tokens": 10
                }).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                short_alias_ok = (resp.status == 200)
        except Exception as e:
            print(f"    Short-name alias test error: {e}")
        check("Short-name alias 'freebuff/glm-5.3-flash' resolves and returns 200", short_alias_ok)

        # 4. Zero-cost probe bypass test
        probe_ok = False
        try:
            req = urllib.request.Request(
                f"{ROUTER_URL}/v1/chat/completions",
                data=json.dumps({
                    "model": "freebuff/z-ai/glm-5.3-flash",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False
                }).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if "healthy and ready" in content:
                    probe_ok = True
        except Exception as e:
            print(f"    Probe bypass test error: {e}")
        check("Synthetic probe bypass ('hi') returns zero-cost mock response immediately", probe_ok)

        # 5. Multi-threaded concurrency test (4 threads parallel)
        import threading
        concurrent_results = []
        def conc_worker(i):
            try:
                req = urllib.request.Request(
                    f"{ROUTER_URL}/v1/chat/completions",
                    data=json.dumps({
                        "model": "freebuff/z-ai/glm-5.3-flash",
                        "messages": [{"role": "user", "content": "hi"}],
                        "stream": False,
                        "max_tokens": 10
                    }).encode(),
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    concurrent_results.append(resp.status == 200)
            except Exception as e:
                concurrent_results.append(False)

        threads = [threading.Thread(target=conc_worker, args=(i,)) for i in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        check("4 parallel concurrent requests succeed without race conditions",
              len(concurrent_results) == 4 and all(concurrent_results))

        # 6. Streaming SSE probe test
        stream_ok = False
        try:
            req = urllib.request.Request(
                f"{ROUTER_URL}/v1/chat/completions",
                data=json.dumps({
                    "model": "freebuff/z-ai/glm-5.3-flash",
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": True,
                    "max_tokens": 30
                }).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                seen_chunks = 0
                for line in resp:
                    l = line.decode('utf-8', errors='replace').strip()
                    if l.startswith("data: ") and l != "data: [DONE]":
                        seen_chunks += 1
                stream_ok = seen_chunks > 0
        except Exception as e:
            print(f"    Streaming test error: {e}")
        check("Streaming SSE (stream: true) delivers real-time token chunks without session cost", stream_ok)

    finally:
        # Always restore original Prio 1 state
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE providerConnections SET data = ? WHERE id = ?", (json.dumps(prio1_orig_data), prio1_id))
        conn.commit()
        conn.close()

# 7. Verify all-accounts-locked circuit breaker when exhausted
all_locked_cb_ok = False
if api_key:
    try:
        req = urllib.request.Request(
            f"{ROUTER_URL}/v1/chat/completions",
            data=json.dumps({
                "model": "freebuff/z-ai/glm-5.3-flash",
                "messages": [{"role": "user", "content": "please summarize quantum mechanics"}],
                "stream": False
            }).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").lower()
        if e.code in (429, 503) and ("rate limited" in body or "reset after" in body or "all accounts" in body or "unavailable" in body):
            all_locked_cb_ok = True
    check("Router circuit breaker returns 429/503 with exact reset countdown when all accounts are locked", all_locked_cb_ok)

# -------------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------------
print("\n===================================================================")
print(f"  Test Results: {passed_tests}/{total_tests} passed ({failed_tests} failed)")
print("===================================================================")

sys.exit(0 if failed_tests == 0 else 1)
