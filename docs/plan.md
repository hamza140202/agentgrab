# PLAN.md — AgentGrab System Design & Extension Plan

> The engineering blueprint: module map, data contracts, fallback semantics, CLI spec, and the roadmap for adding platforms (TikTok, Reddit, X, Douyin, RedNote).

---

## 1. Module Map

```
agentgrab/
├── __init__.py            version, public exports
├── __main__.py            python -m agentgrab → cli.main()
├── cli.py                 argparse surface; stdout=JSON, stderr=logs
├── config.py              paths, defaults, env overrides (AGENTGRAB_*)
├── models.py              DownloadRequest / MethodResult / DownloadResult (dataclasses → JSON)
├── orchestrator.py        platform detect → rank → chain → verify → truth → result
├── verifier.py            ffprobe oracle: container/codecs/duration/image-rejection
├── truth.py               JSON health store, adaptive ranking, quarantine, file lock
├── errors.py              MethodError, VerificationError, PlatformNotFound
├── utils.py               run(), http_get(), atomic_write(), UA constants, logging
└── methods/
    ├── base.py            DownloadMethod ABC (the contract)
    ├── __init__.py        ALL_METHODS registry + platform→methods mapping
    ├── ytdlp_pot.py       [youtube] yt-dlp + node EJS + bgutil POT (tv,visionos,web_safari)
    ├── loaderto.py        [youtube] loader.to AJAX submit/poll/download (throttled)
    ├── ig_graphql.py      [instagram] anon-csrftoken GraphQL doc_id query
    ├── ig_instaloader.py  [instagram] instaloader single-post anonymous
    ├── ig_cobalt.py       [instagram] public cobalt instance + image-result rejection
    └── ytdlp_instagram.py [instagram] yt-dlp extractor (clean-IP fallback)
```

Support assets:
- `pot-server/` — setup script + README for bgutil server lifecycle (`agrab pot start|status` wraps it).
- `tests/test_e2e.py` — live E2E suite (`agrab test` is the CLI façade).
- `skills/agentgrab/SKILL.md` — drop-in skill for Claude-style agent runtimes.
- `docs/research/` — the 5 evidence reports backing every design decision.

## 2. Data Contracts

### DownloadRequest (input)
```python
@dataclass
class DownloadRequest:
    url: str                    # single media URL (post/reel/watch)
    mode: str = "video"         # "video" | "audio"
    quality: int | None = None  # max height (video) / preset (audio: mp3|m4a)
    output_dir: Path = ~/Downloads
    filename: str | None = None # optional stem; extension resolved by method
    method: str | None = None   # force one method (skips chain)
    timeout: int | None = None  # override per-method timeout (seconds)
    verify: bool = True         # run ffprobe verification
```

### MethodResult (method → orchestrator)
```python
@dataclass
class MethodResult:
    file: Path; title: str; duration: float | None; size: int
    meta: dict                  # method-specific extras (uploader, format_id, …)
```
Failure = raise `MethodError("one-line root cause")`. Methods must never return None and never swallow exceptions.

### DownloadResult (orchestrator → agent)
```json
{
  "ok": true,
  "url": "…", "platform": "youtube",
  "file": "/abs/path.mp4", "title": "…", "duration": 19.13, "size": 639340,
  "method": "loaderto",
  "verified": {"container": "mp4", "video_codec": "h264", "audio_codec": "aac", "duration": 19.13},
  "attempts": [
    {"method": "ytdlp_pot", "ok": false, "error": "Sign in to confirm you're not a bot", "ms": 8214},
    {"method": "loaderto",  "ok": true, "ms": 31170}
  ]
}
```
On total failure: `"ok": false` + the complete `attempts` array + `"error"` = last root cause. **Agents get the full diagnostic history, always.**

## 3. Fallback Chain Semantics

