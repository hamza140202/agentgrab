# TECHSTACK.md — AgentGrab Technology Stack & Rationale

> Every component here survived live testing against the actual enemy: a hard-flagged datacenter IP with no cookies. Components that failed are listed too — negative knowledge prevents regression.

---

## 1. Runtime Core

### Python 3.12+
**Role:** primary language for the engine, CLI, methods, verifier, truth store.
**Why chosen:** the entire yt-dlp/instaloader ecosystem is Python; stdlib covers HTTP, JSON, process control, concurrency; dataclasses give clean typed models for agent-facing JSON output. No framework needed — a downloader is orchestration + subprocess discipline, not a web app.

### Node.js ≥ 22 (Node 24 in production build)
**Role:** (a) JS runtime for yt-dlp's External-JS challenge solving (`--js-runtimes node`); (b) host for the bgutil BotGuard POT generation server.
**Why chosen:** since 2025.05.22 yt-dlp deprecates YouTube extraction without a JS runtime, and since late 2025 the EJS challenge system is effectively required for sane extraction on flagged IPs. BotGuard (Google's proof-of-origin) only runs in a real JS VM. Node 22+ is the engine's hard floor.

### ffmpeg 7.x
**Role:** verification oracle (ffprobe) for every downloaded file: container, codecs, duration, stream presence.
**Why chosen:** it is the industry reference for media introspection; it catches every failure mode we care about (HTML-as-MP4, thumbnail-as-video, truncated downloads) in one subprocess call. Also does post-processing (audio extraction, remux) when requested.

### git + GitHub
**Role:** version control, backup, distribution (user: `hamza140202`).
**Why chosen:** the user mandated repo-backed delivery; everything (docs, code, research evidence) is in one repo so any agent can rebuild the system from scratch.

---

## 2. Download Methods (the heart)

### Tier structure per platform

| Tier | YouTube | Instagram |
|---|---|---|
| 1 (fast native) | `ytdlp_pot`: yt-dlp + Node EJS + bgutil POT, clients `tv,visionos,web_safari` | `ig_graphql`: web GraphQL `doc_id=27128499623469141`, anonymous `csrftoken`, `x-ig-app-id: 936619743392459` |
| 2 (workhorse) | `loaderto`: loader.to AJAX resolver API (keyless) | `ig_instaloader`: instaloader single-post anonymous |
| 3 (resilient) | repeat tier 1 (flag windows open/close) | `ig_cobalt`: public cobalt instance (verifier rejects `.jpg` degrade) |
| 4 (last resort) | — | `ytdlp_instagram`: yt-dlp extractor (works only on clean IPs) |

Ordering is **adaptive**: the truth agent re-ranks by live success telemetry, so the table above is the *initial* policy, not a hardcoded destiny.

### yt-dlp 2026.08+ (`pip install yt-dlp`)
**Why kept despite the bot wall:** it is still the best *local* extractor (metadata, formats, muxing, subtitles) and on flag windows / residential IPs it just works. The `ytdlp_pot` method wraps it with the full 2026 stack:

```
yt-dlp --js-runtimes node \
  --extractor-args "youtube:player_client=tv,visionos,web_safari" \
  --socket-timeout 25 --retries 2 --no-playlist \
  -f "bv*[height<=Q]+ba/b[height<=Q]/b"
```

**Player-client intel (verified 2026-10):**
- `tv` — the only client that passed during the original build's flag window (1/12). Non-deterministic gating; retry has real yield.
- `visionos` — no PO-token requirement, no byte cap; best first pick in rotations.
- `android`/`ios` — byte-capped (~1 min) then 403 since 2026-08-17. Never trust for full files.
- `mweb`, `web_safari`, `web_embedded`, `tv_embedded`, `android_vr`, `android_music` — blocked on flagged IPs.

### bgutil-ytdlp-pot-provider 2.0.1 (pip plugin + Node server)
**Role:** generates Google **proof-of-origin tokens** by running BotGuard in a local Node VM; the yt-dlp plugin attaches them to player/GVS requests.
**Why chosen:** it is the reference open implementation of the only native bypass for "Sign in to confirm you're not a bot". Setup: clone `Brainicism/bgutil-ytdlp-pot-provider` tag `2.0.1` → `cd server && npm ci && npx tsc` → `node build/main.js` (port 4416). AgentGrab manages this lifecycle (`agrab pot start|status`) and health-checks `GET /ping` before relying on it.
**Honest limit:** on hard-flagged IPs the playability gate can fire *before* token checks — that's why POT is tier 1 (fast when it hits) but the chain has a workhorse tier 2.

### loader.to AJAX API (keyless resolver — YouTube workhorse)
**Protocol (verified end-to-end):**
1. `GET https://loader.to/ajax/download.php?format={360|480|720|1080|1440|mp3|m4a}&url={encoded}` → `{"success":true,"id":…,"progress_url":…}`
2. Poll `progress_url` every 2.5 s (≤90 s budget) until `progress==1000` → `download_url`
3. GET `download_url` (CDN, different domain — always use the returned URL) → MP4/M4A
**Why chosen:** their clean-IP server farm does the YouTube handshake; our flagged IP only ever talks to loader.to and their CDN. Zero auth, zero infra, verified byte-perfect output. Ethics guardrails built in: 2.5 s poll interval, 1 req/s ceiling, per-request budget.
**Escape hatch:** the paid twin `video-download-api.com` speaks the same protocol with an API key — documented in `plan.md` §7 for environments that need an SLA.

### instaloader 4.15+ (`pip install instaloader`)
**Role:** Instagram single-post/reel anonymous downloads (MP4 + metadata JSON + poster).
**Why chosen:** the only tool that *verified* anonymous single-post access from a flagged datacenter IP. Profile/hashtag enumeration is dead anonymously (429/401 walls) — AgentGrab therefore scopes it to single posts only.
**Gotcha:** it logs 401 "wait a few minutes" warnings and still succeeds; AgentGrab judges by produced files, not log noise.

### Instagram web GraphQL (hand-rolled, no dependency)
**Protocol:** GET `instagram.com/` with a browser UA to mint an anonymous `csrftoken` → POST `/graphql/query` with `x-csrftoken`, `x-ig-app-id: 936619743392459`, form fields `variables={"shortcode":…,"__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider":false}` and `doc_id=27128499623469141` → parse `data.xdt_api__v1__media__shortcode__web_info.items[0].video_versions[]`.
**Why kept despite flakiness:** when it works it's the fastest IG path (one POST, direct CDN URLs, no subprocess). The relay flag omission yields silent empty `items` — baked into the code and commented.
**Truth:** flaky from flagged IPs (execution errors ~3/3 in original build; verified by parallel research run) → tier 1 with 2 retries and jitter, demoted automatically by truth data if it degrades.

### Cobalt (public instance fallback for IG)
**Role:** `POST https://co.otomir23.me/ {"url":…}` → `tunnel` URL.
**Why included:** independent code path (different service family). **Critical caveat:** may return a `.jpg` thumbnail for posts it can't resolve as video — the verifier rejects these, the orchestrator moves on. Public cobalt requires JWT on official instances; only community instances without auth are usable.

---

## 3. Rejected / Dead Technologies (do not resurrect without new evidence)

| Technology | Death certificate |
|---|---|
| Public Invidious instances | 10/10 dead or 403 from datacenter IPs (2026-10 sweep; list in `docs/research/youtube_methods.md`) |
| Public Piped instances | 8/8 dead/403/500 |
| Official Cobalt API | `error.api.auth.jwt.missing` — API keys now mandatory |
| ddownr / p.oceansaver.in | empty responses |
| mp3youtube.cc | "Bad request" on sanity endpoint |
| yt-dlp bare client rotation | all clients LOGIN_REQUIRED on flagged IPs without POT+JS runtime |
| Android/iOS clients for full files | byte-cap ~1 min then 403 (2026-08-17) |
| `api.instagram.com` oEmbed without token, `/api/v1/media/{id}/info/` web headers, anonymous profile enumeration, gallery-dl anonymous, fastdl/igram backends | login walls / moved routes (details in `docs/research/instagram_methods.md`) |

## 4. Deployment Matrix

| Environment | Recipe |
|---|---|
| This sandbox / generic VPS | `pip install -e .` + Node 22+ + ffmpeg + POT server → full chain works (verified) |
| Docker | `python:3.12` base + node:22 + ffmpeg; POT server as second container, `agrab pot status` health-checked |
| Hard-flagged IP, SLA needed | WARP sidecar (`caomingjun/warp`, socks5 :1080) as `ytdlp_pot` proxy tier, and/or `video-download-api.com` key as paid `loaderto` twin |
| Residential IP | native `ytdlp_pot` becomes primary automatically (truth data re-ranks within a few runs) |

## 5. Dependency Pinning

`requirements.txt` (runtime): `yt-dlp>=2026.8.1`, `instaloader>=4.14`, `bgutil-ytdlp-pot-provider>=2.0.1`
System: `python>=3.10`, `node>=22`, `ffmpeg>=6` (7 recommended), `git`.
AgentGrab's own code has **zero** runtime deps beyond these — stdlib HTTP/JSON/subprocess only, so supply-chain risk stays minimal and the tool installs on locked-down hosts.
