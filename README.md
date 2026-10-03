<div align="center">

# AgentGrab

**yt-dlp for AI agents** — cookieless YouTube & Instagram downloads that actually work on cloud/datacenter servers.

Self-healing fallback chains · truth-data method ranking · ffprobe-verified output · machine-readable JSON.

`Python 3.10+` · `Node ≥ 22` · `ffmpeg ≥ 6` · `yt-dlp ≥ 2026.8`

</div>

---

## Why this exists

Vanilla yt-dlp is broken in exactly the environment AI agents run in: datacenter IPs. YouTube answers every player client with `Sign in to confirm you're not a bot`; Instagram login-gates every media endpoint. AgentGrab was built after a **measured truth phase**: every method below was live-tested from a real flagged datacenter IP, and only survivors entered the chain.

| | YouTube | Instagram |
|---|---|---|
| ✅ **Verified working** | loader.to resolver API (keyless), yt-dlp+POT in flag windows | instaloader (anonymous), web GraphQL (flaky-fast) |
| ⚠️ **Flaky / conditional** | `tv`/`visionos` clients (~1/12 on hard-flagged IPs) | public cobalt (rejects `.jpg` degrade) |
| ❌ **Measured dead** | public Invidious ×10, public Piped ×8, official Cobalt (JWT), ddownr, mp3youtube, bare client rotation | yt-dlp IG extractor on datacenter IPs, anonymous profile enumeration, gallery-dl anonymous |

Full evidence: [`docs/claude.md` §2](docs/claude.md) · [`docs/research/`](docs/research/) (1,500+ lines of primary research).

## Quickstart

```bash
pip install -e .          # + system deps: node ≥22, ffmpeg, git
agrab doctor --json       # environment sanity
agrab pot start           # bgutil proof-of-origin server (optional but recommended)
agrab download "https://www.youtube.com/watch?v=jNQXAC9IVRw" --json
agrab download "https://www.instagram.com/p/-CDUMkliABpa/" --json
```

## Agent surface

```bash
agrab download <urls…> [--audio] [--quality 720|max|mp3] [-o DIR] [--method NAME] [--timeout SEC] [--json]
agrab methods [--json]   # registry × live health, truth-ranked
agrab truth [--json]     # the telemetry store
agrab test [--quick] [--json]   # real E2E: canonical YouTube + Instagram vectors
agrab doctor [--json]
agrab pot start|status [--json]
```

Every download returns (with `--json`) the full diagnostic history:

```json
{
  "ok": true, "platform": "youtube", "method": "loaderto",
  "file": "/root/Downloads/me_at_the_zoo.mp4", "duration": 19.13,
  "verified": {"container": "mp4", "video_codec": "h264", "audio_codec": "aac"},
  "attempts": [
    {"method": "ytdlp_pot", "ok": false, "error": "bot_check: Sign in to confirm…", "ms": 8214},
    {"method": "loaderto", "ok": true, "ms": 31170}
  ]
}
```

## How the chain works

1. **Detect platform** → 2. **Rank methods by truth data** (consecutive failures → success rate → latency; 5+ consecutive failures = quarantine, never removal) → 3. **Run the chain** with hard per-method timeouts → 4. **Verify every file** with ffprobe (rejects error pages, images-as-video, sub-second stubs) → 5. **Record telemetry** before the next attempt → 6. **Return JSON** with the complete attempt log.

YouTube: `ytdlp_pot` → `loaderto` → `ytdlp_pot` retry. Instagram: `ig_graphql` → `ig_instaloader` → `ig_cobalt` → `ytdlp_instagram`. Ordering adapts to reality — on a residential IP, native yt-dlp re-ranks to first automatically.

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/claude.md`](docs/claude.md) | operating memory: verified truth table, gotchas, conventions |
| [`docs/agents.md`](docs/agents.md) | multi-agent roles, handoff protocol, escalation ladder |
| [`docs/techstack.md`](docs/techstack.md) | every technology, why it's in, and death certificates for what's out |
| [`docs/plan.md`](docs/plan.md) | architecture, data contracts, extension roadmap (TikTok, Reddit, X, Douyin, RedNote) |
| [`docs/phases.md`](docs/phases.md) | phase-by-phase build log with measured evidence |
| [`docs/skills.md`](docs/skills.md) | agent skills (download / health / pot-ops / extend / truth-keeping) |

## Adding a platform

Truth first: live-test candidate methods, write `docs/research/<platform>.md`, then implement one class per method (`agentgrab/methods/<platform>_<name>.py`), register it, add a canonical test vector, update the truth table in the same commit. Full ritual: [`docs/claude.md` §6](docs/claude.md).

## Status

Phase 0–4 complete (build + unit-verified). Phase 5 E2E evidence and Phase 6 publication: see [`docs/phases.md`](docs/phases.md).

## License

MIT
