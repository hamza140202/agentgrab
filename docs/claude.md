# CLAUDE.md — AgentGrab Operating Memory

> **Read this file first. Every session. No exceptions.**
> This is the single source of truth for what works, what is dead, and how this codebase is wired. If you change behavior that contradicts this file, update this file in the same commit.

---

## 1. Mission

AgentGrab is **yt-dlp for AI agents** — a production downloader that reliably fetches YouTube and Instagram media **from cloud/datacenter servers, without cookies, without login sessions**.

It exists because vanilla yt-dlp fails in the exact environment agents run in: datacenter IPs are hard-flagged by YouTube (`Sign in to confirm you're not a bot`) and Instagram (login-gated media endpoints). AgentGrab wraps multiple download methods in a **self-healing fallback chain**, ranks them by live success telemetry ("truth data"), validates every output file, and returns machine-readable JSON that an agent or CLI can consume without human help.

Design axiom: **"One source of truth — this is possible."** It was proven during the original build (see `docs/phases.md` for the evidence trail).

---

## 2. Verified Truth Table (2026-10, measured from a real datacenter IP)

This table is the most valuable asset in the repo. Every entry was **live-tested**, not assumed.

### YouTube

| Method | Verdict | Evidence |
|---|---|---|
| `loaderto` — loader.to AJAX API (keyless) | ✅ **PRIMARY — works** | Full MP4 downloaded & ffprobe-verified (h264+aac, correct duration) |
| `ytdlp_pot` — yt-dlp + Node JS runtime + bgutil POT server, clients `tv,visionos,web_safari` | ⚠️ **FLAKY fast-path** (≈1/12 on hard-flagged IP; non-deterministic) | Works sometimes; keep as tier-1 with app-level retries |
| Public Invidious (10 instances) | ❌ dead | 403 / timeout / BAD-JSON on all |
| Public Piped (8 instances) | ❌ dead | 403 / 500 / timeout on all |
| Public Cobalt (api.cobalt.tools, canine.tools) | ❌ dead | `error.api.auth.jwt.missing` |
| ddownr / p.oceansaver.in, mp3youtube.cc | ❌ dead | empty response / bad request |
| `android`/`ios` player clients | ❌ byte-capped | ~1-minute cap then 403 (2026-08-17 change) |
| `visionos` client | 🟡 best native client | no POT requirement, no byte cap — keep first in rotation |
| Self-hosted Cobalt + yt-session-generator | 🟡 documented tier | needs a clean egress IP to be useful |
| WARP sidecar (`caomingjun/warp`) + `--proxy socks5://127.0.0.1:1080` | 🟡 documented tier | attacks root cause (IP reputation) |

### Instagram

| Method | Verdict | Evidence |
|---|---|---|
| `ig_instaloader` — instaloader single-post anonymous | ✅ **PRIMARY — works** | MP4 (h264+aac, 13.5 s, 3.2 MB) + JPG + JSON downloaded anonymously |
| `ig_graphql` — web GraphQL `doc_id=27128499623469141` with anonymous `csrftoken` + `x-ig-app-id: 936619743392459` | ⚠️ **FLAKY secondary** | Verified by research run; `execution error` on repeated runs from this IP — needs fresh cookie jar per burst + 2 retries |
| `ig_cobalt` — public instance `co.otomir23.me` | 🟡 last resort | tunnel works but may return `.jpg` thumbnail — verifier MUST reject images |
| `ytdlp_instagram` — yt-dlp IG extractor | ❌ on datacenter IPs | `/api/v1/media/{id}/info/` → 302 login; GraphQL → HTML wall. Works only on clean/residential IPs |
| Anonymous profile/hashtag enumeration | ❌ dead | 401 `require_login` / 429 with 666 s retry |
| gallery-dl anonymous | ❌ dead | official docs confirm login required since mid-2023 |

**Rule of thumb baked into the code:** the reason these methods work is that *someone else's clean IP does the platform handshake* (loader.to's farm, instaloader's web-session emulation) or *the request looks like a legitimate web client* (POT tokens + JS-challenge solving). Native player-client rotation alone is dead on flagged IPs.

---

## 3. Architecture Map

```
CLI (agrab) ──► Orchestrator ──► Method Registry (truth-ranked)
                     │                  │
                     │                 methods/ (pluggable, one file per method)
                     │
                     ├──► Downloader retry loop (per-method timeout, app-level retries)
                     ├──► Verifier (ffprobe: container, codecs, duration; rejects images-as-video)
                     └──► Truth agent (JSON health store, adaptive ranking, quarantine)
```

