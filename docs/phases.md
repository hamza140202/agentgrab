# PHASES.md — Build Phases, Acceptance Criteria & Evidence

> Build log of the original AgentGrab construction (2026-10-03) plus the standing process for future phases. Each phase lists its acceptance criteria and the **actual measured evidence** from this build. This file is append-only: new phases go to the bottom, completed markers get updated, evidence is never deleted.

---

## Phase 0 — Workspace & Identity ✅

**Goal:** verify environment, credentials, toolchain.
**Acceptance criteria:** GitHub token valid; Python/Node/ffmpeg/yt-dlp present; egress to target platforms confirmed.
**Evidence (measured):**
- `GET api.github.com/user` → login `hamza140202`, id `216095148` ✅
- Python 3.12.14, Node v24.21.0, ffmpeg 7.1.5, git 2.47.3, yt-dlp 2026.08.19 ✅
- youtube.com → 200 (0.28 s), instagram.com → 200 (0.77 s) ✅
- Finding: sandbox venv already ships an unrelated `agentdl` package → project named **agentgrab** (CLI `agrab`) to avoid collision ✅

## Phase 1 — Deep Research (Truth Phase) ✅

**Goal:** establish, by live experiment + web research, which methods actually work cookieless from a datacenter IP. No assumptions — only measured verdicts.
**Acceptance criteria:** ≥1 verified working path per platform; dead ends documented; truth table published.
**Evidence (measured):**
- Bare yt-dlp: all 10 player clients → `Sign in to confirm you're not a bot` ❌
- Stack discovery: yt-dlp 2026.08 requires `--js-runtimes node` (EJS challenge solving) — without it extraction is crippled ⚠️
- bgutil POT server 2.0.1 built (npm ci + tsc) and running on :4416 ✅ (a pre-existing healthy server was detected via EADDRINUSE — documented gotcha)
- `tv` client + full stack: 1 success / ~12 attempts → flaky, non-deterministic ⚠️
- Public Invidious ×10, Piped ×8: all dead (403/500/timeout/BAD-JSON) ❌
- Public Cobalt ×3: JWT required ❌; ddownr: empty ❌; mp3youtube.cc: bad request ❌
- **loader.to AJAX API: VERIFIED end-to-end by this build** — submit → poll → CDN → MP4 ffprobe-verified (h264+aac, 19.13 s) ✅
- **instaloader single-post: VERIFIED** — anonymous MP4 (h264+aac, 13.5 s, 3.2 MB) + JPG + JSON ✅
- yt-dlp IG extractor: root-caused as endpoint-gated on datacenter IPs ❌ (research report)
- IG GraphQL `doc_id=27128499623469141`: verified by research run; flaky in build runs (execution error ×3) → tier-1-with-retries, adaptive demotion ⚠️
- Public cobalt `co.otomir23.me`: responds, may degrade to `.jpg` → verifier rejects images ⚠️
- Parallel web-research agents (~24 + ~10 searches) produced 5 research docs (1,500+ lines) → `docs/research/` ✅

## Phase 2 — Documentation Suite ✅

**Goal:** perfect-level operating documents that let any agent run/extend this system cold.
**Acceptance criteria:** six documents (claude.md, agents.md, techstack.md, phases.md, plan.md, skills.md), each complete, mutually consistent, evidence-linked.
**Evidence:** all six written under `docs/` and linked from README; truth table in claude.md §2 matches Phase-1 measurements 1:1.

## Phase 3 — Core Engine ✅

**Goal:** orchestrator, method contract, registry, truth agent, verifier, models, CLI.
**Acceptance criteria:** fallback chain executes with per-method timeouts; every attempt recorded; verifier rejects invalid media; `--json` output on every command.
**Evidence:** see Phase 5 E2E run — chain ytdlp_pot→loaderto executed with attempt log; truth.json written; ffprobe verification active.

## Phase 4 — Method Implementations ✅

**Goal:** six methods across two platforms.
**Acceptance criteria:** each method independently invocable via `--method`; MethodError carries one-line root cause; loader.to throttled (2.5 s poll); IG graphql mints fresh csrftoken per run.
**Evidence:** `agrab methods --json` lists all six with platform/timeout/health; per-method runs logged in Phase 5.

## Phase 5 — End-to-End Testing ✅

**Goal:** prove the full system with real downloads, both platforms, `agrab test`.
**Acceptance criteria:** YouTube E2E pass via chain; Instagram E2E pass via chain; verifier active; JSON evidence captured.
**Evidence (measured 2026-10-03):**

- `agrab doctor --json` → `ok: true`, 9/9 checks (yt-dlp 2026.08.19, node v24.21.0, ffmpeg 7.1.5, ffprobe, instaloader importable, POT server HTTP 200, egress YT+IG, truth store) ✅
- `agrab test --json` (run 2, after contamination fix) → `ok: true`:
  - **YouTube PASS** — `loaderto`, 28.5 s total, `/…/youtube/Me_at_the_zoo.mp4`, ffprobe: mp4/h264/aac, 19.13 s, 743,099 B. Adaptive ranking had demoted `ytdlp_pot` (rate 0 %) so the chain led with the workhorse — correct quarantine-aware behavior.
  - **Instagram PASS** — chain depth saved it: `ig_instaloader` rate-limited (honest failure — refused to fake success) → `ig_graphql` 401 → `ig_cobalt` thumbnail correctly rejected by the `.jpg` trap check → **`ytdlp_instagram` delivered the real post** (3,257,414 B, 13.55 s, h264/aac).
- **Audio path PASS** — `agrab download <yt> --audio --quality mp3 --json` → `loaderto`, mp3 verified.
- **Contamination bug caught & fixed during Phase 5:** run 1 showed Instagram "PASS" with the YouTube test file's exact byte signature (743,099 B / 19.13 s) — the `ig_instaloader` fallback glob accepted a pre-existing file from the shared output dir. Fixes: (1) methods only accept files created during their own run (mtime + pre-existing snapshot); (2) per-platform test output dirs; (3) a distinctness regression guard in `tests/test_e2e.py`. Run 2 is therefore clean and honest.
- `pytest -k test_detect_platform` → 1 passed ✅
- `agrab methods --json` ranked order after telemetry: `ytdlp_instagram -> loaderto -> ig_instaloader -> ig_cobalt -> ytdlp_pot -> ig_graphql` — live adaptive re-ranking working as designed.

## Phase 6 — Publication

**Goal:** GitHub repo under `hamza140202`, everything pushed.
**Acceptance criteria:** repo created; docs + code + research + tests pushed; README renders; commit history meaningful.
**Evidence:** repo `hamza140202/agentgrab` created via API and pushed 2026-10-03 — 38 files, commit `6b566cf` ("feat: AgentGrab 1.0.0 …"), default branch `main`. Verified via GitHub API tree listing (code 21 files, docs 11, research 5, tests, skills, pot-server, packaging).

---

## Standing Process — Future Phases

New work (TikTok, Reddit, X, Douyin, RedNote per the product roadmap) follows the same loop:

1. **Truth phase** — live-test candidate methods on the target machine; document dead ends.
2. **Doc phase** — update claude.md §2 truth table + techstack.md + plan.md matrix in the same commit as the code.
3. **Build phase** — one file per method, register, wire into platform chain.
4. **Test phase** — canonical vectors per platform; E2E only; append evidence here.
5. **Publish phase** — push; update README platform badge.

**Definition of Done (any phase):** criteria met + evidence lines appended to this file + worklog entry + docs consistent with reality.
