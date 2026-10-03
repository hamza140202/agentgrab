# AgentDL — Ecosystem & Architecture Research

**Task ID:** 2-c · **Date:** October 2026 · **Scope:** GitHub ecosystem survey + architecture intelligence for an agent-oriented media downloader (orchestrator + strategy registry + fallback chains + verifier + structured JSON output).

**Method:** web search + direct browsing of GitHub repos/READMEs/wiki + **live verification against the locally installed `yt-dlp 2026.08.19`** (all Python API snippets below were checked against the installed package) + reading yt-dlp's own source & CI workflows (sparse-cloned). `api.github.com` was avoided as instructed.

---

## 1. Ecosystem survey — tools to learn from

### 1.1 yt-dlp — <https://github.com/yt-dlp/yt-dlp>

The dominant downloader (Unlicense license). Key architecture lessons:

- **Plugin system via namespace packages** (`yt_dlp_plugins.extractor` / `yt_dlp_plugins.postprocessor`). Plugins are auto-discovered from `${XDG_CONFIG_HOME}/yt-dlp/plugins/`, `/etc/yt-dlp/plugins/`, `PYTHONPATH`, or pip-installed packages. Extractor plugins **take priority over built-ins** — a clean hook point for AgentDL-style overrides. Env var `YTDLP_NO_PLUGINS` disables them all. Docs: README "# PLUGINS" section + wiki `Plugin Development.md` + template repo `yt-dlp/yt-dlp-sample-plugins`. There is even an archive of rejected plugins: `yt-dlp-archives/plugins`.
- **Extractor arguments** (`--extractor-args KEY:ARGS`) are the sanctioned escape hatch for platform quirks. Programmatically this is the `extractor_args` dict param on `YoutubeDL` (see §2.3). Verified key args for our target platforms:

  | Platform | Extractor arg | Purpose |
  |---|---|---|
  | YouTube | `youtube:player_client=mweb,tv,web_safari,...` | Select Innertube client (default is `visionos,web`); some clients need PO tokens |
  | YouTube | `youtube:po_token=CLIENT.CONTEXT+TOKEN` | Manual PO token (`gvs`/`player`/`subs` contexts) |
  | YouTube | `youtube:fetch_pot=auto` / `pot_trace=true` | PO-token provider policy / debugging |
  | TikTok | `tiktok:api_hostname=api22-normal-c-alisg.tiktokv.com`, `app_version`, `device_id`, `app_info` | Mobile-API extraction knobs (useful from datacenter IPs) |
  | Douyin | `DouyinIE` lives inside `yt_dlp/extractor/tiktok.py` (class `DouyinIE(TikTokBaseIE)`) | Douyin is a first-class yt-dlp extractor |
  | Instagram | `instagram:app_id=ios\|web\|<numeric>` | X-IG-App-ID header choice |
  | X/Twitter | `twitter:api=syndication` | Syndication API fallback (no login) |
  | RedNote | `yt_dlp/extractor/xiaohongshu.py` (`XiaoHongShuIE`) | Supported natively |
  | Reddit | `yt_dlp/extractor/reddit.py` (`RedditIE`) | Supported natively |

- **Test architecture (verified from `.github/workflows/` + `devscripts/run_tests.py`):** yt-dlp splits CI into
  - `core` tests → `pytest -m "not download"` (offline; runs on every PR, incl. Windows + pypy matrix);
  - `download` tests → `pytest -m "download"` (network, known-flaky, run separately; `RETRIES = 3`);
  - a separate `challenge-tests.yml` workflow scoped to `yt_dlp/extractor/youtube/pot/**`, `jsc/**` (runs Deno/Bun/Node/QuickJS matrix);
  - a `--flaky` / `--disallow-flaky` mechanism: in CI, flaky tests are *skipped* (`--disallow-flaky` is appended when `CI` env is set) rather than allowed to fail builds. `handler_flaky` pytest marker + conftest autouse fixture implements it.
  - Lesson for AgentDL: **offline unit suite must be the required check; online "smoke downloads" run on a schedule with retries and are never merge-blocking.**
- **Embedding guidance (from README "# EMBEDDING YT-DLP"):** *"Your program should avoid parsing the normal stdout... use options such as `-J`, `--print`, `--progress-template`, `--exec`"* — and from Python, embed `YoutubeDL` directly. Also: `devscripts/cli_to_api.py` translates any CLI switches to `YoutubeDL` params — a great devtool to copy.
- **License:** Unlicense (embedding is friction-free). cobalt by contrast is **AGPL-3.0** — do not copy its code into AgentDL.

### 1.2 cobalt — <https://github.com/imputnet/cobalt> (monorepo: api/, web/, packages/)

