# freebuff-9router

Serve the **FreeBuff** free coding models (GLM 5.3 Flash, DeepSeek V4 Flash, MiMo, Solar Pro, …)
through **[9Router](https://9router.com)** as a first-class provider, using
**freebuff-proxy** as a local OpenAI-compatible gateway.

```
your tools (Hermes / OpenCode / Cline / aider / codex / any OpenAI client)
        │
        ▼
9Router  (localhost:20128, prefix: freebuff/*)
        │  OpenAI-compatible, Bearer = your FreeBuff token
        ▼
freebuff-proxy  (127.0.0.1:3457, bridge mode)
        │  wire-translated, CLI-faithful session lifecycle
        ▼
codebuff.com  (FreeBuff upstream)
```

## What you get

- `freebuff/<model-id>` entries on `GET /v1/models` of 9Router — live-fetched
  from the proxy's catalog on every request, filtered by the per-model toggles
  in the dashboard (Providers → FreeBuff). The toggles are the single source
  of truth: what you enable there is exactly what `/model` pickers serve;
  disable one and it vanishes within a second (see **Model list sync** below).
- One 9Router **connection per FreeBuff account**, governed by the **Fill-First Sequential Routing & Exhaust-First Session Guardian**: FreeBuff charges credits (Freebucks) upon 1-hour session admission rather than per-token. Using Round-Robin would trigger simultaneous 1-hour sessions across multiple accounts, leading to disastrous multi-session bleeding where all accounts burn their daily quota in parallel! Instead, FreeBuff connection selection is hard-locked to `fill-first`. 9Router pins requests strictly to the current active account until its daily quota is genuinely exhausted. Transient server errors (500–504) and short rate limits (429) keep the account pinned; only genuine daily exhaustion triggers sequential promotion with an unconstrained lockout until the exact upstream `resetAt` time.
- **Bridge mode** end to end: the FreeBuff token lives *only* in 9Router's SQLite and is
  relayed per-request; the proxy stores no tokens and needs no pool configuration.
- **Zero 9Router patches.** Everything is registered through 9Router's own
  `openai-compatible` provider-node mechanism (the same rows its dashboard writes), so
  `npm i -g 9router` updates do not touch it.
- **Antigravity-Grade Automated Onboarding**: Direct 1-click device login right in the 9Router Web UI.
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
sudo ./install.sh            # builds + installs freebuff-proxy, registers 9Router provider
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

#### Option A: Directly from 9Router Web UI (Recommended)
1. Go to `http://localhost:20128/dashboard/providers/openai-compatible-chat-freebuff`
2. Click **"Add Connection"**.
3. A modal opens with the login link and code, and **automatically launches the GitHub login page** in a new tab.
4. Log in with your secondary GitHub account.
5. The modal automatically polls upstream, imports the session token and email, and saves the connection into your pool!

#### Option B: Terminal CLI
```bash
python3 freebuff9r.py login-url        # prints a URL + flow ids
# open the URL in a private window, log in with the OTHER GitHub account, then:
python3 freebuff9r.py wait-login --fingerprint <FP> --hash <HASH> --expires-at <EXP>
```

Each account becomes one 9Router connection under the same `freebuff` prefix.

## What install.sh does (so you can audit it)

1. Builds `freebuff-proxy` from the pinned upstream release tag into `/usr/local/bin/`.
2. Creates a locked-down systemd service `freebuff-proxy.service`:
   dedicated system user, `ProtectSystem=strict`, loopback-only bind
   (`LISTEN_ADDR=127.0.0.1:3457`), `SAFE_MODE=true`, `COST_MODE=free`,
   bridge mode (`AUTH_TOKENS` empty).
3. Backs up `~/.9router/db/data.sqlite`, then registers the provider node +
   seed connection via `freebuff9r.py` (SQLite rows identical to what the
   9Router dashboard writes — no bundle patches, survives updates).
4. Applies `patch-9router-ui.py` to enable official FreeBuff high-resolution branding and 1-click device login.
5. Starts the FreeBuff device login flow and hands you the URL.

## Update survivability (the point of this repo)

| State | Lives in | Survives `npm i -g 9router`? |
|---|---|---|
| provider node + connections | `~/.9router/db/data.sqlite` (outside node_modules) | ✅ |
| FreeBuff tokens | `providerConnections.data.apiKey` (same DB) | ✅ |
| model list | live-fetched from the proxy's `/v1/models` per request | ✅ always fresh |
| proxy binary + systemd unit | `/usr/local/bin` + `/etc/systemd/system` | ✅ (independent of 9Router) |
| proxy env | `/etc/freebuff-proxy/env` (0600) | ✅ |

No file inside 9Router's install tree is permanently modified. 9Router re-reads
`providerConnections` from SQLite on every request, so registration needs **no restart**
and cannot be wiped by an update. After a 9Router update, just re-run
`python3 freebuff9r.py status` to confirm.

## Removal

```bash
sudo systemctl disable --now freebuff-proxy
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

- **ToS risk.** Driving FreeBuff through a proxy carries account risk: *"Using FreeBuff tokens through a proxy violates FreeBuff/Codebuff terms of service. Accounts may be suspended or banned."* Use throwaway/free accounts you can afford to lose.
- **Your prompts go to Codebuff** — same as using the official FreeBuff CLI. Do not send
  private code, credentials, or client data through any free upstream.
- The proxy's anti-ban features (`SAFE_MODE`, jitter, rotation) reduce but do not
  eliminate detection; IP quality matters (datacenter IPs are scrutinized harder).

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `freebuff/*` models missing from `/v1/models` | proxy down? `systemctl status freebuff-proxy`; then `python3 freebuff9r.py status` |
| chat returns `502 upstream_auth_rejected` | the token on that connection expired/revoked — re-run the login flow with `--replace` |
| `503 session_superseded` | another client used the same account's seat; wait or use a second account |
| 429 storms | add more accounts (each = one connection) or lower traffic; FreeBuff resets daily |
| after 9Router update models vanish | re-run `python3 freebuff9r.py status`; if the DB schema changed, re-run `register` |
| chat fails with `bridge: token validation failed: upstream has no active session` | you built the proxy **without** our patch — use `install.sh` (applies `patches/0001-*.patch`, see below) |

## Patches (upstream fixes this repo carries)

Our patches live in [`patches/`](patches/) and are applied by `install.sh`
right after clone — idempotent: skipped when already applied, and a loud
hard-fail when a patch no longer applies.

### `0001-bridge-accept-idle-tokens.patch`
Upstream v1.18.2's bridge entry creation rejects any token whose zero-cost probe returns the **healthy idle** state (`status: "none"`). The patch makes the bridge cache accept the idle state and let the session manager admit on demand.

### `0002-probe-bypass-and-refund-settle.patch`
Detects zero-token healthcheck and dashboard test requests (such as the flask icon tests in 9Router) and responds locally at zero Freebucks cost.

### `0003-models-token-validation.patch`
Hooks into `GET /v1/models` in bridge mode to validate client-supplied Bearer tokens against the upstream session endpoint for zero-cost live verification in the GUI.

## High-Grade 9Router GUI / Web Interface Integration

The included `patch-9router-ui.py` script automatically enhances the 9Router Web UI with an **Antigravity-grade automated onboarding experience**:
- **One-Click Automated Login (Like Antigravity / GitHub Device Flow)**: Clicking "Add Connection" immediately opens a dedicated modal with the verification URL and code, and **simultaneously opens Codebuff's GitHub login in a new browser tab**.
- **Real-Time Automated Token & Account Enrollment**: Background polling checks the upstream login status every 3 seconds. The moment you authenticate in your browser, your auth token and email are retrieved, automatically stored/updated in 9Router's database, and the modal shows "Connected Successfully!" before refreshing your connection list.
- **Official High-Resolution Vector Branding**: the authentic FreeBuff mark — the white geometric glyph of two interlocking L-strokes forming the "F" on a black squircle, reconstructed pixel-exact from the official freebuff.com site SVG and apple-touch-icon — rendered at 512/256/128/32px with transparent outer corners, displayed natively across the providers catalog and connection cards.
- **Antigravity-Grade Available Models UI & Control**: Instead of generic OpenAI tables, FreeBuff renders the exact Antigravity model card interface with robot avatars, monospace model chips, capability badges (Vision, Reasoning), instant copy buttons, batch controls ("Active All", "Disable All"), per-model hover-to-disable actions, and a "Disabled models (N):" section with one-click restore pills.
- **Short-Name Aliasing**: Seamlessly maps standard short names (`deepseek-v4-flash`, `glm-5.3-flash`, `solar-pro`) and upstream paths (`deepseek/deepseek-v4-flash`, `z-ai/glm-5.3-flash`, `upstage/solar-pro4`) to upstream FreeBuff models.
- **Idempotent & Safe**: Automatically verifies syntax via `node -c` with instant rollback on any issue, and integrates seamlessly into the post-update hook.
- Detailed step-by-step visual documentation is available in [docs/WEB_UI_GUIDE.md](docs/WEB_UI_GUIDE.md).

## Model list sync (dashboard toggles ⇆ /model pickers)

The models a `/model` picker (Hermes, OpenCode, …) lists for `freebuff/*` are an
exact, live function of the toggle switches in the 9Router dashboard
(Providers → FreeBuff):

- **How it works:** the dashboard's per-model toggle list is rendered from
  `kv` scope `customModels` rows (one `<alias>|<model-id>|llm` row per model);
  the toggle state lives in scope `disabledModels`. 9Router's `/v1/models`
  serves the union of the proxy's live catalog and those rows, **minus** the
  disabled set — the disabled filter applies to customModels rows too, so a
  model you switch off vanishes from every picker instantly (no restart), and
  the router actively refuses it (HTTP 400) if a stale client still asks.
- **`scripts/sync-models.py`** — audit + auto-repair, idempotent: re-mirrors
  the customModels toggle list from the live proxy catalog (so upstream model
  adds/retires appear as new toggles), removes stray `disabledModels` rows
  under the prefix key (which would silently override a UI re-enable), and
  invalidates Hermes's on-disk picker cache
  (`~/.hermes/provider_models_cache.json`, 1h TTL) so a toggle shows up on the
  next picker open instead of an hour later. `--check` = read-only.
- **`scripts/sync-models-watch.py`** + `systemd/freebuff-model-sync.service` —
  polls the toggle-relevant DB state (loop-safe: ignores 9Router's own
  constant write traffic and its own idempotent writes) and reconciles
  automatically ~1s after every UI click. Enable once and every dashboard
  add/remove lands in `/model` by itself:

```bash
sudo install -m644 systemd/freebuff-model-sync.service /etc/systemd/system/
sudo systemctl enable --now freebuff-model-sync
```

## Files

```
freebuff9r.py                  all-in-one manager (register/add-token/login-url/wait-login/sync-models/status/verify/remove)
install.sh                     end-to-end installer (build + systemd + registration + UI patch + login)
patch-9router-ui.py            high-grade 9Router GUI/UX patcher (first-class Web UI support)
scripts/verify.sh              CI-style smoke test of the whole chain
scripts/sync-models.py         audit + repair UI-toggle ⇆ /model sync (alias hygiene, cache invalidation)
scripts/sync-models-watch.py   watchdog: auto-reconcile ~1s after every dashboard toggle
systemd/freebuff-proxy.service service unit (hardened, loopback-only)
systemd/freebuff-model-sync.service  model-sync watchdog unit
.env.example                   proxy environment template
assets/freebuff.svg            official vector brand asset (Codebuff / FreeBuff mark)
assets/freebuff.png            official 512x512 high-resolution icon
docs/ARCHITECTURE.md           how the pieces talk (wire-level)
docs/SECURITY.md               threat model + hardening checklist
docs/WEB_UI_GUIDE.md           detailed guide for 9Router GUI & automated device login
patches/0001-bridge-accept-idle-tokens.patch
patches/0002-probe-bypass-and-refund-settle.patch
patches/0003-models-token-validation.patch
```

## Credits & license

- [freebucks-proxy](https://github.com/trefeon/freebucks-proxy) (MIT) by trefeon — the gateway foundation.
- [9Router](https://www.npmjs.com/package/9router) — the router.
- This repo: MIT. Not affiliated with Codebuff/FreeBuff.
