# YouTube Cloud-IP Bypass — Fresh Research Addendum (Task 1-a)

**Task ID:** 1-a · **Date:** 2026-10-03 · **Method:** fresh web searches (~24 queries) + primary-source fetches + **new live tests from this datacenter sandbox (Alibaba Cloud IP, same class as user's server)**
**Complements:** `research/youtube_methods.md` (task 2-a — deep baseline: yt-dlp/bgutil/cobalt/invidious-companion/IP-egress physics). This addendum adds only NEW findings + verified-dead confirmations. RESEARCH ONLY — no code changed.

---

## 0. Headline: one NEW method verified END-TO-END from a datacenter IP today

### loader.to free AJAX API (server-side farm; keyless, cookieless) — ✅ VERIFIED WORKING

The `loader.to` downloader site exposes a working JSON API whose **backend farm (residential/clean IPs) touches YouTube for you**. Tested from this flagged datacenter IP, no key, no cookies, no browser:

```
# 1) Submit job  (formats verified: 240, 360, 480, 720, 1080, 1440, mp3, m4a, wav, flac)
GET https://loader.to/ajax/download.php?format=1080&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DjNQXAC9IVRw
→ {"success":true,"id":"v2_stream_…","progress_url":"https://lto2.affadaffa.com/api/progress?id=v2_stream_…"}

# 2) Poll until progress==1000 (~30-45 s), then read download_url
GET https://lto2.affadaffa.com/api/progress?id=v2_stream_…
→ {"success":1,"progress":1000,"download_url":"https://travis40.savenow.to/api/v2/download/…"}

# 3) GET download_url → valid MP4 (verified: ISO MP4, ffprobe duration 19.1 s = correct)
```

- Bad format → `{"message":"Unknown format.","errors":{"format":["Unknown format."]}}` (used to enumerate the format list).
- Progress payload self-identifies the commercial tier: *"If you want your application to use our API contact us: sp_golubev@protonmail.com or visit https://video-download-api.com/"*.
- **Official/commercial sibling: `video-download-api.com`** — same protocol (`p.savenow.to/ajax/download.php?url=…&format=mp3&apikey=…`, poll `/ajax/progress.php`; also `/api/v2/download`, `/ajax/subtitles` for VTT/SRT, `/api/button/` embeds). "Free-start API key" for testing, wallet credit for production. This is the sanctioned path if the free endpoint starts gating.
- Caveats: output is a single muxed stream (quality capped at what their farm offers; no per-format adaptive choice), rate limits unpublished (keyless = gray-zone use of the site's own backend; throttle and cache results), hosts (`lto*.affadaffa.com`, `*.savenow.to`) may change — resolve at runtime, keep timeouts + validator. **This is the strongest "no infra" fallback tier found.**

### Re-verified dead (matches user's tests)
- `p.oceansaver.in/ajax/download.php` (ddownr): **empty response** re-confirmed today (loader.to is a different, live backend).
- `api.cobalt.tools`: `{"status":"error","error":{"code":"error.api.auth.jwt.missing"}}` re-confirmed today.
- Public Invidious / Piped / raw innertube / full client rotation: no change (see task 2-a report §2, §7, §8, §11).

---

## 1. TOP 5 ranked actionable approaches (for the fallback chain)

### #1 — loader.to AJAX API (keyless) → video-download-api.com (free-start key) as the paid twin
**(a) Tool:** loader.to public endpoint; commercial twin video-download-api.com ("loader-compatible hosted endpoints"). No GitHub repo; REST only.
**(b) How it works:** their server-side download farm resolves the video (residential/clean egress, their own client/POT plumbing), transcodes/streams, and hands you a finished file URL from `*.savenow.to`. Your IP only talks to loader.to/savenow, never to youtube/googlevideo → the IP-reputation playability gate that kills yt-dlp from datacenter IPs never sees you.
**(c) Auth:** none for loader.to (keyless today); `apikey` required at video-download-api.com (free test key available).
**(d) Why it works where yt-dlp fails:** the YouTube touch happens from their IPs (the same physics that makes cobalt self-host/invidious-companion work — but zero infra on your side).
**(e) Usage:** see §0 curl sequence. Pseudo-pipeline: `submit → poll (2–5 s interval, ≤90 s budget) → download → verify (magic bytes + ffprobe)`. Cache by videoId+format.

### #2 — Self-hosted Cobalt on a clean-IP host (+ `imputnet/yt-session-generator`)
**(a)** `github.com/imputnet/cobalt` (docs: `docs.cobalt.video`), session server `github.com/imputnet/yt-session-generator`.
**(b)** POST JSON `{"url":"https://youtu.be/ID"}` → `tunnel` URL; cobalt's backend IP does the YouTube fetch and proxies the bytes. Optional `YOUTUBE_SESSION_SERVER` auto-mints `po_token`+`visitor_data`.
**(c)** No auth for your own instance (add JWT/Turnstile only if exposed publicly).
**(d)** Same "cleaner IP touches YouTube" physics; full control of rate limits; streams originate from cobalt host.
**(e)**
```bash
docker run -d -p 8080:8080 ghcr.io/imputnet/yt-session-generator:webserver   # on SAME public IP as cobalt
# cobalt compose: API_URL=https://cb.example.com  YOUTUBE_SESSION_SERVER=http://yt-session:8080
curl -s -X POST https://cb.example.com/ -H 'Accept: application/json' -H 'Content-Type: application/json' \
  -d '{"url":"https://youtu.be/jNQXAC9IVRw","videoQuality":"1080","youtubeVideoCodec":"h264"}'
```
Note: cobalt dev quiet since ~2026-04; still functional per docs. Bandwidth = your host's (it tunnels bytes).

### #3 — Egress re-route: Cloudflare WARP sidecar + yt-dlp(+bgutil) behind it
**(a)** docker `caomingjun/warp` (or warp-cli) + yt-dlp `--proxy socks5://127.0.0.1:1080`.
**(b)** All YouTube requests egress via Cloudflare IPs (better reputation than raw datacenter ranges); POT stack (bgutil :4416) runs locally.
**(c)** No auth (free WARP).
**(d)** Attacks the actual root cause — IP reputation. Task 2-a + upstream corroboration: gate is IP-based; changing egress is the class of fix that actually works. Paid residential/ISP proxies (`socks5h://user:pass@host:port`) are the higher-reliability paid variant; free SOCKS5 lists = last-resort tier (0.5–2 % pass rate).
**(e)**
```bash
docker run -d --name warp -p 127.0.0.1:1080:1080 caomingjun/warp
yt-dlp --proxy socks5://127.0.0.1:1080 --js-runtimes node \
  --extractor-args "youtube:player_client=mweb,tv,web_safari" "https://youtu.be/VIDEO_ID"
```

### #4 — yt-dlp + POT provider stack, incl. NEW provider intel (tier-2, mildly-flagged IPs only)
**(a)** `Brainicism/bgutil-ytdlp-pot-provider` (node/deno/docker), `jim60105/bgutil-ytdlp-pot-provider-rs` (single Rust binary, crates.io Mar 2026), `coletdjnz/yt-dlp-getpot-wpc` (real-Chromium WebPO minter).
**(b)** Mints guest WebPO tokens via BotGuard without login; plugin feeds yt-dlp.
**(c)** No auth. **(d)** Honest limit (VERIFIED twice now): on hard-flagged datacenter IPs the playability gate fires *before* token checks → still `LOGIN_REQUIRED`. Use for GVS-403 fixes + mildly-flagged IPs + as the companion to #3.
**NEW datapoint:** yt-dlp issue **#17404 (Aug 2026)**: user reports `yt-dlp-getpot-wpc` resolved persistent 403s where other means failed (browser-run BotGuard yields stronger tokens). Keep wpc as the POT fallback when bgutil-sourced tokens don't clear a gate.
**(e)**
```bash
python3 -m pip install -U bgutil-ytdlp-pot-provider          # plugin
docker run -d -p 127.0.0.1:4416:4416 brainicism/bgutil-ytdlp-pot-provider
yt-dlp --js-runtimes node --extractor-args "youtube:player_client=mweb;fetch_pot=always" URL
# wpc fallback:
python3 -m pip install -U yt-dlp-getpot-wpc && yt-dlp \
  --extractor-args "youtubepot-wpc:browser_path=/usr/bin/chromium" URL
```

### #5 — Invidious-companion standalone self-host (clean IP / IPv6 rotation)
**(a)** `github.com/iv-org/invidious-companion` (Deno; active, Sep 2026).
**(b)** Works WITHOUT full Invidious: `POST /companion/youtubei/v1/player {"videoId":…}` → player JSON with **decrypted videoplayback URLs**; `GET /companion/latest_version?id=…&itag=18&local=true` → proxied file. Bearer auth = `invidious_companion_key`.
**(c)** Bearer secret you set; no Google account.
**(d)** Companion's YouTube.js fork + session handling does the YouTube touch; point it at a clean IP (per-request IPv6 /64 rotation is the documented self-hoster meta-trick).
**(e)**
```bash
docker run -d -p 127.0.0.1:8282:8282 ghcr.io/iv-org/invidious-companion:latest \
  -e INVIDIOUS_COMPANION_KEY=changeme
curl -s http://127.0.0.1:8282/companion/youtubei/v1/player \
  -H 'Authorization: Bearer changeme' -H 'Content-Type: application/json' \
  -d '{"videoId":"jNQXAC9IVRw"}'
```
Caveat: inherits the same IP-reputation wall if *its* egress is flagged → pair with #3-style clean egress.

---

## 2. NEW capability worth wiring in: yt-dlp-ytse (SABR/UMP formats)

- **`coletdjnz/yt-dlp-ytse`** (PyPI `yt-dlp-ytse` 0.4.3; needs yt-dlp ≥ 2025.01.26): experimental plugin enabling **UMP** (`youtube:formats=ump`) and **SABR** (`youtube:formats=sabr`) streaming downloads — increasingly the ONLY formats `web`/newer clients return (yt-dlp #12482). Uses `LuanRT/googlevideo` UMP/SABR protocol. Livestreams incl. `--live-from-start` supported; no `-N`/`--download-sections`/resume.
- **VERIFIED today from this datacenter IP: it does NOT bypass the bot-check** — with `formats=ump` the player response is still `LOGIN_REQUIRED` (gate precedes format retrieval, as expected). Its value = future-proofing quality tiers once the gate is passed via #2/#3/#5 (web client is SABR-only now).
```bash
python3 -m pip install -U yt-dlp-ytse
yt-dlp --extractor-args "youtube:formats=ump" -S proto:ump URL
```

## 3. Fresh client-policy intel (from ytcui-dl v2 README, Aug 2026, + yt-dlp master `_base.py`)

- **`VISIONOS` client: no PO token required AND no byte-cap on its format URLs** (author pulled a 679 MB 2160p60 stream end-to-end). Keep `visionos` first in every rotation.
- **`ANDROID_VR`/`ANDROID`/`IOS`: since ~2026-08-17 the CDN byte-caps their URLs to ~1 minute of stream (~3 MB audio / ~10–12 MB 1080p) before 403** even when the player response looks fine (yt-dlp master comment confirms the android_vr break at clientVersion 1.65.10). Don't count on them for full files anymore.
- `ANDROID` pinned to 20.10.38 returns `LOGIN_REQUIRED` **without `visitorData`** — bootstrap/visitor-data handling is load-bearing.
- **Probabilistic gating is real:** user's 1/12 `tv` success + independent write-up ("same link fails then works twenty minutes later") → cheap multi-attempt retry across clients has non-zero yield; treat as bonus, never as a tier.
- `MilkmanAbi/ytcui-dl` (C++17, 14★, active Aug 2026): standalone client-chain downloader (`VISIONOS→ANDROID_VR→ANDROID→IOS` + SABR gate + bgutil POT passthrough) — useful reference implementation; same physics as yt-dlp (no gate bypass).

## 4. Confirmed-dead / do-not-build list (Oct 2026)

| Approach | Status |
|---|---|
| Public Invidious instances | dead/anti-bot'd (5 left, all walled) — unchanged |
| Piped public instances | dead for streams (`SignInConfirmNotBotException` upstream) |
| Public Cobalt (`api.cobalt.tools`, canine.tools, instances.cobalt.best) | JWT/anti-bot/cert — re-verified today |
| ddownr `p.oceansaver.in` ajax | empty response — re-verified today (loader.to endpoint is the live sibling) |
| mp3youtube.cc | "Bad request" (user) |
| Raw innertube / client rotation alone | dead (LOGIN_REQUIRED; now additionally byte-capped URLs on android/ios/android_vr) |
| OAuth login in yt-dlp | dead (cookies only; account-ban risk — throwaway only) |

## 5. Recommended chain update for the downloader system

`preflight → yt-dlp (visionos-first, +ejs, bgutil :4416) → [NEW] loader.to keyless API → cobalt self-host if provisioned → WARP-sidecar retry of tier 1 → wpc POT fallback → invidious-companion on clean egress → paid residential proxy → video-download-api.com (paid key) as final guarantees`. Validate every artifact (magic bytes, ffprobe, size); ledger-reorder tiers from observed success.

## 6. Sources (accessed 2026-10-03)
- Live tests in this sandbox: loader.to e2e (720p file verified, 1080/mp3/1440/m4a/wav/flac accepted, 240/360/480 valid), ddownr empty, cobalt JWT error, yt-dlp 2026.08.19 + `ytse` 0.4.3 `formats=ump` → LOGIN_REQUIRED, `visionos` single-client → LOGIN_REQUIRED.
- PyPI `yt-dlp-ytse` 0.4.3 README; `github.com/coletdjnz/yt-dlp-ytse` (+ issues page).
- `MilkmanAbi/ytcui-dl` README (client byte-caps, VISIONOS notes, POT via bgutil API).
- yt-dlp master `yt_dlp/extractor/youtube/_base.py` (client policies, android_vr 2026-08-17 comment).
- video-download-api.com (API protocol docs, endpoints, free-start key).
- yt-dlp issue #17404 (wpc resolves persistent 403s, Aug 2026); bgutil issue #37 (closed; POT ≠ IP-gate bypass).
- tbd.yt blog (Jul 31, 2026) + forum.gnoppix.org (Jan 18, 2026): consumer-grade corroboration — non-deterministic gating, browser "embedded trick" irrelevant to servers, web_safari spoof = same class as client rotation.
- GitHub topics `yt-dlp-pot-provider` (no new major providers beyond bgutil/bgutil-rs/wpc/Heroku).
- Prior baseline: `research/youtube_methods.md` (task 2-a) and `research/raw/*`.