"paste the link, get the file" — the reference for **API-shaped design** (AGPL-3.0; hosted instances bot-protected; you self-host). From `docs/api.md`:

- `POST /` with a small JSON schema (`url` required; everything else optional with sane defaults: `videoQuality: 1080`, `downloadMode: auto|audio|mute`, `filenameStyle`, `youtubeVideoCodec: h264|av1|vp9`, `tiktokFullAudio`, `youtubeHLS`...).
- **Response envelope is a union on a `status` key**: `tunnel` | `local-processing` | `redirect` | `picker` | `error`. Exactly the pattern agents need: one field to switch on, everything else structured.
- Errors are **machine-readable codes** (`error.code`, e.g. `api.auth.missing`) with optional `error.context` (`service`, `limit`) — never prose.
- Rate limiting exposed via standard `RateLimit-*` headers (IETF draft); auth via `Authorization: Api-Key <uuid>` or short-lived JWT `Bearer` (from a Turnstile challenge) via `POST /session`.
- `GET /` returns instance info (`cobalt.version`, `cobalt.services[]`, `git.commit`) — a health/capability endpoint worth copying (`GET /health` for AgentDL).
- `GET /tunnel` streams the file; returns `Content-Length` or `Estimated-Content-Length` (explicitly "not for strict size verification" — verification must happen on the artifact itself).
- **Ethics stance** documented in README (proxy-like, no caching, public content only) — good precedent language for AgentDL's README.

### 1.3 gallery-dl — <https://github.com/mikf/gallery-dl> (active dev moved to Codeberg, announced in issue #9374)

- Image-gallery counterpart; optional **`ytdl` integration** delegates HLS/DASH video to yt-dlp — precedent for "compose with yt-dlp instead of reimplementing".
- Robust **download-archive** concept (sqlite/postgres-backed dedup) and configuration-file layering (`/etc/gallery-dl/config.json` → user config → `--config`), PyPI + standalone binaries + Snap + Chocolatey distribution, nightly builds from a separate builds repo (`gdl-org/builds`).
- Ecosystem data point: even flagship GitHub media tools are hedging to Codeberg — AgentDL should keep repo metadata portable (standard CI config, no GitHub-only hard dependencies beyond Actions).

### 1.4 brainicism/bgutil-ytdlp-pot-provider — <https://github.com/Brainicism/bgutil-ytdlp-pot-provider>

The canonical solution to YouTube's PO-token / "Sign in to confirm you're not a bot" wall on **datacenter IPs** (maintained by a yt-dlp maintainer; MIT-ish; PyPI + Docker):

- Two-part architecture: **Provider** (HTTP server on port **4416**, Docker image, Node ≥22 or Deno ≥2; or a per-call script) + **Provider plugin** (PyPI `bgutil-ytdlp-pot-provider`) that plugs into yt-dlp's **PO Token Provider Framework** (`yt_dlp/extractor/youtube/pot/README.md`).
- Zero-config when on `127.0.0.1:4416`; otherwise `--extractor-args "youtubepot-bgutilhttp:base_url=http://host:port"`.
- Internally caches tokens (`TOKEN_TTL` env, default 6 h; tokens are **bound to video ID** now, and can expire within ~12 h) — AgentDL should treat tokens as short-lived per-video artifacts, never long-lived secrets.
- Honest caveat in their README: a PO token "does not guarantee bypassing 403" and does **not** bypass IP-based login walls; multiple player clients may need trying (`player-client=mweb,tv,web_safari`). → Confirms AgentDL's need for **fallback chains**, not silver bullets.
- Verification pattern for plugins: look for `PO Token Providers: bgutil:http-x.y.z (external)` lines in `yt-dlp -v` output — implies AgentDL's doctor command should surface provider/plugin load status similarly.
- PO Token facts (from wiki `PO Token Guide.md`): generated by BotGuard (Web)/DroidGuard (Android)/iOSGuard; per-platform incompatible; contexts `gvs`, `player`, `subs`; client matrix (`web` needs Subs+GVS, `tv` none-but-DRM-without-cookies, `android` GVS-or-Player, `web_embedded` none but only embeddable videos). Related: `iv-org/youtube-trusted-session-generator`, `LuanRT/BgUtils`.

### 1.5 LuanRT/YouTube.js (`youtubei.js`) — <https://github.com/LuanRT/YouTube.js>

- TypeScript client for YouTube's private InnerTube API; Node/Deno/browsers; MIT. `const innertube = await Innertube.create()`.
- Powers BgUtils (PO token minting). For AgentDL: it's the reference if we ever need a first-class InnerTube strategy outside yt-dlp, but adopting it means shipping a JS runtime — keep it as an **optional sidecar strategy**, not a core dependency.

