# AGENTS.md — Multi-Agent Operating Manual for AgentGrab

> **Purpose:** This file defines how AI agents (Claude Code, CLI copilots, autonomous pipelines) operate AgentGrab, how work is divided among specialized agent roles, and the exact handoff protocol that keeps multi-agent runs consistent. It doubles as a system prompt seed: point any capable agent at this file and it can operate the project.

---

## 1. The Four Operational Roles

AgentGrab's architecture mirrors a four-agent crew. In production these roles are **implemented as code** (the downloader runs them on every request); in development they map to **how you should behave** when working on the repo.

### 🎼 The Orchestrator (`orchestrator.py` — and you, when coordinating)

**Job:** own the end-to-end pipeline. Detect platform, rank methods via truth data, run the fallback chain with per-method timeouts, never let one failure kill the mission.

**Operating rules:**
- Always attempt methods in truth-ranked order. Never hardcode a "best" method in the hot path — trust the health store.
- Enforce per-method budgets. A hung method is a failed method.
- Every attempt (success or failure) is recorded to the truth store. No silent failures.
- Return structured `DownloadResult` — the caller (an agent) needs machine-readable truth, not prose.

**Human-agent equivalent:** when you run a build session, you are the orchestrator: sequence the tasks, delegate, keep the chain moving, record everything.

### 🔍 The Verifier (`verifier.py` — and you, when reviewing)

**Job:** treat every downloaded byte as guilty until proven innocent. Run ffprobe: confirm container, confirm a real audio/video stream, confirm duration > 0.5 s, reject images served as videos (the cobalt `.jpg` trap).

**Operating rules:**
- Never accept "the request returned 200" as success. Files lie.
- Reject mjpeg/png-only files. Reject 10 KB "videos".
- When reviewing code/docs: check claims against `docs/claude.md` truth table. Unverified claims get flagged, not merged.

### 📊 The Truth Agent (`truth.py` — and you, when analyzing)

**Job:** maintain the empirical record. Every attempt appends to `~/.agentgrab/truth.json`: attempts, successes, failures, latency, consecutive-failure streaks. Methods with ≥5 consecutive failures enter **quarantine** (demoted to last-resort but never removed — clouds heal, and a quarantined method may recover).

**Operating rules:**
- Ranking = consecutive failures (asc) → success rate (desc) → avg latency (asc).
- Never delete history; reset only via explicit `agrab truth reset`.
- When you (as an agent) discover a method died or revived, update `docs/claude.md` §2 truth table **in the same commit**.
- Report truth, not hope: "loader.to: 14/15 today" beats "loader.to should work".

### 🧪 The Tester (`cli.py test`, `tests/test_e2e.py` — and you, when validating)

**Job:** prove the system works with real downloads, on the real machine, right now. No mocks in the critical path.

**Operating rules:**
- E2E tests hit live platforms with canonical URLs (see §4). A "test" that doesn't download and ffprobe a file is a smoke check, not a test.
- Run `agrab test --json` and paste the result into the phase evidence log.
- Flaky ≠ broken: rerun twice before declaring failure. Record the pass rate, not a boolean.

---

## 2. Handoff Protocol (multi-agent sessions)

When several agents share this repo, the shared state is: `worklog.md` (append-only), `docs/claude.md` (truth table), `docs/phases.md` (evidence). Protocol:

1. **Before starting:** read `worklog.md` and `docs/claude.md` §2. Know what previous agents proved and broke.
2. **Claim a Task ID** (e.g. `3-b`) and state it in your first worklog entry.
3. **During work:** each unit of work ends with an append to `worklog.md` using the standard block:

   ```markdown
   ---
   Task ID: 3-b
   Agent: <name>
   Task: <one line>

   Work Log:
   - <concrete steps, commands, and outcomes>

   Stage Summary:
   - <key results / decisions / artifacts>
   ```

4. **Truth changes are commits:** if you learn a method died/revived, update `docs/claude.md` §2 + append to worklog + commit. One discovery, one commit, no batching.
5. **Never trust another agent's unverified claim.** Re-run the command. The truth store exists because claims rot.

---

## 3. Command Surface for Agents

Every command supports `--json`. Stdout = machine output; stderr = human logs.

```bash
agrab download <url> [--audio] [--quality 360|480|720|1080|1440|max]
                     [-o OUTPUT_DIR] [--method NAME] [--timeout SEC]
                     [--no-verify] [--json]
agrab download URL1 URL2 ... --json        # batch, returns JSON array
agrab methods [--json]                     # registry + live health, ranked
agrab truth [--json] / agrab truth reset
agrab test [--quick] [--json]              # E2E: real YouTube + Instagram downloads
agrab doctor [--json]                      # environment diagnostics
agrab pot start|status [--json]            # bgutil POT server control
```

**Agent decision loop** (canonical):

```bash
agrab doctor --json            # 1. is the environment sane?
agrab download "$URL" --json   # 2. try the chain
# ok:false? -> read attempts[].error, run `agrab methods --json`,
# retry once; if still failing, report the attempts array verbatim.
```

When reporting failure to a human, include the full `attempts` array from the JSON — it is the entire diagnostic history of the request.

---

## 4. Canonical Test Vectors

Used by `agrab test` and expected to remain stable:

| Platform | URL | Why |
|---|---|---|
| YouTube | `https://www.youtube.com/watch?v=jNQXAC9IVRw` | "Me at the zoo" — first YouTube video, never deleted, 19 s |
| Instagram | `https://www.instagram.com/p/-CDUMkliABpa/` | Public 2020 post, anonymous-accessible (verified) |

If a canonical vector dies, replace it with an equivalent stable asset and update this table + `tests/test_e2e.py` in one commit.

---

## 5. Escalation Ladder (what to do when downloads fail)

1. Read `attempts[].error` from the JSON result — find the last method that *almost* worked.
2. `agrab methods --json` — is the best method quarantined? Is success rate degraded platform-wide (API outage) vs. per-method (bug)?
3. `agrab doctor --json` — is the POT server down? Node missing? Network partitioned?
4. `agrab truth reset` **only if** you suspect stale health data (e.g. after network restoration).
5. Retry once with `--method` forced to the historically-reliable method (`loaderto` for YouTube, `ig_instaloader` for Instagram).
6. Still failing? Update `docs/claude.md` §2 if the platform changed, and surface the failure honestly. Agents do not paper over outages.

---

## 6. Agent Etiquette (hard rules)

- Do not ask humans questions the truth store can answer. Run the command first.
- Do not fabricate success. If verification failed, the download failed.
- Do not remove a working-but-slow method without telemetry proving it's dead for 24 h+.
- Do not add cookies/login sessions to bypass a failing method — the mission is **cookieless**. A cookie-based path may exist only as an explicitly-labeled non-default escape hatch.
- Keep `docs/claude.md` §2 and the truth store in sync. Divergence between documented truth and live telemetry is the #1 way agent systems rot.
