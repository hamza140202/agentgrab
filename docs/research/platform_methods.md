# Platform Cookieless Download Methods — AgentDL Research (Task 2-b)

**Date:** 2026-10-03
**Researcher:** platform-research agent (Task 2-b)
**Test environment:** Alibaba Cloud Hong Kong datacenter IP (`47.57.232.232`, AS45102) — genuine datacenter IP.
**Tools verified:** yt-dlp 2026.08.19 (+ curl_cffi 0.16.3 impersonation), curl, ffmpeg.

> Legend: ✅ = live-verified from the datacenter IP in this environment on 2026-10-03.
> ⚠️ = partially verified / stale sources. ❌ = verified broken. **UNVERIFIED** = not tested, reported from docs/community.

---

## 1. TikTok

### (a) Primary method: yt-dlp native — ❌ BROKEN from datacenter IPs
- `yt-dlp "https://www.tiktok.com/@user/video/ID"` → `[TikTok] ...: Unexpected response from webpage request`.
- The TikTok webpage host returns **HTTP 302 → challenge/captcha page** for datacenter ASNs (verified with plain curl: `HTTP 302`, 136-byte body).
- Installing `curl_cffi` (browser TLS impersonation, which yt-dlp's TikTok extractor requests) did **NOT** fix it. Block is IP-based, not fingerprint-based.
- Internals (from `yt_dlp/extractor/tiktok.py`): extractor sets random `odin_tt` cookie, copies `sid_tt` if present (login), and has a JS-challenge cookie solver (`_solve_challenge_and_set_cookies`). None of this defeats the datacenter-IP block.
- TikTok oEmbed (`https://www.tiktok.com/oembed?url=...`) → 302 (via "TLB" load balancer) — unusable from DC IPs. ✅❌
- **Note:** `cookies` of ANY kind (even anonymous fresh ones) do not help here; the web page itself is walled by IP reputation.

### (b) Primary fallback: tikwm.com public API — ✅ WORKS
The most reliable cookieless method. No auth, no cookies.

**Endpoint:**
```
GET https://www.tikwm.com/api/?url=<urlencoded TikTok URL>&hd=1
```
- `url` accepts full `https://www.tiktok.com/@user/video/ID` URLs. Short `vt.tiktok.com` links: resolve the redirect client-side first (tikwm does follow them server-side, but we could not obtain a live short code to verify — **UNVERIFIED for short links**).
- `hd=1` requests the HD no-watermark rendition (adds `hdplay` when available).

**Request headers:** none strictly required (works with plain curl, default UA). Sending a browser UA is harmless.

**Response shape (verified live, code 0 = success):**
```json
{
  "code": 0,                  // 0 = success; -1 = error (see msg)
  "msg": "success",
  "processed_time": 0.49,
  "data": {
    "id": "6718335390845095173",
    "region": "US",
    "title": "...",
    "duration": 10,
    "play":    "https://v16m.tiktokcdn-us.com/.../?...",   // NO-WATERMARK mp4 (signed, expires)
    "hdplay":  "...",            // HD no-watermark (absent unless hd=1 / only for some videos)
    "wmplay":  "https://v16m.tiktokcdn-us.com/...",        // WATERMARKED mp4
    "size": 2953029, "wm_size": 0,
    "music":  "https://v16-ies-music.tiktokcdn-us.com/...",// original audio mp3
    "music_info": { "id": "...", "title": "original sound - ...", "author": "...", "original": true, "duration": 10, "play": "..." },
    "cover": "...", "origin_cover": "...", "ai_dynamic_cover": "...",
    "play_count": 159429, "digg_count": 35181, "comment_count": 5717, "share_count": 1497,
    "create_time": 1564234358,
    "author": { "id": "...", "unique_id": "scout2015", "nickname": "Scout, Suki & Stella", "avatar": "..." },
    "images": [...]   // photo/slideshow posts: array of image CDN URLs (NOT live-verified — UNVERIFIED)
  }
}
```
**Field path to video URL:** `data.hdplay` (best, if non-empty) → else `data.play` (no watermark) → `data.wmplay` (watermarked). Audio: `data.music`. Photo posts: `data.images[*]` (**UNVERIFIED**).

**Watermark:** `play`/`hdplay` are watermark-free; `wmplay` is watermarked. ✅
**CDN URLs are signed and short-lived** (hours) — download immediately after resolution.

**Rate limits:** the widely cited policy is **1 request/second** (third-party integrations ship "TikWM public API, 1 request/second" as their backend). ✅ Live burst test: 5 requests ~0.3 s apart all returned `code 0` — no hard enforcement observed at low volume, but implement ≥1 s pacing to stay safe. Error code on abuse is `-1` with a free-API-limit message.
**Other public TikTok APIs:** musicallydown / dlpify / snaptik-style sites — HTML scrapers, no stable JSON, frequently captcha'd — **UNVERIFIED**, avoid as primary.

### Gotchas
- Geo-mismatch: tikwm resolves region and sometimes returns US-region CDN URLs; works from HK datacenter. ✅
- Some videos have `hdplay` absent → use `play`.
- `wm_size: 0` observed even when `wmplay` is non-empty; don't trust `wm_size`.

---

## 2. Instagram

### (a) yt-dlp native — ❌ login required from datacenter IPs
- Live test: `[Instagram] ...: Instagram sent an empty media response. ... use --cookies ...` on a public post (`/p/BgFFfOgg6ig/`).
- yt-dlp's anonymous flow (`?__a=1&__d=dis` web profile API) is dead for DC IPs; extractor source has explicit branches for "rate-limit for accessing posts anonymously" and login redirects.
- Posts pages return HTTP 200 but only a ~640 KB JS shell (no `scontent` media URLs, no og:video) — content is JS-gated. Profile pages 302 → `/accounts/login/`. ✅❌

### (b) Anonymous endpoints tested — all fail from datacenter IP
| Method | Result |
|---|---|
| `https://www.instagram.com/p/<code>/embed/captioned/` | HTTP 200 but JS shell; **no server-side media**, no `EmbeddedMediaImage`, no `og:video` (even for a 2019 public post) ✅❌ |
| Googlebot UA on post page | Same 640 KB shell, 0 media URLs — UA spoof does not help ✅❌ |
| `https://i.instagram.com/api/v1/media/<mid>/info/` with Android app UA + `X-IG-App-ID: 936619743392459` | HTTP 403 `{"message":"login_required","logout_reason":33}` ✅❌ |
| `https://www.instagram.com/api/v1/media/<mid>/info/` (web API, same headers) | HTTP 302 → login ✅❌ |
| Post code → media id: `int.from_bytes(base64.urlsafe_b64decode(code + "=="), "big")` (works: `BgFFfOgg6ig` → `432703441977010728`) | conversion formula itself is fine |
| InstaFix instances `www.ddinstagram.com`, `d.ddinstagram.com` | connection timeout ✅❌ |
| `www.kkinstagram.com` | HTTP 504 ✅❌ |
| imginn.com | HTTP 403 ✅❌ |
| picuki.com | 301 away ✅❌ |

InstaFix upstream (github.com/Wikidepia/InstaFix) has ongoing "posts failing to load" issues (issue #26, activity Apr 2026).

### (c) Remaining options
- **Self-host InstaFix** — cookieless for low-res media; high-res requires a session cookie (**UNVERIFIED** cookieless quality).
- **Commercial resolver services / HelloTik-style multi-platform parsers** — **UNVERIFIED**, likely rate-limited or paid.
- **Practical verdict (Oct 2026):** Instagram is the weakest platform for cookieless datacenter use. Any public-post download without login needs either (1) residential proxies + scraping `__a=1`-style flows, or (2) a cookie/credential source — both out of scope. Recommend: attempt yt-dlp anonymous (rarely works), then fail fast with a clear "IG requires auth/proxy" error.

### Gotchas
- Even the oEmbed API (`api.instagram.com/oembed`) requires an app token (deprecated 2020+) — no anonymous metadata either.
- Stories/highlights/reels-audio pages are strictly login-only.

---

## 3. Reddit

### (a) yt-dlp native / reddit JSON API — ❌ IP-blocked (ASN-level)
- `https://www.reddit.com/r/<sub>/comments/ID/.json`, `https://api.reddit.com/...`, `https://old.reddit.com/...`, `https://oauth.reddit.com/...` → **HTTP 403 "Blocked"** (190 KB block page) from Alibaba-HK datacenter IP. ✅❌
- Retested with full browser UA, `Accept: application/json`, and with curl_cffi `chrome`/`safari184`/`firefox133` TLS impersonation → still 403. **Block is by IP/ASN, not TLS fingerprint.**
- `yt-dlp "https://v.redd.it/ID"` → generic extractor follows redirect to `www.reddit.com` → 403. ❌
- Fallback mirrors also dead for us:
  - **PullPush.io** (`api.pullpush.io/reddit/search/submission/?ids=`) → HTTP 429 with explicit message: *"This website does not provide free scraping resources for agents."* ✅❌
  - **rxddit.com** → serves cached subreddit pages but post resolution returns meta-refresh: *"Reddit blocked the request. Reddit is actively preventing this service from working with recent api changes"* (refs r/modnews post 1tq9vxo on anti-scraping). ✅❌
  - **redlib/libreddit instances** — probed 7 public instances: 1×200 (tiny page), 1×429, 2×403, 2×502, 1×timeout. Effectively unusable from DC IPs. ✅❌

### (b) Working fallback chain — ✅ Arctic Shift metadata + v.redd.it direct CDN
**Step 1 — metadata (works, no auth):**
```
GET https://arctic-shift.photon-reddit.com/api/posts/ids?ids=t3_1wwlchp
GET https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=videos&limit=100&sort=desc
Headers: User-Agent: anything non-generic (e.g. "AgentDL/1.0")
```
- Returns full submission JSON (`data: [...]`). Key fields:
  - `data[0].media.reddit_video.fallback_url` → e.g. `https://v.redd.it/<id>/CMAF_720.mp4?source=fallback`
  - `data[0].media.reddit_video.hls_url` / `.dash_url` (signed query `a=...` — but see below, plain URLs work too)
  - `data[0].media.reddit_video.has_audio`, `duration`, `width`, `height`
  - `url_overridden_by_dest` / `url` (crossposts: `crosspost_parent_list[0].media...`)
  - `preview.images[0].source.url` (preview.redd.it proxy URL)
- Arctic Shift index has slight ingest lag (fresh posts may be missing). No observed rate limit at research volume (hundreds of requests OK). ✅

**Step 2 — media download (works, no signature, no cookies):** ✅
Reddit changed renditions in 2025-26: **old `DASH_*.mp4` files are dead (403)**; new **CMAF** renditions are open:
```
https://v.redd.it/<id>/HLSPlaylist.m3u8      → 200 application/x-mpegurl   (master playlist)
https://v.redd.it/<id>/DASHPlaylist.mpd      → 200 application/dash+xml
https://v.redd.it/<id>/CMAF_720.mp4          → 200 video/mp4   (VIDEO-ONLY track)
https://v.redd.it/<id>/CMAF_480.mp4 / CMAF_360.mp4 / CMAF_220.mp4 → 200
https://v.redd.it/<id>/CMAF_AUDIO_128.mp4    → 200 video/mp4   (AUDIO-ONLY track)
https://v.redd.it/<id>/CMAF_AUDIO_64.mp4     → 200
https://v.redd.it/<id>/DASH_720.mp4          → 403  (DEAD)
https://v.redd.it/<id>/DASH_96.mp4, DASH_AUDIO_128.mp4, DASH_AUDIO_64.mp4 → 403 (DEAD)
```
- Which CMAF_* resolutions exist varies per video (max is whatever `fallback_url` says, commonly 720). **Enumerate via `HLSPlaylist.m3u8`** rather than guessing: it lists `CMAF_220/270/360/480/720.m3u8` + `CMAF_AUDIO_64/128.m3u8`.
- HLS master verified via yt-dlp: `yt-dlp -f "bv*+ba/b" "https://v.redd.it/<id>/HLSPlaylist.m3u8"` → works, lists video-only + audio-only formats, ffmpeg muxes automatically. ✅
- Direct-file route: download `CMAF_<max>.mp4` + `CMAF_AUDIO_128.mp4` then `ffmpeg -i video -i audio -c copy out.mp4`. **Audio is a separate track — always merge or you get silent video.**
- Images: `https://i.redd.it/<hash>.jpeg` → HTTP 200 from DC IP ✅. `preview.redd.it` URLs (from Arctic Shift `preview` field) should also work (**UNVERIFIED with a real URL**; fake hash gives 403 as expected).

### Gotchas
- `www.reddit.com` JSON + `oauth.reddit.com` + `old.reddit.com` = all IP-blocked; do NOT build the primary path on them.
- PullPush explicitly anti-agent; rxddit upstream broken; redlib instances rate-limited — don't rely on any HTML mirror.
- v.redd.it/i.redd.it CDN is NOT blocked — this is the key asymmetry to exploit.
- Some posts are link posts (YouTube etc.) — check `post_hint`/`domain` before treating as native video.

---

## 4. X / Twitter

### (a) Primary method: yt-dlp native — ✅ WORKS from datacenter IPs (best platform)
```
yt-dlp "https://x.com/<user>/status/<ID>"
```
- Live verified: extractor fetches **guest token** (`POST https://api.x.com/1.1/guest/activate.json` with the public web bearer token — verified returning `{"guest_token":"..."}` ✅), then GraphQL `TweetResultByRestId` (`https://x.com/i/api/graphql/2ICDjqPd81tulZcYrtpTuQ/TweetResultByRestId`), then lists HLS + progressive formats up to 720p (and higher on some posts). No cookies, no login. ✅
- Bearer token used by the web client (public, constant): `AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA`
- Fallback chain inside yt-dlp when GraphQL 429s: **syndication endpoint** (see below). Can force with `--extractor-args "twitter:api=syndication"` (also `legacy`/`graphql`).

### (b) Fallback 1: fxtwitter API — ✅ WORKS
```
GET https://api.fxtwitter.com/status/<ID>
```
**Response shape (verified):**
```json
{
  "code": 200,             // 200 ok; 404 = tweet not found (shape: {"code":404,"message":"NOT_FOUND","tweet":null})
  "message": "OK",
  "tweet": {
    "id": "...", "text": "...", "raw_text": "...", "created_at": "...", "created_timestamp": "...",
    "author": { "name": "...", "screen_name": "BTS_twt", ... },
    "likes": ..., "retweets": ..., "replies": ..., "bookmarks": ..., "views": ...,
    "media": {
      "all": [...],
      "videos": [ { "url": "https://video.twimg.com/ext_tw_video/<mid>/pu/vid/720x960/xxx.mp4?tag=10",
                    "format": "video/mp4", "type": "video" } ],
      "photos": [ ... ]
    },
    "twitter_card": "...", "color": "..."
  }
}
```
- **Field path:** `tweet.media.videos[*].url` (direct mp4 on `video.twimg.com`); photos: `tweet.media.photos[*].url`.
- No auth, no cookies; plain UA fine; not Cloudflare-challenged. Service internally healthy (`GET /ping` → 200 with user payload ✅).

### (c) Fallback 2: Twitter syndication API — ✅ WORKS (with correct token + UA)
```
GET https://cdn.syndication.twimg.com/tweet-result?id=<ID>&token=<TOKEN>&lang=en
Headers: User-Agent: Googlebot        ← REQUIRED; default UA returns an HTML "X / ?" page (404-ish)
```
**Token formula** (from yt-dlp `twitter.py`, mirrors the JS in X's embed widget):
```
token = ((tweet_id / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, '')
# Python: js_number_to_string((int(id)/1e15)*math.pi, 36) then strip chars '0' and '.'
```
(NB: must emulate JS float→base36 exactly — use yt-dlp's `yt_dlp.jsinterp.js_number_to_string`, not naive base36.)

**Response shape (verified, BTS video tweet 1256648835272605697):**
```json
{ "__typename": "Tweet", "text": "...", "created_at": "2020-05-02T...", "favorite_count": ...,
  "user": { "screen_name": "BTS_twt", ... },
  "mediaDetails": [ { "type": "video", "aspect_ratio": [...], "duration_millis": ...,
      "video_info": { "variants": [
        { "content_type": "application/x-mpegURL", "url": "https://video.twimg.com/.../pu/pl/....m3u8?tag=10" },
        { "content_type": "video/mp4", "bitrate": 632000,  "url": ".../vid/320x426/....mp4?tag=10" },
        { "content_type": "video/mp4", "bitrate": 2176000, "url": ".../vid/720x960/....mp4?tag=10" } ] } } ] }
```
- **Field path:** `mediaDetails[*].video_info.variants[*].url` — pick highest `bitrate` mp4 (or the m3u8).
- Note: syndication media is sometimes capped at lower max-bitrate than GraphQL; also unavailable for age-gated/protected tweets.
- 404 (HTML page) = deleted/never-existed tweet.

### (d) Other
- `video.twimg.com/...` direct CDN: **no auth needed**, downloads fine from DC IP ✅ (10 MB file verified).
- **vxtwitter (`api.vxtwitter.com`)**: ❌ Cloudflare JS challenge ("Just a moment…") for non-browser clients, even with chrome TLS impersonation. Avoid for CLI/agent use.
- nitter instances: poast/privacyredirect/space/lightbrd all dead or 403 from DC IP ✅❌.

### Gotchas
- Deleted-tweet detection: fxtwitter `code:404` / syndication HTML page / yt-dlp `ExtractorError`.
- GraphQL `features` blob changes over time — prefer yt-dlp (maintained) over hand-rolled GraphQL calls.
- Rate limits: guest-token GraphQL throttles aggressively under volume; yt-dlp auto-falls back to syndication on 429. Pace requests, reuse guest tokens briefly.

---

## 5. Douyin

### (a) yt-dlp native — ❌ needs fresh cookies (not necessarily logged in)
- Live test: `yt-dlp "https://www.douyin.com/video/7126745726494821640"` → `[Douyin] ...: Fresh cookies (not necessarily logged in) are needed`.
- yt-dlp's Douyin path hits `https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=...` which requires: `ttwid` cookie (anonymous device token) + signed query (`a_bogus` / newer `X-Gnarly` per evil0ctal docs; older `X-Bogus`) + often `msToken`.
- `ttwid` anonymous minting endpoint used by old tooling — `POST https://ttwid.bytedance.com/ttwid/bridge/register/` → **HTTP 404 now** ✅❌.
- `douyin.com/` homepage from DC IP → 2.4 KB JS bootstrap shell, **no ttwid Set-Cookie** ✅❌.

### (b) Anonymous endpoints tested — all dead
| Method | Result |
|---|---|
| Legacy item API `https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids=<id>` | HTTP 200 with **empty body** (dead) ✅❌ |
| Mobile share page `https://www.iesdouyin.com/share/video/<id>` (iPhone UA) | 200 but 32 KB JS/argus-csp bootstrap; **no ROUTE_DATA / playAddr server-side** ✅❌ |
| tikwm douyin support | `{"code":-1,"msg":"Url parsing is failed!..."}` — **tikwm is TikTok-only, does NOT support douyin** ✅❌ |

### (c) evil0ctal/Douyin_TikTok_Download_API — public instance now paid
- **`api.douyin.wtf` public instance: requires API key now.** Every endpoint → HTTP 401 `{"error":{"code":"UNAUTHENTICATED","message":"Send a valid API key in the X-API-Key header..."}}` ✅❌ (old path `/api/hybrid/video_data` → 404; new surface is `/api/v1/{platform}/video`, `/api/v1/parse`, `/api/v1/{platform}/user/...` per its `/openapi.json`).
- **Self-hosting (docker):** README states v4 requires you to **paste a browser Douyin cookie** into `config.yaml` ("v4 has no identity pool, and the cookie..."); **v5 (current main)** runs an **identity pool that mints guest identities via a headless browser** and rotates them ("a headless browser mints guest identities, and the pool tops itself up"). So self-host is viable *without user login*, but requires headless-browser infrastructure and includes its own pure-Python signing (`a_bogus`, `X-Bogus`, `X-Gnarly`, `X-Dynosaur`).
- This is the strongest Douyin option for AgentDL **if** we accept a Docker sidecar. Exact response fields (v5): `/api/v1/douyin/video?url=...` returns the aweme detail (video.play_addr, bit_rate[], image Gallery for slideshows) — **UNVERIFIED** without an API key/self-host run.

### (d) Direct web API (what full scraping needs) — ❌ not cookieless in practice
`GET https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=<id>&...&a_bogus=<sig>`
- Needs: valid `ttwid` + `msToken` cookies, full browser header set, and a valid signature over the query string: historically `X-Bogus` (2023) → `a_bogus` (2024-25) → `X-Gnarly`/`X-Dynosaur` (2025-26). Open-source implementations exist (MediaCrawler `media_platform/douyin/client.py`; evil0ctal signing module) but all assume a minted identity; from a clean DC IP with no cookies the endpoint rejects. ⚠️/❌

### (e) Verdict & recommendations
- No simple public HTTP API works cookieless from DC IPs (as of Oct 2026).
- Options ranked: (1) **self-host evil0ctal v5 docker** (headless-browser identity pool; no user login) — recommended integration path; (2) implement `a_bogus`/`X-Gnarly` signing + anonymous `ttwid` acquisition — brittle, research-heavy (**UNVERIFIED** whether ttwid can still be minted anonymously at all); (3) third-party MCP/parsers (e.g., `wanyi-watermark` on PyPI, HelloTik) — **UNVERIFIED**, untrusted.
- Gotchas: watermarked vs raw — aweme `play_addr` (no watermark, via CDN rewrite) vs `download_addr` (watermark); slideshows = `images[]`; CN-only CDN sometimes requires Referer `https://www.douyin.com/`.

---

## 6. RedNote / Xiaohongshu

### (a) yt-dlp native (XiaoHongShuIE) — extractor exists; page fetch blocked from DC IP
Extractor source (verified, `yt_dlp/extractor/xiaohongshu.py`):
- `_VALID_URL`: `https?://www.xiaohongshu.com/(?:explore|discovery/item)/(?P<id>[\da-f]+)` (24-hex-char id; newer share links carry `?xsec_token=...&xsec_source=` which the extractor accepts in the URL).
- Flow: download webpage → `window.__INITIAL_STATE__` (after `js_to_json`) → `note.noteDetailMap.<id>.note` →
  - **video renditions:** `note.video.media.stream[<idx>][<quality>]` entries with `masterUrl`, `backupUrls[]`, `fps,width,height,videoCodec,audioCodec,audioBitrate,videoBitrate,avgBitrate,qualityType,size,duration(ms)`;
  - **original file:** `note.video.consumer.originVideoKey` → direct `GET https://sns-video-bd.xhscdn.com/<key>` (extractor HEAD-checks it);
  - **images (image notes / covers):** `note.imageList[*].urlDefault` / `.urlPre` (xhscdn webpic URLs);
  - metadata: `note.title`, `note.desc`, `note.tagList[].name`, `note.user.userId`; `og:title` from HTML.

**But from a datacenter IP the webpage itself is walled:** ✅❌
```
GET https://www.xiaohongshu.com/explore/6411cf99000000001300b6d9
→ 302 → https://www.xiaohongshu.com/404/sec_<rand>?redirectPath=...&error_code=300031
        &error_msg=当前笔记暂时无法浏览 ("this note temporarily cannot be viewed")&verifyMsg=
```
- Reproduced with plain curl (browser UA) **and** curl_cffi `chrome`/`safari184` impersonation → always the `sec_` challenge redirect. IP-reputation / trust-token based, not TLS-based.
- With a compliant session (residential IP + cookies from a real browser visit), yt-dlp's extractor works — i.e., the *parsing* is maintained; the *access* is the problem.

### (b) What the page gives when accessible (for our own scraper)
- `window.__INITIAL_STATE__` is inline in HTML (some deployments store `note.detail.videos`/media as base64-encoded JSON strings that must be decoded after `js_to_json` — community scrapers handle both encodings).
- Video CDN hosts: `sns-video-bd.xhscdn.com` (direct by `originVideoKey`), stream URLs under `*.xhscdn.com`; images `sns-webpic-qc.xhscdn.com`. These CDN URLs are NOT separately signature-protected once you have them (**UNVERIFIED for direct CDN fetch from DC IP** — we could not obtain a real URL from a DC IP).
- The signed API route `GET https://edith.xiaohongshu.com/api/sns/web/v1/feed` (POST) / `/api/sns/web/v1/note/<id>` requires `x-s`, `x-t` (+ `x-s-common`) signature headers and a `web_session`-bearing cookie — **not cookieless**. ❌

### (c) Fallbacks
- **XHS-Downloader (JoeanAmier/XHS-Downloader)** — popular open-source Python tool, claims 无需登录 (no login) for public notes, parses `__INITIAL_STATE__` exactly as above, supports image+video notes and live-photo assets. CLI/TUI. **UNVERIFIED from DC IP** — the `sec_` challenge we hit suggests it needs compliant IP/headers; test before adoption.
- Online parsers (HelloTik etc.): **UNVERIFIED**, no stable documented JSON API, don't build on them.
- Self-host proxy with residential exit + seeded cookies is the only robust route today (out of cookieless scope).

### (d) Verdict
- RedNote is (with Instagram) the hardest platform for cookieless datacenter downloads. Recommend: (1) try yt-dlp/xhs-downloader direct (fails on DC IPs), (2) plan an optional residential-proxy egress or accept failure with clear error, (3) watch for xsec_token requirement on share links.

---

## Executive matrix (datacenter-IP, cookieless, verified 2026-10-03)

| Platform | Primary | Status | Fallback | Status |
|---|---|---|---|---|
| TikTok | yt-dlp TikTokIE | ❌ IP-walled | **tikwm.com API** (`data.play` no-WM) | ✅ works, ~1 r/s policy |
| Instagram | yt-dlp anonymous | ❌ login required | self-host InstaFix / embed proxies | ⚠️ UNVERIFIED, public instances down |
| Reddit | Arctic Shift metadata + `v.redd.it/HLSPlaylist.m3u8` via yt-dlp, or CMAF_*.mp4+CMAF_AUDIO_128.mp4 + ffmpeg | ✅ works | direct CMAF files (no sig) | ✅ works; DASH_* dead |
| X/Twitter | yt-dlp TwitterIE (guest token GraphQL) | ✅ works | fxtwitter API → `tweet.media.videos[].url`; syndication (Googlebot UA + π-token) | ✅ both work |
| Douyin | — | ❌ needs ttwid+signing | self-host evil0ctal v5 (headless identity pool) | ⚠️ viable w/ sidecar, UNVERIFIED output |
| RedNote | yt-dlp XiaoHongShuIE | ❌ `sec_` challenge 302 | XHS-Downloader self-host | ⚠️ UNVERIFIED from DC IP |

**Audio merge notes:** Reddit CMAF video files carry no audio track (audio is a separate `CMAF_AUDIO_*.mp4` — ffmpeg mux required, or use the HLS playlist through yt-dlp which handles it). TikTok/X/Douyin/RedNote mp4s are muxed.

**General gotchas:** signed/expiring CDN URLs everywhere (resolve-then-download immediately); always send a real-browser User-Agent (several endpoints 403/serve junk to curl defaults); TikTok/Reddit blocks are ASN-based — curl_cffi impersonation does NOT bypass them, so don't over-invest in fingerprint spoofing for those two; DO use impersonation-style headers for X guest API and general politeness.