### 1.6 Evil0ctal/Douyin_TikTok_Download_API — <https://github.com/Evil0ctal/Douyin_TikTok_Download_API> (v5, 2026)

**The closest architectural cousin to AgentDL.** v5 is a ground-up rewrite whose stated motive is exactly our thesis: *"the API would die quietly and nobody would know. A cookie expires, a signature algorithm changes, an endpoint gets rate-limited, and you find out when someone files an issue."* Its v5 design:

- **Identity pool that maintains itself** (headless browser mints guest identities; pool tops itself up) with **health tiers, quantised LRU rotation, one in-flight lock per identity, token bucket per (identity, endpoint), circuit breaker per endpoint**.
- **One structured record per request**; live health visible for every identity/endpoint.
- **Async-by-default API** (`202` + `task_id`, `?wait=` to force sync).
- **One service layer, three entrances**: REST + **MCP (streamable-http)** + CLI — the MCP badge is first-class in their README.
- Stack: Python 3.12, FastAPI, SQLAlchemy 2 async, Typer, structlog, wreq (browser TLS fingerprint emulation), httpx, uv, ruff, mypy, pytest, Docker Compose (three images incl. a Go download sidecar and a browser-identity sidecar).
- Project layout (verbatim, worth emulating): `src/dtk/{api, platforms, signing, transport, identity, scheduler, services, worker, db, ops, media, models, urls, mcp, cli, i18n, core}` with `platforms/` = per-platform adapters (endpoints, params, parsers) and `services/` shared by all entrances.
- Takeaway for AgentDL: prove that **orchestrator + per-platform strategy adapters + health/circuit-breaker state + MCP surface** is the 2026 state of the art in this domain.

### 1.7 iv-org/invidious-companion — <https://github.com/iv-org/invidious-companion>

Deno-based companion service that Invidious now delegates **all YouTube stream retrieval** to (the old invidious/Companion naming is superseded). Confirms the industry direction: main service stays simple, flaky upstream logic lives in a **separately deployable companion process**. AgentDL's orchestrator should assume its "YouTube strategy" may need to be a hot-swappable/sidecar component.

### 1.8 MCP servers for yt-dlp (AI agents increasingly speak MCP)

Documented via npm registry search + listings (glama.ai, lobehub, mcpservers.org):

| Server | Package / repo | Notes |
|---|---|---|
| **yt-dlp-mcp-server** | `antonio-orionus/yt-dlp-mcp-server` (npm `yt-dlp-mcp-server` v0.2.0, 2026-06) | The serious one: **28 typed tools**, "plan before write" (`ytdlp_plan_download` dry-run), 323 options mirrored from `yt_dlp.options.create_parser()`, archive inspect/check tools, argv arrays with `shell:false`, expert raw-argv mode gated behind `YTDLP_MCP_ENABLE_EXPERT=true`, Docker bundle (yt-dlp+ffmpeg+ffprobe+Deno). Tool groups: environment / inspect / plan / download / archive / download+postprocess / expert; plus `ytdlp://capabilities` resource. |
| @kevinwatt/yt-dlp-mcp | npm v0.10.0 (2026-08), `github.com/kevinwatt/yt-dlp-mcp` | Thin wrapper, actively updated |
| @gtvar/yt-dlp-mcp | npm v1.0.5, `github.com/Gtvar/yt-dlp-mcp` | Thin wrapper |
| yt-dlp-mcp | npm v1.3.0 | "automatic setup" wrapper |
| easyhak YouTube Search & Download MCP | glama.ai listing | yt-dlp + LLM integration |
| mcp-youtube | modelscope listing | subtitles-focused |

**Gap analysis:** there is **no MCP server covering Douyin/RedNote/Instagram/Reddit** the way AgentDL intends; and none of the yt-dlp MCP wrappers do fallback-chain orchestration or verification. AgentDL CLI-first + MCP surface = differentiated.

### 1.9 "Media downloader for AI agents" — prior art search

No established project named as such exists yet (searches for `agent youtube downloader cli`, `ai agent video download tool` return only MCP wrappers, generic tutorials, and agent-CLI guidelines). Emerging conventions from the agent-CLI literature (apidog "Top CLI tools for AI agents" 2026-09, BlindPay CLI, glama "build-with-ak", `ai-native-cli` spec):

- **`--json` on every command**, stable envelope `{ok, data?, error?}`;
- **predictable/semantic exit codes**; explicit flags; no prose-only output;
- `ai-native-cli` spec defines a **three-layer certification model: Agent-Friendly → Agent-Ready → Agent-Native** (default JSON, self-description via `--help --json`).

---

## 2. yt-dlp Python embedding (verified against installed yt-dlp 2026.08.19)

### 2.1 Canonical embedding

