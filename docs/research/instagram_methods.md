# Instagram cookieless download from cloud/datacenter IPs — late 2025 / 2026

Task 1-b research. All "VERIFIED" claims were live-tested from this sandbox's datacenter IP
(47.57.242.119, known-flagged: same IP where yt-dlp gets "Sign in to confirm you're not a bot"
on YouTube and "empty media response" on Instagram). Raw evidence in `/tmp/igsearch/raw/`
(embed HTML, JSON responses, downloaded MP4s) and cloned sources in `/tmp/igsearch/instafix`
and `/tmp/igsearch/cobalt`.

---

## TL;DR

Per-post public reels/posts CAN still be downloaded anonymously from a datacenter IP via the
**web GraphQL endpoint `POST https://www.instagram.com/graphql/query` with
`doc_id=27128499623469141`** (the query instaloader 4.15.3 uses) — requires only the anonymous
`csrftoken` cookie from a GET to instagram.com, no login. yt-dlp fails because it uses a
*different* endpoint (`/api/graphql`, doc_id `27130156389949648`) that is gated.
**Profile/tag/hashtag enumeration anonymously is effectively dead** (401/429).

---

## TOP 5 ranked approaches

### #1 — Web GraphQL `doc_id=27128499623469141` (direct HTTP, no login) ✅ VERIFIED
*(same endpoint instaloader uses; returns `video_versions` MP4 URLs, images, carousels, captions)*

Two-step recipe (works from flagged datacenter IP, tested 6/6 across photo/reel/carousel):

```bash
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

# Step 1: obtain ANONYMOUS csrftoken cookie (no login!)
curl -s -c cj.txt -A "$UA" https://www.instagram.com/ -o /dev/null
CSRF=$(grep csrftoken cj.txt | awk '{print $7}')

# Step 2: doc_id query for the shortcode
curl -s -b cj.txt -A "$UA" \
  -H "x-csrftoken: $CSRF" \
  -H "x-ig-app-id: 936619743392459" \
  "https://www.instagram.com/graphql/query" \
  --data-urlencode 'variables={"shortcode":"CDUMkliABpa","__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider":false}' \
  --data-urlencode "doc_id=27128499623469141" \
  --data-urlencode "server_timestamps=true"
```

Response: `data.xdt_api__v1__media__shortcode__web_info.items[0]` with:
- `media_type`: 1=photo, 2=video, 8=carousel
- `video_versions[]` → `{url, width, height}` (pick max area; verified 720x1280 MP4)
- `image_versions2.candidates[].url` (poster/photo)
- `carousel_media[]` (children have their own `video_versions`/`image_versions2`)
- `caption.text`, `user.username`, `pk` (media id), `taken_at`, `code`

Hard-won caveats (all tested):
- **No cookie jar → HTTP 403** (HTML). The anonymous csrftoken cookie is mandatory.
- **Missing the `__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider:false`
  variable → HTTP 200 but `items: []`** (silent empty). Keep the exact variables shape.
- Without `x-csrftoken` header matching the cookie → `{"errors":[{"message":"execution error"}]}`.
- CDN video URLs (`scontent-*.cdninstagram.com/o1/v/t2/...mp4?oe=...`) are signed and expire
  (~hours) — download immediately. Direct CDN GET from this datacenter IP worked (3.2 MB MP4).
- Rate limits: 4 rapid repeats OK; instaloader self-throttles ~275 GQL req/10 min (client cap);
  server 429s observed on *profile* paths, not on per-post queries at low volume.

### #2 — instaloader 4.15.3 (pip) for single posts/reels ✅ VERIFIED
```bash
pip install instaloader            # 4.15.3
instaloader -- -CDUMkliABpa        # single post/reel by shortcode (note the "-" target)
# → downloads 2020-07-31_...UTC.mp4 (3.2 MB, verified ISO Media MP4) + .jpg + .txt + .json
```
- Auth/key needed: **none** for single public posts.
- Python API: `from instaloader import Instaloader, Post; post = Post.from_shortcode(ctx, code)`
  → `post.video_url`, `.title`, `.owner_username`, etc.
- Internally issues exactly the #1 query (doc_id `27128499623469141`,
  `structures.py:_obtain_metadata`) plus full retry/429 handling.
- **Anonymous PROFILE downloads are broken in practice from datacenter IPs** (VERIFIED):
  `instaloader world_record_egg` → server 429, "The request will be retried in 666 seconds".
  Needs login (session file) to be practical for bulk/profile scraping.

