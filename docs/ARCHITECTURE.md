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
- multi-account rotation is 9Router's native connection priority/backoff logic, which
  the user already operates for Cline/Antigravity accounts;
- the proxy stays stateless w.r.t. tokens, so proxy restarts never touch credentials;
- the proxy dashboard still shows bridged sessions and credit state per token.

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