```python
import json
import yt_dlp

URL = 'https://www.youtube.com/watch?v=YE7VzlLtp-4'

ydl_opts = {}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(URL, download=False)          # simulate / metadata only
    safe  = ydl.sanitize_info(info)                       # makes info JSON-serializable
    print(json.dumps(safe))
```

- Constructor signature (verified): `YoutubeDL.__init__(self, params=None, auto_init=True)`.
- Key public API (verified signatures):

```python
ydl.extract_info(url, download=True, ie_key=None, extra_info=None,
                 process=True, force_generic_extractor=False)
ydl.download(url_list)                       # returns _download_retcode (0 ok, 1 errors)
ydl.download_with_info_file(info_filename)   # re-download from a saved .info.json
ydl.sanitize_info(info_dict, remove_private_keys=False)
ydl.prepare_filename(info_dict, dir_type='', *, outtmpl=None, warn=False)
ydl.add_post_processor(pp, when='post_process')   # when ∈ utils.POSTPROCESS_WHEN
ydl.add_progress_hook(ph)
```

- **`extract_info` return is NOT guaranteed JSON-serializable** — always pass through `sanitize_info` (official warning, README §Embedding).

### 2.2 Options that matter for an agent-oriented wrapper (verified against `help(YtDLP)` param docs)

```python
opts = {
    # output / filesystem
    'outtmpl': {'default': '%(uploader).30B-%(title).200B-%(id)s.%(ext)s'},
    'paths':   {'home': '/data/media', 'temp': '/data/tmp'},   # keys: home,temp,+OUTTMPL_TYPES
    'restrictfilenames': True,
    'download_archive': '/var/lib/agentdl/archive.txt',  # youtube-dl style seen-IDs file

    # simulation vs download
    'skip_download': False,
    'simulate': True,            # unset/None => simulate only if listing flags used
    'extract_flat': False,       # True: never resolve; 'in_playlist': don't resolve inside playlists

    # format
    'format': 'bestvideo*+bestaudio/best',   # format selection strings (see README FORMAT SELECTION)

    # resilience (yt-dlp does its own retrying)
    'retries': 3,                       # known errors, default 3
    'extractor_retries': 3,
    'fragment_retries': 10,
    'concurrent_fragment_downloads': 4,
    'socket_timeout': 15,
    'wait_for_video': (1, 30),          # scheduled streams
    'sleep_interval_requests': 0.5,

    # observability
    'quiet': True,
    'no_warnings': False,
    'noprogress': True,
    'progress_hooks': [my_progress_hook],
    'postprocessor_hooks': [my_pp_hook],
    'logger': MyLogger(),               # needs .debug/.info/.warning/.error
    'color': {'stdout': 'never', 'stderr': 'never'},   # or a single policy string

    # extraction behaviour / platform quirks  <-- KEY for fallback chains
    'extractor_args': {
        'youtube': {'player_client': ['mweb', 'tv', 'web_safari'],
                    'fetch_pot': ['auto']},
        'twitter': {'api': ['syndication']},
        'instagram': {'app_id': ['ios']},
        'tiktok': {'api_hostname': ['api22-normal-c-alisg.tiktokv.com']},
    },
    'http_headers': {'User-Agent': '...'},
    # cookies: 'cookiefile': '/path/cookies.txt'   (AgentDL default: none, per design)
}
```

- `extractor_args` contract (verified from param docs): *"A dictionary of arguments to be passed to the extractors... Argument values must always be a list of string(s). E.g. `{'youtube': {'skip': ['dash','hls']}}`"*. This is the exact mechanism for implementing **per-strategy platform tuning** without shelling out to the CLI.
- `--extractor-args` CLI syntax (README): `KEY:ARGS`, `ARGS` is `;`-separated `ARG=VAL1,VAL2`; in CLI, `-` and `_` interchangeable. In the Python dict, keys are the **extractor name** (`youtube`, `twitter`, `youtubepot-bgutilhttp`...).
- bgutil provider wiring (README of bgutil): if the POT HTTP server is reachable at non-default URL: `'extractor_args': {'youtubepot-bgutilhttp': {'base_url': ['http://127.0.0.1:8080']}}` (CLI form: `--extractor-args "youtubepot-bgutilhttp:base_url=http://..."`; multiple args to one provider are `;`-separated).

### 2.3 Hooks & error handling

Progress hook payload (official example + docs):

```python
def my_progress_hook(d):
    # d['status'] ∈ {'downloading', 'finished'} (also 'error' possible in some paths)
    # downloading: d['downloaded_bytes'], d['total_bytes'] or d['total_bytes_estimate'],
    #              d['speed'], d['eta'], d['fragment_index'], d['fragment_count'], d['filename']
    if d['status'] == 'finished':
        ...  # post-processing comes next
```

