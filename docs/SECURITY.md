# Security & Threat Model

## Asset inventory

| Asset | Location | Protection |
|---|---|---|
| FreeBuff account tokens | `~/.9router/db/data.sqlite` `providerConnections.data.apiKey` | SQLite file perms + 9Router host access control; DB outside node_modules |
| 9Router API key | same DB `apiKeys` | as above |
| proxy admin token | `/etc/freebucks-proxy/env` (0640 root:freebucks-proxy) | generated 24-byte hex at install |
| proxy session/history DB | `/var/lib/freebucks-proxy/` (dedicated system user) | systemd `ProtectSystem=strict`, `ProtectHome=true`, `NoNewPrivileges=true` |

## Network exposure

- **freebucks-proxy binds `127.0.0.1:3457` only.** The admin dashboard and `/v1/*`
  are unreachable from other hosts. To use the dashboard:
  `ssh -L 3457:127.0.0.1:3457 user@host` → `http://127.0.0.1:3457/admin`.
- 9Router itself binds all interfaces by default (its own design). If this host is
  internet-facing, firewall 20128 to trusted sources or tunnel it — that is 9Router's
  concern, not introduced by this repo.
- Outbound from the proxy: `https://www.codebuff.com` (upstream wire), GitHub
  releases API (6h-cached update check), `www.cloudflare.com/cdn-cgi/trace` (egress
  IP probe). No telemetry destination beyond what the upstream proxy does (audited
  against its source; no third-party endpoints, no obfuscated exfiltration).

## Trust boundaries

1. **Client → 9Router:** authenticated by the 9Router API key (standard).
2. **9Router → proxy:** loopback HTTP, Bearer = the FreeBuff token. Traffic never
   leaves the host unencrypted (loopback).
3. **Proxy → Codebuff:** TLS; the proxy mimics the official CLI's egress signature
   (this is the ToS-gray part — see "Risks you accept").

## Secrets handling rules (this repo)

- No token, key, or password is ever committed. `.gitignore` excludes
  `.deploy-secrets*`, `.env`, `*.db`, backups.
- `install.sh` generates the admin token with `openssl rand -hex 24` and prints it
  once; re-runs never overwrite an existing env file.
- `freebuff9r.py` never prints tokens; `status` shows only `token ✓ / PLACEHOLDER`.
- DB backups created by the tooling get `chmod 600`.

## Hardening checklist

- [x] proxy loopback-only bind (default in env template + service)
- [x] dedicated non-login system user for the proxy
- [x] systemd sandbox: `ProtectSystem=strict`, `ProtectHome=true`,
      `NoNewPrivileges=true`, `ReadWritePaths` limited to its state dir
- [x] admin token generated at install (never the upstream default `123456`)
- [x] env file 0640 root:freebucks-proxy
- [ ] change 9Router's dashboard/admin access policy per your host (out of scope here)
- [ ] if you expose 9Router beyond localhost: front it with TLS + auth or a VPN
      (Tailscale/WireGuard)

## Risks you accept (be honest with yourself)

1. **ToS violation / account bans.** freebucks-proxy's own generator prints:
   *"Using FreeBuff tokens through a proxy violates FreeBuff/Codebuff terms of
   service. Accounts may be suspended or banned."* Treat FreeBuff accounts as
   disposable. Don't attach an account whose loss hurts you (e.g. one tied to
   paid Codebuff history).
2. **Prompt/code disclosure.** Everything you send goes to Codebuff's servers —
   identical to using their official CLI. Never route proprietary code, secrets,
   or client data through free upstreams.
3. **Evasion posture.** The proxy's anti-ban features (TLS/UA parity, jitter,
   isolated fingerprints per account) are detection-evasion measures. Depending on
   your jurisdiction and the operator's stance this is against the letter of the
   ToS even when technically permitted. This repo ships SAFE_MODE defaults and
   does not add further evasion beyond the upstream's own.
4. **Supply chain.** `install.sh` builds from the **pinned** upstream tag
   (`FREEBUFF_UPSTREAM_TAG`) over HTTPS from GitHub. Verify before running:
   `git -C /tmp/freebucks-proxy-build log -1` should match the tag you expect.

## Incident response

- Suspected token leak → rotate immediately: re-login each account
  (`login-url` + `wait-login --replace`) or `remove` + re-register.
- Proxy misbehaving → `systemctl stop freebucks-proxy`; everything degrades to
  "models unavailable" in 9Router, no data loss.
- Full teardown → `python3 freebuff9r.py remove` + `systemctl disable --now
  freebucks-proxy` (+ delete `/usr/local/bin/freebucks-proxy`,
  `/etc/freebucks-proxy/`, the system user).
