---
name: agentgrab
description: Download YouTube or Instagram media (videos/reels/posts, audio) from cloud servers without cookies or logins, using AgentGrab's self-healing fallback chain. Use when the user asks to download/save/fetch a YouTube video or Instagram reel/post — especially on servers, VPS, sandboxes, or AI CLI environments where yt-dlp alone fails with "Sign in to confirm you're not a bot".
---

# AgentGrab — cookieless media downloads for agents

## When to use

- "Download this YouTube video / Instagram reel" on any server or cloud environment
- yt-dlp alone fails with bot checks or login gates
- You need a file (not a webpage), with verification and machine-readable results

## Quick reference

```bash
# 1. Environment sanity (once per session)
agrab doctor --json

# 2. The one command that does everything (chain, retries, verification)
agrab download "https://www.youtube.com/watch?v=VIDEO_ID" --json
agrab download "https://www.instagram.com/reel/SHORTCODE/" --json

# Options
agrab download URL --audio --quality mp3 --json      # audio only
agrab download URL --quality 720 --json              # cap video height
agrab download URL -o /tmp/media --json              # output dir
agrab download URL --method loaderto --json          # force one method
agrab download URL1 URL2 --json                      # batch → JSON array
```

## Interpreting results

- `ok: true` → file ready at `.file`, ffprobe-verified (`.verified`), method used in `.method`
- `ok: false` → `.attempts[]` holds every method's failure cause; retry once, then
  surface `.attempts` verbatim — it is the complete diagnostic history
- Health/retries: `agrab methods --json` (ranked health), `agrab truth --json` (raw store)

## Failure playbook

1. Read `attempts[].error` — find the closest-to-success method
2. `agrab methods --json` — degraded platform-wide (API outage) or one method (bug)?
3. `agrab doctor --json` — POT server down? node/ffmpeg missing? egress blocked?
4. `agrab pot start` — repair the YouTube fast-path (never blocks the chain; tier-2 works without it)
5. Force the historically-reliable path: `--method loaderto` (YouTube) / `--method ig_instaloader` (Instagram)

## Hard rules

- Stdout is JSON when `--json` is passed; logs go to stderr — never parse human logs
- Verification is always on: a `.jpg` thumbnail from cobalt or an error page saved as
  `.mp4` fails the chain — do not disable it to "make things pass"
- No cookies/logins: the mission is cookieless operation; a cookie path exists only as
  an explicitly non-default escape hatch
- Exit codes: 0 success · 1 download failed (read JSON) · 2 usage/environment error

## Install (if missing)

```bash
pip install -e /path/to/agentgrab   # or: pip install git+https://github.com/hamza140202/agentgrab.git
# system deps: node ≥22, ffmpeg ≥6, git
agrab pot start
```

Full docs: `docs/skills.md` in the repo (skills: download / health / pot-ops / extend / truth-keeping).