Postprocessor hook payload: `{'status': 'started'|'processing'|'finished', 'postprocessor': name, 'info_dict': ...}` — docs say *"Check this first and ignore unknown values."*

Custom postprocessor:

```python
class MyCustomPP(yt_dlp.postprocessor.PostProcessor):
    def run(self, info):
        self.to_screen('Doing stuff')
        return [], info

with yt_dlp.YoutubeDL() as ydl:
    ydl.add_post_processor(MyCustomPP(), when='pre_process')  # when ∈ POSTPROCESS_WHEN
```

Error classes (verified import surface of `yt_dlp.utils`, 2026.08.19):

```
YoutubeDLError                      # base
├── DownloadError                   # wrapper raised by extract_info/download — catch this in orchestrator
├── ExtractorError                  # extraction-stage failure (has .video_id, .exc_info)
├── GeoRestrictedError
├── UnavailableVideoError
├── ContentTooShortError
├── PostProcessingError
├── SameFileError, LockingUnsupportedError, XAttrMetadataError,
│   RegexNotFoundError, UnsupportedError, UnsafeExecExpansionError
+ networking exceptions: yt_dlp.networking.exceptions.HTTPError, TransportError, ...
```

Pattern: run `extract_info` inside `try/except yt_dlp.utils.DownloadError as e` — the orchestrator maps `str(e)`/`cause` onto retryability (see §4). CLI main (source-verified) exits: **0** success, **1** error(s) occurred, **100** `MaxDownloadsReached`, **101** `DownloadCancelled`, and catches `DownloadError`→1.

### 2.4 JSON output modes (CLI reference; useful for subprocess strategies)

From `yt_dlp/options.py` (source-verified):

- `-j, --dump-json` — quiet; one JSON per video; simulates unless `--no-simulate`.
- `-J, --dump-single-json` — whole playlist/URL in one line.
- `-O, --print [WHEN:]TEMPLATE` — print arbitrary template fields (e.g. `--print after_move:filepath` → **final filepath**, the reliable way to learn where the file landed).
- `--progress-template download:TEMPLATE` — emit machine-parsable progress lines (`%(progress._percent_str)s` etc.; video fields under `%(info.id)s`).
- `--newline` — progress as one line per tick (log-friendly).

`devscripts/cli_to_api.py` (upstream devtool) converts any CLI invocation to `YoutubeDL` params — AgentDL should ship a similar `--show-params` debug command.

---

## 3. Verification patterns for downloaded artifacts

Layered checks (cheapest first), as informed by yt-dlp/cobalt/gallery-dl practice:

