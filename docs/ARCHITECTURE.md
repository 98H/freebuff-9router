# Architecture

## Components

| Layer | Software | Port | State |
|---|---|---|---|
| Client | Hermes / OpenCode / Cline / aider / … | — | stateless |
| Router | 9Router (Next.js standalone) | 20128 | SQLite `~/.9router/db/data.sqlite` |
| Gateway | freebuff-proxy (Go, single binary) | 3457 (loopback) | SQLite `data/freebuff.db` (sessions/history) |
| Upstream | codebuff.com (FreeBuff) | 443 | server-side session per account |

## The wire

9Router speaks OpenAI on the client side and **OpenAI-compatible on the gateway side**
(the `openai-compatible` provider-node mechanism):

1. Client calls `POST http://localhost:20128/v1/chat/completions` with
   `model: "freebuff/z-ai/glm-5.3-flash"`.
2. 9Router resolves the prefix `freebuff` → the provider connection (priority-ordered,
   one per FreeBuff account), strips the prefix, and POSTs
   `{proxy}/v1/chat/completions` with `model: "z-ai/glm-5.3-flash"` and
   `Authorization: Bearer <connection.apiKey>`.
3. freebuff-proxy runs in **bridge mode**: the Bearer IS the upstream FreeBuff token.
   It opens/reuses a FreeBuff session for that token (one live session per account,
   exactly like the official CLI), translates the request to the upstream wire
   protocol (session admission, run start, streaming tool turns, FINISH), and
   streams an OpenAI-shaped SSE response back.
4. Credits (`freebucks`) are metered per session-hour upstream, refunded on early
   session DELETE; the proxy mirrors the upstream `prices` map.

## Why "bridge" and not "pooled"

The upstream project supports a token pool inside the proxy. This repo deliberately
pairs 9Router with **bridge mode** (the pairing the upstream's own
`server_bridge_9router_test.go` pins):

- token custody stays in 9Router's SQLite — one credential store for all providers;
- multi-account routing is governed by 9Router's connection priority, enhanced by the **FreeBuff Exhaust-First Session Guardian**;
- the proxy stays stateless w.r.t. tokens, so proxy restarts never touch credentials;
- the proxy dashboard still shows bridged sessions and credit state per token.

## FreeBuff Session Cost Model & Exhaust-First Guardian

### The Hourly Session Cost Model
Upstream FreeBuff (Codebuff) meters usage by **session admission** (charging 5–25 Freebucks per session hour depending on model tier), NOT strictly per-token:
- When a request begins, a 1-hour session is admitted upstream.
- Whether a user exchanges one quick message or continuously streams tokens, the 1-hour session fee is committed.
- **The Round-Robin Hazard (Multi-Session Bleeding):** In traditional providers, round-robin balances request loads. In FreeBuff, distributing requests round-robin across accounts would immediately admit and start 1-hour sessions on *all accounts simultaneously*. If 10 accounts each receive 1 request, 10 distinct 1-hour sessions are opened, bleeding daily Freebucks quota across all accounts in parallel.

### Solution: Fill-First & Exhaust-First Guardian Architecture
To achieve mathematical optimality and prevent session bleeding:
1. **Hard-Locked Fill-First Routing:**
   - In 9Router's connection selector (`server/chunks/4572.js`), connection routing for any provider matching `freebuff` is strictly forced to `fill-first`, regardless of user GUI settings.
   - All requests are pinned to the highest-priority active connection.
2. **Transient Error Pinning:**
   - Server errors (500, 502, 503, 504) and transient rate limits (429 with short retry or no quota exhaustion indicator) do NOT trigger account failover.
   - Failover on transient glitches would trigger a new 1-hour session on the next account. Instead, the Guardian returns the error directly to the caller, keeping the account pinned.
3. **Exhaustion-Only Sequential Promotion:**
   - Sequential promotion occurs ONLY upon genuine daily quota exhaustion:
     - HTTP 401 (token invalidated/revoked)
     - HTTP 402 (payment/freebucks balance exhausted)
     - HTTP 403 (account banned/restricted)
     - HTTP 429 containing explicit reset timestamps (`reset at ...`, `resets at ...`), long retries (>10 min), or quota keywords (`allowance`, `ceiling`, `exhaust`, `spent`, `freebucks`, `balance`, `insufficient`).
   - The exhausted connection is locked out at the connection level (`modelLock___all`) until the exact upstream `resetAt` time (or 12 hours) and the cooldown is unclamped from the default 30-minute ceiling.
   - 9Router sequentially fails over to the next priority account.
4. **Zero-Cost Probe Bypass:**
   - Synthetic health probes ("hi", "test") are answered immediately at zero cost without opening an upstream session.

## 9Router registration internals

`freebuff9r.py register` writes the same rows the dashboard's
"Providers → Add OpenAI Compatible" dialog writes:

- `providerNodes` row:
  - `id = "openai-compatible-chat-freebuff"`
  - `type = "openai-compatible"`
  - `name = "FreeBuff"`
  - `data = {"prefix": "freebuff", "apiType": "chat", "baseUrl": "http://127.0.0.1:3457/v1"}`
- `providerConnections` row (one per account):
  - `provider = <node id>`, `authType = "apikey"`, `isActive = 1`
  - `data = {"apiKey": <freebuff token>, "providerSpecificData": {"prefix", "apiType",
    "baseUrl", "nodeName": "FreeBuff", "connectionProxy*"}, "testStatus": "active"}`

Model listing needs **no static model table**: 9Router's `buildModelsList` live-fetches
`{baseUrl}/models` for openai-compatible connections with no `enabledModels` whitelist
(server chunk `7220.js`, fetcher `C()`), so the served catalog always mirrors the
proxy's current model registry (added/retired upstream models appear/disappear without
touching 9Router).

## Update survivability

Nothing is patched inside 9Router's install tree:

- DB (`~/.9router/db/data.sqlite`) is outside `node_modules` and is re-read per request
  (no restart needed after registration);
- the proxy binary/systemd unit/env are independent of 9Router;
- after a 9Router update, `freebuff9r.py status` should pass unchanged. If a 9Router
  version changes its SQLite schema, `register` re-runs idempotently and repairs rows.