### #3 — Self-hosted cobalt (imputnet/cobalt) with Instagram support
- Source: https://github.com/imputnet/cobalt — `api/src/processing/services/instagram.js`.
  Anonymous fallback chain: (1) `i.instagram.com/api/v1/oembed/?url=` with **Instagram Android
  app UA** → `media_id`; (2) `i.instagram.com/api/v1/media/{id}/info/` with mobile headers
  (IP-reputation dependent); (3) `instagram.com/p/{id}/embed/captioned/` HTML
  `contextJSON`; (4) web GQL `POST /graphql/query` doc_id `8845758582119845`
  (`PolarisPostActionLoadPostQueryQuery`) with anon cookies (csrftoken+ig_did+mid) built from
  the post page. Optional `instagram` cookies make it reliable.
- Live public instance test (no login): `POST https://co.otomir23.me/`
  `{"url":"https://www.instagram.com/reel/Cop84x6u7CP/"}` → `{"status":"redirect","url":".../o1/v/t2/...mp4"}`
  (real MP4 URL, VERIFIED). Two other reels returned `tunnel` with **.jpg poster** — i.e. the
  instance's chain degraded for some posts. Expect partial results from public instances.
- Official `api.cobalt.tools` requires auth now: `{"code":"error.api.auth.jwt.missing"}` (400).
- Self-host:
  ```bash
  docker run -d -p 9000:9000 ghcr.io/imputnet/cobalt:10   # see docs/run-an-instance.md
  curl -X POST http://localhost:9000/ -H 'Content-Type: application/json' \
       -d '{"url":"https://www.instagram.com/reel/XXXX/"}'
  ```
- `instances.cobalt.best` (community instance list) is **DEAD** — parked/ads domain (VERIFIED).

### #4 — InstaFix (Wikidepia/InstaFix, Go) — self-host; embed-scraper + GQL fallback
- Source: https://github.com/Wikidepia/InstaFix. Routes: `/p/{id}`, `/reel/{id}`, `/tv/{id}`,
  `/stories/{user}/{id}`, `/images/{id}/{n}`, `/videos/{id}/{n}` (302 → CDN URL; needs
  TelegramBot UA for direct redirect), `/oembed`. Non-bot UAs get an HTML embed page.
- Scraper: `GET instagram.com/p/{id}/embed/captioned/` (no login) → TimeSliceImpl JSON /
  EmbeddedMediaImage; on "WatchOnInstagram" gating → `POST /graphql/query`
  doc_id `25531498899829322` (older PolarisPostActionLoadPostQueryQuery) — **this doc_id got
  403 from our flagged IP even with full Chrome header set** (VERIFIED); works on cleaner IPs.
  Optional `-remote-scraper` sidecar (InstaFix-remote-scraper) for blocked deployments.
- VERIFIED: the embed endpoint itself works anonymously from datacenter IP but serves **only
  the poster image for videos** (no mp4 in HTML) and only to non-browser UAs
  (curl/python/Go UAs → media HTML; Chrome UA → "EmbedBrokenMedia").
- Public instances today: `ddinstagram.com` → NXDOMAIN (from here); `kkinstagram.com` →
  301 to `kkclip.com` app landing (degraded: `/videos/...` returned poster JPG); `vxinstagram.com`
  → 502. Self-host: `docker run -p 3000:3000 ghcr.io/wikidepia/instafix:main`.

### #5 — Commercial no-login APIs (documented, stable, paid) + mobile oEmbed helper
- Apify Store (verified via `api.apify.com/v2/store`, PAY_PER_EVENT pricing):
  - `coderx/instagram-posts-reels-scraper-no-login-required`
  - `data-slayer/instagram-profile-reels` (~50k runs), `intropix/instagram-posts-reels-scraper` (~27k runs)
  ```bash
  curl -X POST "https://api.apify.com/v2/acts/coderx~instagram-posts-reels-scraper-no-login-required/run-sync-get-dataset-items?token=$APIFY_TOKEN" \
       -H 'Content-Type: application/json' -d '{"urls":["https://www.instagram.com/reel/XXXX/"]}'
  ```
  Free tier: $5/mo platform credits.