1. **Detect platform** from URL host/path (youtube.com, youtu.be, m.youtube.com, shorts → `youtube`; instagram.com → `instagram`).
2. **Rank candidates**: truth-store ranking = consecutive failures (asc) → success rate (desc) → avg latency (asc). Quarantined methods (≥5 consecutive failures) go last but are never dropped.
3. **Forced method** (`--method`) short-circuits ranking (still verified, still recorded).
4. **Per-method budget:** `min(req.timeout or method.default_timeout, config.max_method_timeout)`. A method that hangs fails and the chain moves on.
5. **YouTube chain rounds:** tier-1 (`ytdlp_pot`) → tier-2 (`loaderto`) → tier-1 retry (flag windows open non-deterministically — measured 1/12; one extra round is cheap and gives real yield).
6. **Instagram chain:** `ig_graphql` (2 in-method retries with fresh cookie jar) → `ig_instaloader` → `ig_cobalt` (image results rejected by verifier → counts as method failure) → `ytdlp_instagram`.
7. **Verification gate:** only a verifier-passing file counts as success; verification failure = method failure (truth records it).
8. **Recording:** every attempt (method, ok, error, ms) is appended to the truth store before the next attempt starts — a crash mid-chain never loses telemetry.

## 4. Truth Store Schema (`~/.agentgrab/truth.json`)
```json
{
  "loaderto": {
    "attempts": 15, "successes": 14, "failures": 1,
    "consecutive_failures": 0, "avg_ms": 32450,
    "last_ok": "2026-10-03T15:02:11Z", "last_error": null,
    "quarantined": false
  }
}
```
`agrab truth` renders it; `agrab methods` merges it with the registry; `agrab truth reset` recreates the file (explicit human action only).

## 5. CLI Specification

```
agrab download <urls…> [--audio] [--quality Q] [-o DIR] [--method NAME]
                       [--timeout SEC] [--no-verify] [--json]
agrab methods [--json]     registry × truth, ranked, quarantine flags
agrab truth [--json] | truth reset
agrab test [--quick] [--json]    canonical E2E vectors (YouTube + Instagram; --quick = YouTube only)
agrab doctor [--json]            yt-dlp/node/ffmpeg versions, POT ping, egress checks, instaloader import
agrab pot start|status [--json]  bgutil server lifecycle (clone→build→run if missing)
```
Exit codes: `0` success · `1` download failed (attempts array in JSON) · `2` usage/environment error. Batch mode prints a JSON array; exit 0 only if all succeeded.

## 6. Quality & Mode Mapping

| Request | ytdlp_pot | loaderto | IG methods |
|---|---|---|---|
| video 360/480/720/1080/1440 | `-f "bv*[height<=Q]+ba/b[height<=Q]/b"` | `format=Q` | best available (IG caps at source quality) |
| video max | `b` | `format=1080` | best available |
| audio (mp3/m4a) | `-f ba -x --audio-format F` | `format=F` | instaloader: source audio track; cobalt: `audioFormat` |

## 7. Extension Plan (roadmap platforms)

Adding a platform = (a) 2+ methods implementing the contract, (b) platform detection rule, (c) canonical test vector, (d) truth-table row in claude.md §2, (e) `docs/research/` evidence file. Targets from the product roadmap:

| Platform | Planned method 1 (research-first) | Planned method 2 |
|---|---|---|
| TikTok | tikwm.com resolver API (keyless, server-side fetch) | cobalt (public instance) |
| Reddit | public `.json` media endpoints + yt-dlp (hosted media) | cobalt |
| X/Twitter | syndication `cdn.syndication.twimg.com` tweet-result API | cobalt / fxtwitter-style resolvers |
| Douyin | web share-page parse (ttwid cookie dance) | third-party resolver APIs |
| RedNote (XHS) | web share-page sniaml parse | resolver APIs |

No platform ships until its methods pass the Phase-1 truth discipline (live evidence, dead ends documented).

## 8. Non-Goals

- No cookie/login management in the default path (mission: cookieless; escape hatches stay explicit and non-default).
- No queue daemon / web UI — AgentGrab is a CLI/library for agents; orchestration belongs to the calling agent.
- No DRM circumvention — public media only.

## 9. Risk Register

| Risk | Mitigation |
|---|---|
| loader.to shuts down / rate-limits hard | paid twin video-download-api.com (same protocol); WARP/cobalt tiers documented; truth data exposes degradation immediately |
| YouTube changes POT/challenge system | bgutil repo is actively maintained; `agrab doctor` fails loudly; local `ytdlp_pot` and `loaderto` are independent code paths |
| IG GraphQL doc_id deprecation | instaloader is independent; doc_id constants live in ONE place (`ig_graphql.py`) for fast patching |
| Sandbox kills long-running POT server | `agrab pot start` is idempotent; `doctor` health-checks; `loaderto` needs no local server |
| Platform adds aggressive per-IP rate limits | jittered retries, throttle constants centralized in `config.py`, batch mode spaces requests |
