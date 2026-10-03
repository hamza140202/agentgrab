# SKILLS.md — Agent Skills for AgentGrab

> Drop-in knowledge for AI agents (Claude Code skills, CLI copilots, autonomous pipelines). Each skill is a self-contained recipe: when to use it, the exact commands, and how to interpret results. A copy-paste-ready skill package lives at `skills/agentgrab/SKILL.md`.

---

## Skill 1 — `agentgrab:download` (core competency)

**When to use:** the user (or your pipeline) asks to fetch a YouTube or Instagram video/reel/post as a file, from a cloud machine, without logins.

**Recipe:**
```bash
# 1. Sanity (once per session): environment + services
agrab doctor --json
# ok:false? Fix what doctor names (pot server down → agrab pot start; node missing → install Node ≥22).

# 2. Download
agrab download "https://www.youtube.com/watch?v=VIDEO_ID" --quality 720 --json
agrab download "https://www.instagram.com/reel/SHORTCODE/" --json

# 3. Act on the result
#    ok:true  → file path is in .file, metadata in .title/.duration/.size
#    ok:false → read .attempts[] (full diagnostic history), retry once,
#               then surface the attempts array verbatim to the user.
```

**Audio-only:** append `--audio` (mp3/m4a via `--quality mp3|m4a`).
**Batch:** pass multiple URLs; output is a JSON array; exit code 0 only if all succeed.

**Anti-patterns:** don't parse human logs when `--json` exists; don't retry more than twice without checking `agrab methods --json` health; don't treat a cobalt `.jpg` as a video (the verifier already rejects it — don't disable verification).

---

## Skill 2 — `agentgrab:health` (self-diagnosis)

**When to use:** downloads are failing and you need to know *why* before acting.

**Recipe:**
```bash
agrab methods --json     # ranked health: success rates, quarantine flags
agrab truth --json       # raw telemetry store
agrab doctor --json      # environment: yt-dlp/node/ffmpeg, POT ping, egress
```

**Interpretation:**
- One method degraded, others fine → platform-side flakiness; the chain already compensates; retry.
- All methods failing + doctor's egress checks red → network partition; stop, report.
- `loaderto` success rate sagging while `ytdlp_pot` rises → the flag window opened; nothing to do, ranking adapts automatically.
- Quarantined method you *know* recovered (e.g. after network fix) → `agrab truth reset` and let it re-prove itself.

---

## Skill 3 — `agentgrab:pot-ops` (YouTube fast-path operations)

**When to use:** `ytdlp_pot` matters to you (best quality/resolution) and you want the POT server explicitly managed.

**Recipe:**
```bash
agrab pot status --json         # is bgutil healthy on :4416?
agrab pot start                 # clone+build+launch if missing (idempotent)
# Manual deep setup (matches pot-server/setup.sh):
#   git clone --single-branch --branch 2.0.1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git
#   cd bgutil-ytdlp-pot-provider/server && npm ci && npx tsc
#   node build/main.js          # binds 127.0.0.1:4416
```

**Facts:** POT tokens do NOT guarantee bypass — on hard-flagged IPs the gate can fire before token checks. That's why `loaderto` exists as tier 2. Never block a user request on POT server repair; the chain works without it.

---

## Skill 4 — `agentgrab:extend` (add a platform/method)

**When to use:** the roadmap calls for a new platform (TikTok/Reddit/X/Douyin/RedNote) or a new method for an existing one.

**Recipe:**
1. **Truth first.** Live-test the candidate approach on the target machine. Write the evidence file `docs/research/<platform>_<method>.md` (what you tried, exact commands, verdicts). Dead ends are deliverables.
2. Implement `agentgrab/methods/<platform>_<name>.py` extending `DownloadMethod` (contract: `name`, `platforms`, `default_timeout`, `download(req) -> MethodResult`, raise `MethodError` with one-line root cause).
3. Register in `methods/__init__.py`; add platform detection in `orchestrator.py`; add a canonical test vector.
4. Update `docs/plan.md` §7 matrix + `docs/claude.md` §2 truth table **in the same commit**.
5. Prove it: `agrab download <url> --method <name> --json` then `agrab test --json`; append evidence to `docs/phases.md`.

---

## Skill 5 — `agentgrab:truth-keeping` (documentation discipline)

**When to use:** continuously — after every discovery, outage, or recovery.

**Rules:**
- `docs/claude.md` §2 is the canonical truth table. Live telemetry (`truth.json`) and documented truth must never diverge.
- One discovery = one commit touching: claude.md §2 (+ worklog if multi-agent session).
- Report pass *rates*, not booleans: "tv client 1/12 today" is truth; "tv client broken" is vibes.
- Never delete evidence in `docs/phases.md`; append.

---

## Installation as an Agent Skill

Claude-style runtimes: copy `skills/agentgrab/` into your skills directory (e.g. `~/.claude/skills/`). The SKILL.md front-matter declares the trigger description; the body embeds Skill 1–3 above so the agent can operate AgentGrab without reading this file.