- **Mobile oEmbed (free, VERIFIED 200 from datacenter IP, no login)** — metadata + media_id
  resolver, *no* video URL:
  ```bash
  curl "https://i.instagram.com/api/v1/oembed/?url=https://www.instagram.com/p/CDUMkliABpa/" \
    -H "user-agent: Instagram 275.0.0.27.98 Android (33/13; 280dpi; 720x1423; Xiaomi; Redmi 7; onclite; qcom; en_US; 458229237)" \
    -H "x-ig-app-locale: en_US" -H "x-ig-device-locale: en_US" -H "x-fb-http-engine: Liger"
  # → {media_id: "2365570995034528346_6178175591", title, author_name, thumbnail_url, ...}
  ```
  (This is cobalt's step-1 resolver.)

---

## Confirmed-dead / do-not-re-test

| # | Approach | Evidence |
|---|----------|----------|
| 1 | **yt-dlp Instagram extractor** on datacenter IP (user's failure reproduced by source analysis) | extractor tries `/api/v1/media/{id}/info/` → 302 login redirect; `/api/graphql` doc_id `27130156389949648` → returns HTML wall (I tested manually with anon cookies); webpage RelayPrefetch → gated ⇒ "empty media response" |
| 2 | `/api/v1/media/{id}/info/` with **web** headers (old 2023-24 X-IG-App-ID trick) | 302 login redirect (i.instagram.com and www) |
| 3 | `/api/v1/media/{id}/info/` with **mobile app UA** from flagged IPs | 403 `login_required` (IP-reputation; may work on clean IPs — cobalt relies on it) |
| 4 | Anonymous profile/tag enumeration: `/api/v1/users/web_profile_info/`, user GQL doc_id `9510064595728286`, instaloader profile runs | 401 `require_login` / server 429 with 666 s retry |
| 5 | Legacy `api.instagram.com/oembed/` (no token) | dead; Graph oEmbed requires app access token |
| 6 | Public InstaFix instances as a group | ddinstagram NXDOMAIN; kkinstagram → kkclip app-landing (jpg-degraded); vxinstagram 502 |
| 7 | `instances.cobalt.best` directory | parked/ads domain |
| 8 | gallery-dl anonymous Instagram | official docs: "login required since mid-2023", still true |
| 9 | fastdl.app / igram.world / indown.io ajax backends (`/api/ajaxSearch`) | routes moved → 404s; undocumented, unstable; snapinsta.app unreachable (DNS-blocked here) |
| 10 | Graph API "public media no token" | no such API; Business/Creator accounts + tokens only |

## Answers to the specific checklist

1. **Does instaloader still allow anonymous public profile post downloads in 2026?**
   Per-post (shortcode) anonymous: **YES, verified** (real MP4 downloaded). Anonymous
   profile/hashtag enumeration: **effectively NO from datacenter IPs** — 429 throttles
   (666 s waits) and 401 `require_login` on the profile endpoints; needs login session.
2. **Does public oEmbed/GraphQL return video URLs without auth?**
   oEmbed: no (metadata only, and legacy oEmbed is token-gated).
   GraphQL: **YES** — `POST /graphql/query` doc_id `27128499623469141` with anonymous
   csrftoken returns `video_versions` (verified); InstaFix's older doc_id
   `25531498899829322` got 403 from this IP; yt-dlp's `/api/graphql` doc_id is gated.
3. **Which cobalt-like instances support IG without login?**
   Self-hosted cobalt = full chain (add cookies for reliability). Public
   `co.otomir23.me` partially works (1 of 3 test reels returned a real MP4 URL; others
   jpg-degraded). Official API requires JWT. InstaFix public instances are dead/degraded.
4. **Documented stable snapinsta/fastdl-style backends?** None found; that family is
   undocumented, CF-walled and shifting routes (404s). Not recommended.

## Next actions for AgentDL (suggestion only — no code changed in this task)
- Add `ig-graphql` strategy implementing recipe #1 (~30 lines; requests + cookie jar),
  or ship instaloader in the venv as the Instagram primary; keep `ig-ytdlp` as last resort.
- Keep `ig-instafix` only with a *self-hosted* instance (`AGENTDL_INSTAFIX_URL`); public
  instances are unreliable.
- Consider a cookies tier only for profile/tag bulk enumeration, not per-post.

## Raw evidence index (/tmp/igsearch/raw/)
- `gql_egg2.json` → InstaFix doc_id 25531498899829322 → 403 HTML (flagged IP)
- `gql2712.json`, `g_*.json`, `rr1-4.json` → doc_id 27128499623469141 → 200 with data
- `nocookie.json` (403), `csrfonly.json` (execution error), `s1-3.json` (items:0 without relay var) → caveats
- `embed_BsOGulcndj-.html` (image post embed OK), `emb_CDUMkliABpa.html` (reel → poster only + WatchOnInstagram)
- `./-CDUMkliABpa/2020-07-31_17-54-43_UTC.mp4` → instaloader anonymous download (3.2 MB MP4)
- `oembed_mob.json` → mobile oEmbed 200; `mediainfo_mob.json` → 403 login_required
- `apigql.json` → yt-dlp's /api/graphql doc_id → HTML wall
- `cobalt_*.json`, `cobalt_reel.mp4`(403 probe), otomir23 responses in transcript
- `wpi.json` → web_profile_info 401; sources cloned: `/tmp/igsearch/instafix`, `/tmp/igsearch/cobalt`