- `agentgrab/orchestrator.py` — pipeline: detect platform → rank methods → attempt chain → verify → record truth → return `DownloadResult`.
- `agentgrab/methods/base.py` — the method contract. **One method = one class** in one file, registered in `methods/__init__.py`.
- `agentgrab/verifier.py` — ffprobe-based validation. Never trust a 200 response; verify bytes.
- `agentgrab/truth.py` — persistent JSON health store (`~/.agentgrab/truth.json`), adaptive ranking, quarantine after 5 consecutive failures.
- `agentgrab/cli.py` — agent-facing surface: `download | methods | truth | test | doctor | pot`.

Every command supports `--json` — agents should never scrape human output.

---

## 4. Critical Runtime Facts

1. **yt-dlp ≥ 2025.05.22 requires a JS runtime** for YouTube challenge solving. Pass `--js-runtimes node`. Node ≥ 22 must be on PATH. Without it, extraction quality degrades and bot-detection odds rise.
2. **bgutil POT server must be running** on `127.0.0.1:4416` for the `ytdlp_pot` method. Check with `agrab doctor` / `agrab pot status`; start with `agrab pot start`. Setup: clone `Brainicism/bgutil-ytdlp-pot-provider` at tag `2.0.1`, `cd server && npm ci && npx tsc`, run `node build/main.js`.
3. **POT plugin** comes from `pip install bgutil-ytdlp-pot-provider` (auto-loaded by yt-dlp).
4. **loader.to is rate-unspecified** — treat it as a courtesy API: throttle (built-in 2.5 s poll, 1 req/s max), cache results, never hammer it. If it starts failing globally, the paid twin is `video-download-api.com` (same protocol, API key).
5. **Instagram GraphQL needs an anonymous `csrftoken`** — GET `https://www.instagram.com/` with a browser UA first, then send the cookie + `x-csrftoken` + `x-ig-app-id: 936619743392459`. Include the relay provider flag in `variables` or `items` comes back empty.
6. **Verifier rejects images masquerading as downloads** (cobalt `.jpg` degrade, poster-only responses). Any file without a real audio/video stream fails.
7. **Timeouts are per-method and enforced** — a method that hangs never blocks the chain.

---

## 5. Conventions

- Python 3.12+, stdlib-first. External deps: `yt-dlp`, `instaloader`, `bgutil-ytdlp-pot-provider` only. No heavyweight frameworks.
- Every method class sets `name`, `platforms`, `default_timeout`, and raises `MethodError` (never returns `None` on failure).
- Structured logging goes to stderr in `[agentgrab] level: message` form; **stdout is reserved for JSON** when `--json` is passed.
- No global mutable state outside `truth.py` (which owns the health store file lock).
- Tests: `agrab test` (E2E, hits real platforms) and `tests/test_e2e.py`. CI-friendly: `--quick` skips the slowest platform.
- Commit style: `area: change` (e.g. `methods: add IG graphql retry jitter`). Update `docs/phases.md` status markers when completing a phase.

## 6. How to Add a Method (the 6-step ritual)

1. Create `agentgrab/methods/my_method.py` with a class extending `DownloadMethod`.
2. Implement `download(req) -> MethodResult`; raise `MethodError` with a **one-line root cause** on failure.
3. Register it in `agentgrab/methods/__init__.py` (`ALL_METHODS` list).
4. Add it to `docs/plan.md` method matrix with platform + priority.
5. Test it standalone: `agrab download <url> --method my_method --json`.
6. Run `agrab test --json` and append the result line to `docs/phases.md` evidence.

## 7. Known Gotchas (learned the hard way)

- The POT server failing with `EADDRINUSE` usually means **one is already running** — health-check before starting.
- `instaloader` emits 401 "wait a few minutes" warnings then still succeeds — don't treat warnings as failures; judge by output files.
- loader.to `progress_url` may point at a different domain than the submit host — always use the returned URL.
- On some sandboxes port 4416 is pre-occupied by a healthy POT server — reuse it, don't fight it.
- ffprobe on files whose names start with `-` needs `--` or absolute paths.
- Never parse yt-dlp progress output for success; exit code + verified file are the only truth.

## 8. Where the Evidence Lives

- `docs/research/*.md` — full research reports (1,500+ lines: instance sweeps, API autopsies, bypass genealogy).
- `docs/phases.md` — phase-by-phase build log with pass/fail evidence.
- `agrab truth --json` — live, current health of every method on this machine.