1. **Existence & completeness**
   - yt-dlp writes `<file>.part` during download and renames on success → any leftover `.part`/`.ytdl` next to the artifact = interrupted (also `.part-Frag*` for fragmented HLS/DASH).
   - `info_dict['requested_downloads'][0]['filepath']` (or `--print after_move:filepath`) is the post-merge truth of where the file is.
   - Compare file size to `info['filesize']`/`filesize_approx` when present (cobalt's `Estimated-Content-Length` header is explicitly *not* for strict verification — same idea: estimates never validate).
2. **ffprobe structural validation** (the industry-standard integrity check):

   ```bash
   ffprobe -v error -print_format json -show_format -show_streams -show_entries \
     "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,sample_rate" file.mp4
   ```

   ```python
   import json, subprocess
   def probe(path):
       out = subprocess.run(
           ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
           capture_output=True, text=True, check=True).stdout
       return json.loads(out)
   # validate: format.duration within ±2s of info['duration'];
   # a video stream exists with expected codec (h264/av1/vp9) & width/height;
   # an audio stream exists (unless downloadMode=mute); size>0; no 'error' in output.
   ```

   Deep integrity option (slow): `ffmpeg -v error -i file -f null -` surfaces decode errors; unix/SU consensus for "is it complete".
3. **Identity & dedup**
   - youtube-dl-style **download archive**: `download_archive` file with lines `youtube <id>` (id + extractor); yt-dlp skips and records entries. `--force-write-download-archive` even in simulate mode (option verified). gallery-dl generalizes this to sqlite/postgres archives.
   - **Checksums**: yt-dlp's own test suite uses MD5 of fixture files (`_file_md5` in `test/test_download.py`); for AgentDL record `sha256` in the job ledger (blake3 if perf matters); compare against platform-declared size rather than nonexistent remote hashes.
4. **Metadata cross-check**: title/id/duration/extractor from info dict vs probe output; uploader, timestamp for the JSON result envelope.
5. **Result envelope** (cobalt-style): `{"ok": true, "status": "verified", "artifact": {...ffprobe summary...}, "source": {...strategy, extractor, id...}, "attempts": [...]}`.

---

## 4. Retry / fallback orchestration (Python)

### 4.1 Strategy registry + ordered fallback chain

```python
from dataclasses import dataclass

@dataclass
class Strategy:
    name: str
    platforms: frozenset[str]           # e.g. {'youtube'}
    weight: int = 100                   # lower = tried earlier within chain
    def build(self, ctx) -> 'Downloader': ...

class Registry:
    def __init__(self): self._s: dict[str, list[Strategy]] = {}
    def register(self, s: Strategy):
        self._s.setdefault(s.platforms, []).append(s)
    def chain_for(self, url_platform: str) -> list[Strategy]:
        return sorted(self._s.get(url_platform, []), key=lambda s: s.weight)

class Orchestrator:
    def run(self, url):
        last_err = None
        for strat in self.registry.chain_for(self.detect_platform(url)):
            if self.breaker.is_open(strat.name):
                continue
            for attempt in backoff(range(3)):          # exponential + jitter
                try:
                    result = strat.build(self.ctx).download(url)
                    self.health.record(strat.name, ok=True)
                    return result
                except RetryableError as e:
                    last_err = e; continue
                except FatalError as e:
                    last_err = e; break
            self.health.record(strat.name, ok=False)
            self.breaker.record_failure(strat.name)
        raise AllStrategiesFailed(last_err)
```

Concrete YouTube chain (informed by §1.4/1.1): `yt-dlp+mweb client (bgutil POT)` → `yt-dlp+tv/web_safari` → `yt-dlp+android_vr` → `cobalt self-hosted instance` → `invidious-companion instance` → fail with structured error.

### 4.2 Circuit breaker + instance health state

Per-strategy (or per-instance) counters persisted in a local JSON state file (`~/.local/state/agentdl/health.json` — XDG):

```json
{
  "invidious:inv-nl.example": {"ok": 41, "fail": 3, "cooldown_until": 1767225600, "last_error": "HTTP 429"},
  "bgutil:http":               {"ok": 99, "fail": 0, "avg_ms": 210}
}
```

Rules: closed → open after N consecutive failures (e.g. 5) → half-open probe after cooldown (e.g. 300 s with jitter). Update on every attempt; a successful health-check probe halves cooldown. Libraries if we don't hand-roll: **tenacity** (retry with exponential backoff + jitter, wait_random_exponential) and **pybreaker** (CircuitBreaker); newer unified libs (pyresilience, 2026) package both. yt-dlp itself has `yt_dlp.utils.RetryManager` (signature verified: `RetryManager(_retries, _error_callback, **kwargs)`) used internally for known-error retries — AgentDL's own wrapper should not duplicate what `retries`/`extractor_retries` already do, and should only orchestrate *across strategies*.

**Exponential backoff + jitter (canonical form):**

```python
import random, time
def backoff(attempts, base=1.0, cap=60.0):
    for i in attempts:
        yield None
        time.sleep(min(cap, base * 2 ** i) * random.uniform(0.5, 1.5))
```

**Health-check caching** exactly as the brief suggests (track success rates per invidious instance in a local JSON state file) is validated by the Douyin v5 design (§1.6) — they went further with health *tiers* and per-(identity, endpoint) token buckets; AgentDL v1 should implement: JSON ledger + consecutive-failure breaker + weighted round-robin, and leave tiered LRU identity pools for later.

---

## 5. CLI design for agents

Convergent 2026 conventions (§1.9 sources + yt-dlp/cobalt study):

- **Every command accepts `--json`** and emits a stable envelope: `{"ok": bool, "data": ...}` / `{"ok": false, "error": {"code": "...", "message": "...", "retryable": bool, "context": {...}}}`. Machine-readable error **codes**, never prose-only (cobalt §1.2).
- **Semantic exit codes** (yt-dlp precedent): `0` success; `1` generic error; `2` usage error; `3` unsupported URL/no strategy; `4` all strategies failed; `5` verification failed; `100` max-downloads reached; `101` cancelled. Document them in `--help` (agents read `--help`).
- **Quiet by default when piped**; `--quiet`/`-q`; progress only to **stderr**, results only to **stdout**; `--log-level` + structured logs (structlog, per Douyin v5) so agents can tail diagnostics without polluting the JSON channel.
- **`--plan` / dry-run mode** (the "plan before write" idea from yt-dlp-mcp-server): prints what *would* be downloaded, with formats, sizes, output path — agents like to validate before acting.
- **Idempotency**: `--download-archive` default-on so repeated invocations are safe (gallery-dl/yt-dlp practice).
- **Distribution**: `pip install agentdl` + `pipx install agentdl` + `uv tool install agentdl`; single-file PyInstaller binaries per release (yt-dlp/gallery-dl precedent) — matters for agents that can't manage venvs. Pin Python ≥3.10 (yt-dlp still tests 3.10–3.15 + pypy).
- **Config file layout** (XDG, yt-dlp/gallery-dl style):
  ```
  ~/.config/agentdl/config.toml          # user config (strategies, defaults, proxies)
  ~/.config/agentdl/strategies.d/*.toml  # drop-in strategy overrides (yt-dlp plugins dir analog)
  ~/.local/state/agentdl/health.json     # circuit-breaker/instance ledger (XDG state)
  ~/.local/state/agentdl/archive.txt     # download archive (or sqlite)
  ~/.cache/agentdl/pot.json              # short-lived PO token cache (TTL ≤ 6h per bgutil)
  ```
- **Self-description**: `agentdl --version --json` → `{"version": ..., "yt_dlp": "2026.08.19", "ffmpeg": ..., "strategies": [...]}` (cobalt `GET /` precedent); optional MCP surface at parity with CLI (§1.6/1.8).

---

## 6. GitHub repo conventions (what a professional repo needs here)

Studied on yt-dlp / cobalt / bgutil / Douyin v5 / gallery-dl READMEs + CI:

- **README**: badges (release, PyPI, Docker, CI, CodeQL, Python min version, license, MCP-ready à la Douyin v5), 30-second quickstart, `--json` example *first* (agents and humans both), ethics/legal note (cobalt's "public content only; zero liability" language), supported-sites table with fallback-chain notes.
- **LICENSE**: **MIT** (per project requirement; note ecosystem contrast — yt-dlp Unlicense, cobalt AGPL-3.0 → no code reuse from cobalt).
- **CI (GitHub Actions)** — follow yt-dlp's proven split:
  - required `quick-test` on every PR: offline unit tests only (`pytest -m "not download"`), ruff/mypy, one OS+Python;
  - matrix `core` job: ubuntu+windows, 3.10–3.15+pypy;
  - separate **non-required, scheduled** `online-tests` workflow (cron 2×/day): `pytest -m download`, `--reruns 2 --reruns-delay 3.0`, uploads failures as artifacts, never blocks merges; mirror yt-dlp's `--flaky`/`--disallow-flaky` marker scheme so known-flaky platforms (YouTube!) self-skip in CI;
  - challenge-style workflow scoped to anti-bot code paths (bgutil/POT), like yt-dlp `challenge-tests.yml` with JS runtime matrix;
  - pinned action SHAs + `permissions: {}` + `cancel-in-progress` concurrency (yt-dlp hardening, copy it).
- **CONTRIBUTING.md** with developer instructions for adding a strategy (mirror yt-dlp's extractor authoring docs); **security policy** (PRIVATE vuln reporting); **CHANGELOG**; topic tags for discoverability (`yt-dlp-plugins`, `yt-dlp-pot-provider` precedent); CODEOWNERS; release automation (`build.yml`/`release.yml` pattern).

---

## 7. Recommended AgentDL architecture (synthesis)

```
                       ┌────────────────────────────────────────────────────────┐
                       │                      agentdl CLI / MCP                  │
                       │  download | plan | verify | doctor | health | cache     │
                       └───────────────▲────────────────────────────────────────┘
                                       │ structured call (dataclass/TypedDict)
                       ┌───────────────┴────────────────┐
                       │           ORCHESTRATOR          │   platform detect →
                       │  Job ledger · retries · budget  │   strategy chain resolve
                       └───┬────────────────────────────┘
                           │ ordered by weight, filtered by circuit breaker
        ┌──────────────────┼───────────────────────────┬──────────────────────┐
        ▼                  ▼                           ▼                      ▼
 ┌─────────────┐   ┌──────────────┐          ┌───────────────┐      ┌──────────────┐
 │ YtdlpStrategy│   │ CobaltStrategy│         │ InvidiousStrat │ ...  │ DouyinAPIStrat│
 │ (in-process  │   │ (HTTP client) │         │ (HTTP client)  │      │ (Evil0ctal   │
 │  YoutubeDL)  │   │  POST / JSON  │         │  instance pool │      │  self-host)  │
 └──────┬──────┘   └──────┬───────┘          └───────┬────────┘      └──────┬───────┘
        │  extractor_args per platform/client chain             │               │
        ▼                  ▼                                  ▼               ▼
   [bgutil POT sidecar :4416]              [instance health ledger]   [identity pool]

                           ┌────────────────────────────┐
                           │          VERIFIER           │
                           │ .part? → size? → ffprobe →  │
                           │ metadata match → sha256     │
                           └───────────────┬─────────────┘
                                           ▼
                     {"ok":true,"artifact":{...},"source":{...},"attempts":[...]}
```

**Recommended project layout** (fusion of yt-dlp plugin conventions + Douyin v5 `src/dtk` layout + cobalt monorepo docs layout):

```
agentdl/
├── src/agentdl/
│   ├── cli/                 # Typer app, --json envelope, exit codes, logging setup
│   ├── core/                # settings (pydantic-settings), errors, exit codes, logging
│   ├── orchestrator/        # job runner, platform detection, chain resolution, budgets
│   ├── registry/            # Strategy dataclass, weight-ordered registry, entry-point loading
│   ├── strategies/
│   │   ├── ytdlp_strategy.py      # in-process YoutubeDL embedding (§2) + extractor_args maps
│   │   ├── cobalt_strategy.py     # POST /, status-union handling, tunnel download
│   │   ├── invidious_strategy.py  # instance pool + health ledger
│   │   └── douyin_strategy.py     # Douyin/RedNote path via Evil0ctal API or yt-dlp
│   ├── resilience/          # backoff+jitter, CircuitBreaker, health.json ledger
│   ├── verify/              # ffprobe JSON, .part detection, sha256, archive
│   ├── output/              # envelope builders, --plan rendering
│   └── mcp/                 # optional MCP server over the same service layer
├── tests/
│   ├── unit/                # offline, marker "not download" — required CI
│   └── online/              # marker "download", scheduled workflow only, --flaky aware
├── docs/                    # api.md (envelope spec), strategies.md, mcp.md
├── .github/workflows/       # quick-test.yml (required) · core.yml · online.yml (cron) · release.yml
├── pyproject.toml           # uv/ruff/mypy/pytest; console_script agentdl
└── README.md                # badges, --json first, ethics note, MIT
```

---

## 8. Key risks & open questions for Task 3 (design)

1. **YouTube on datacenter IPs is the hardest problem** (PO tokens + IP reputation). Mitigation chain exists (bgutil sidecar + client rotation + cobalt fallback) but must be treated as *probabilistic*, with honest health metrics — never hard promises (bgutil's own caution).
2. **AGPL contagion**: cobalt is AGPL-3.0 — integrate as an external HTTP service only, zero code copying.
3. **yt-dlp API drift**: pin `yt-dlp>=2026.08.19` with a compat shim; watch the `extractor_args` contract (stable) vs internals (unstable). Consider a nightly "canary" online test against YouTube to detect breakage early.
4. **Token/secrets hygiene**: POT tokens short-lived & per-video; never persist beyond TTL (`~/.cache/agentdl/pot.json`, TTL ≤ 6 h).
5. **Repo host hedging** (gallery-dl → Codeberg): keep CI config portable.
6. Open question: MCP transport for v1 — Douyin v5 uses streamable-http; npm wrappers are stdio. Recommend stdio first (agent CLI integration is easiest), HTTP later.

---

## Appendix A — Source links

- yt-dlp: <https://github.com/yt-dlp/yt-dlp> · wiki (cloned): Plugin Development.md, PO Token Guide.md, Plugins.md · sample plugins: <https://github.com/yt-dlp/yt-dlp-sample-plugins> · rejected-plugins archive: <https://github.com/yt-dlp-archives/plugins>
- yt-dlp source inspected: `yt_dlp/YoutubeDL.py` (params doc), `yt_dlp/options.py` (CLI flags), `yt_dlp/__init__.py` (exit codes), `test/conftest.py`+`test/helper.py` (flaky markers), `devscripts/run_tests.py`, `.github/workflows/{core,quick-test,challenge-tests}.yml`
- cobalt: <https://github.com/imputnet/cobalt> + `docs/api.md` (AGPL-3.0)
- gallery-dl: <https://github.com/mikf/gallery-dl> (+ Codeberg migration notice)
- bgutil POT provider: <https://github.com/Brainicism/bgutil-ytdlp-pot-provider> (PyPI, Docker, port 4416)
- YouTube.js: <https://github.com/LuanRT/YouTube.js> · BgUtils: <https://github.com/LuanRT/BgUtils>
- Douyin/TikTok API: <https://github.com/Evil0ctal/Douyin_TikTok_Download_API> (v5 architecture)
- invidious-companion: <https://github.com/iv-org/invidious-companion>
- yt-trusted-session-generator: <https://github.com/iv-org/youtube-trusted-session-generator>
- MCP servers: <https://github.com/antonio-orionus/yt-dlp-mcp-server> · <https://github.com/kevinwatt/yt-dlp-mcp> · <https://github.com/Gtvar/yt-dlp-mcp> · npm `yt-dlp-mcp`
- Resilience libs: tenacity · pybreaker · pyresilience (<https://pyresilience.readthedocs.io>)
- Agent-CLI conventions: apidog "Top CLI tools for AI agents" (2026-09) · BlindPay CLI · ai-native-cli spec (skills.rest)
