# freebuff-9router

Serve the **FreeBuff** free coding models (GLM 5.3 Flash, DeepSeek V4 Flash, MiMo, Solar Pro, …)
through **[9Router](https://9router.com)** as a first-class provider, using
**[freebucks-proxy](https://github.com/trefeon/freebucks-proxy)** as a local OpenAI-compatible
gateway.

```
your tools (Hermes / OpenCode / Cline / aider / codex / any OpenAI client)
        │
        ▼
9Router  (localhost:20128, prefix: freebuff/*)
        │  OpenAI-compatible, Bearer = your FreeBuff token
        ▼
freebucks-proxy  (127.0.0.1:3457, bridge mode)
        │  wire-translated, CLI-faithful session lifecycle
        ▼
codebuff.com  (FreeBuff upstream)
```

## What you get

- `freebuff/<model-id>` entries on `GET /v1/models` of 9Router — live-fetched from the
  proxy catalog, never stale.
- One 9Router **connection per FreeBuff account**; 9Router's native multi-connection
  rotation spreads traffic across your accounts (same pattern as multiple Cline accounts).
- **Bridge mode** end to end: the FreeBuff token lives *only* in 9Router's SQLite and is
  relayed per-request; the proxy stores no tokens and needs no pool configuration.
- **Zero 9Router patches.** Everything is registered through 9Router's own
  `openai-compatible` provider-node mechanism (the same rows its dashboard writes), so
  `npm i -g 9router` updates do not touch it.
- Idempotent tooling: register, add accounts, verify, status, remove.

## Requirements

- Linux (amd64/arm64) or macOS, root or sudo
- [9Router](https://www.npmjs.com/package/9router) installed and running
- One of: prebuilt toolchain to build the proxy (Go ≥ 1.26 + Node ≥ 20) — see
  `install.sh`, which handles the build for you
- A GitHub account to authorize a FreeBuff token (one browser click)

## Quickstart

```bash
git clone https://github.com/98H/freebuff-9router.git
cd freebuff-9router
sudo ./install.sh            # builds + installs freebucks-proxy, registers 9Router provider
```

The installer prints a **login URL** at the end. Open it, sign in with the GitHub
account you want a token for — the token is captured and registered automatically.

Then verify:

```bash
python3 freebuff9r.py status
python3 freebuff9r.py verify --router-key <9Router API key> \
        --model freebuff/z-ai/glm-5.3-flash --prompt "say hi"
```

### Add another account

```bash
python3 freebuff9r.py login-url        # prints a URL + flow ids
# open the URL in a private window, log in with the OTHER GitHub account, then:
python3 freebuff9r.py wait-login --fingerprint <FP> --hash <HASH> --expires-at <EXP>
```

Each account becomes one 9Router connection under the same `freebuff` prefix.

## What install.sh does (so you can audit it)

1. Builds `freebucks-proxy` from the pinned upstream release tag into `/usr/local/bin/`.
2. Creates a locked-down systemd service `freebucks-proxy.service`:
   dedicated system user, `ProtectSystem=strict`, loopback-only bind
   (`LISTEN_ADDR=127.0.0.1:3457`), `SAFE_MODE=true`, `COST_MODE=free`,
   bridge mode (`AUTH_TOKENS` empty).
3. Backs up `~/.9router/db/data.sqlite`, then registers the provider node +
   seed connection via `freebuff9r.py` (SQLite rows identical to what the
   9Router dashboard writes — no bundle patches, survives updates).
4. Starts the FreeBuff device login flow and hands you the URL.

## Update survivability (the point of this repo)

| State | Lives in | Survives `npm i -g 9router`? |
|---|---|---|
| provider node + connections | `~/.9router/db/data.sqlite` (outside node_modules) | ✅ |
| FreeBuff tokens | `providerConnections.data.apiKey` (same DB) | ✅ |
| model list | live-fetched from the proxy's `/v1/models` per request | ✅ always fresh |
| proxy binary + systemd unit | `/usr/local/bin` + `/etc/systemd/system` | ✅ (independent of 9Router) |
| proxy env | `/etc/freebucks-proxy/env` (0600) | ✅ |

No file inside 9Router's install tree is modified. 9Router re-reads
`providerConnections` from SQLite on every request, so registration needs **no restart**
and cannot be wiped by an update. After a 9Router update, just re-run
`python3 freebuff9r.py status` to confirm.

## Removal

```bash
sudo systemctl disable --now freebucks-proxy
python3 freebuff9r.py remove
```

`remove` deletes only rows this tool created (matched by prefix + node id) and writes a
timestamped DB backup first.

## Security posture & honest risk notes

**What this stack does right**

- Proxy binds `127.0.0.1` only; the admin dashboard (`/admin`, strong random token) is
  loopback-only too. Reach it via SSH port-forward: `ssh -L 3457:127.0.0.1:3457 host`.
- Bridge mode keeps FreeBuff tokens in one place (9Router's DB, `0600`, same store that
  already holds your other providers' OAuth tokens).
- No secrets are committed anywhere in this repo; `.deploy-secrets` style files are
  git-ignored.

**What you must accept**

- **ToS risk.** Driving FreeBuff through a proxy is exactly what freebucks-proxy's own
  warning says: *"Using FreeBuff tokens through a proxy violates FreeBuff/Codebuff terms
  of service. Accounts may be suspended or banned."* Use throwaway/free accounts you can
  afford to lose.
- **Your prompts go to Codebuff** — same as using the official FreeBuff CLI. Do not send
  private code, credentials, or client data through any free upstream.
- The proxy's anti-ban features (`SAFE_MODE`, jitter, rotation) reduce but do not
  eliminate detection; IP quality matters (datacenter IPs are scrutinized harder).

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `freebuff/*` models missing from `/v1/models` | proxy down? `systemctl status freebucks-proxy`; then `python3 freebuff9r.py status` |
| chat returns `502 upstream_auth_rejected` | the token on that connection expired/revoked — re-run the login flow with `--replace` |
| `503 session_superseded` | another client used the same account's seat; wait or use a second account |
| 429 storms | add more accounts (each = one connection) or lower traffic; FreeBuff resets daily |
| after 9Router update models vanish | re-run `python3 freebuff9r.py status`; if the DB schema changed, re-run `register` |
| chat fails with `bridge: token validation failed: upstream has no active session` | you built the proxy **without** our patch — use `install.sh` (applies `patches/0001-*.patch`, see below) |

## Patches (upstream fixes this repo carries)

Our patches live in [`patches/`](patches/) and are applied by `install.sh`
right after clone — idempotent: skipped when already applied, and a loud
hard-fail when a patch no longer applies (so an upstream fix or API change is
never silently missed).

### `0001-bridge-accept-idle-tokens.patch`

Upstream v1.18.2's bridge entry creation rejects any token whose zero-cost
probe returns the **healthy idle** state (`status: "none"`, documented by the
same code as a valid state returned *alongside* `ErrNoActiveSession`). The
practical effect: every fresh FreeBuff account that has never held a session
fails every chat with `502 upstream_unavailable`. The patch makes the bridge
cache accept the idle state and let the session manager admit on demand —
which is exactly what the upstream's own pooled paths already do. If a future
upstream tag fixes this, `install.sh` will tell you to delete the patch.

## Files

```
freebuff9r.py                  all-in-one manager (register/add-token/login-url/status/verify/remove)
install.sh                     end-to-end installer (build + systemd + registration + login)
scripts/verify.sh              CI-style smoke test of the whole chain
systemd/freebucks-proxy.service  service unit (hardened, loopback-only)
.env.example                   proxy environment template
docs/ARCHITECTURE.md           how the pieces talk (wire-level)
docs/SECURITY.md               threat model + hardening checklist
```

## Credits & license

- [freebucks-proxy](https://github.com/trefeon/freebucks-proxy) (MIT) by trefeon — the gateway.
- [9Router](https://www.npmjs.com/package/9router) — the router.
- This repo: MIT. Not affiliated with Codebuff/FreeBuff.
