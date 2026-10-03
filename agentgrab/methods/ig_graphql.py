"""ig_graphql — Instagram tier-1: web GraphQL query (doc_id=27128499623469141)
with an anonymous csrftoken minted per run. Fastest IG path when it works
(direct CDN URLs, no subprocess); flaky on flagged IPs -> 2 retries with fresh
cookie jars + jitter, and automatic demotion by the truth agent when it degrades.

Gotcha baked in: omitting the relay provider flag in variables yields HTTP 200
with EMPTY items — keep it.
"""
from __future__ import annotations

import http.cookiejar
import json
import random
import time
import urllib.parse
import urllib.request

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod


class IgGraphqlMethod(DownloadMethod):
    name = "ig_graphql"
    platforms = ("instagram",)
    default_timeout = config.DEFAULT_TIMEOUTS["ig_graphql"]

    def _new_session(self):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        return opener, jar

    def _mint_csrf(self, opener) -> str:
        req = urllib.request.Request(
            "https://www.instagram.com/",
            headers={"User-Agent": config.IG_BROWSER_UA,
                     "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                     "Accept-Language": "en-US,en;q=0.9"})
        with opener.open(req, timeout=20) as r:
            r.read(1024)
        for cookie in jar_of(opener):
            if cookie.name == "csrftoken":
                return cookie.value
        raise MethodError("no csrftoken cookie minted")

    def download(self, req: DownloadRequest) -> MethodResult:
        shortcode = self._shortcode_from_url(req.url)
        last_err = "unknown"
        for attempt in range(1, config.IG_GRAPHQL_RETRIES + 1):
            try:
                return self._attempt(req, shortcode)
            except MethodError as e:
                last_err = str(e)
                utils.log.debug("ig_graphql attempt %d failed: %s", attempt, last_err)
                if attempt < config.IG_GRAPHQL_RETRIES:
                    time.sleep(random.uniform(*config.IG_GRAPHQL_RETRY_JITTER))
        raise MethodError(last_err)

    def _attempt(self, req: DownloadRequest, shortcode: str) -> MethodResult:
        opener, _ = self._new_session()
        csrf = self._mint_csrf(opener)

        variables = {
            "shortcode": shortcode,
            "__relay_internal__pv__PolarisAIGMMediaWebLabelEnabledrelayprovider": False,
            "fetch_tagged_user_count": None,
            "hoisted_comment_id": None,
            "hoisted_reply_id": None,
        }
        form = urllib.parse.urlencode({
            "variables": json.dumps(variables),
            "doc_id": config.IG_GRAPHQL_DOC_ID,
            "server_timestamps": "true",
        }).encode()
        http_req = urllib.request.Request(
            "https://www.instagram.com/graphql/query",
            data=form, method="POST",
            headers={
                "User-Agent": config.IG_BROWSER_UA,
                "X-CSRFToken": csrf,
                "X-IG-App-ID": config.IG_APP_ID,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.instagram.com/",
                "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Content-Type": "application/x-www-form-urlencoded",
            })
        try:
            with opener.open(http_req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:
            raise MethodError(f"graphql request failed: {utils._one_line(e)}") from None

        if payload.get("errors"):
            msg = utils._one_line(payload["errors"][0].get("message", "execution error"))
            raise MethodError(f"graphql error: {msg}")

        info = ((payload.get("data") or {}).get("xdt_api__v1__media__shortcode__web_info") or {})
        items = info.get("items") or []
        if not items:
            raise MethodError("empty items (post gated, deleted, or doc_id stale)")

        media = items[0]
        versions = media.get("video_versions") or []
        if not versions:
            raise MethodError("no video_versions (post is image-only or media gated)")

        best = max(versions, key=lambda v: v.get("width") or 0)
        url = best.get("url")
        if not url:
            raise MethodError("video version missing url")

        user = (media.get("user") or {}).get("username") or "instagram"
        caption = ((media.get("caption") or {}).get("text") or "").strip()
        title = utils.slugify(caption or f"ig_{user}_{shortcode}", 80)
        dest = req.output_dir / f"{title}.mp4"
        size = utils.download_to_file(url, dest, timeout=60)

        duration = None
        try:
            duration = float((media.get("video_duration") or 0)) or None
        except (TypeError, ValueError):
            pass
        return MethodResult(file=dest, title=title, duration=duration, size=size,
                            meta={"shortcode": shortcode, "user": user,
                                  "width": best.get("width"), "height": best.get("height")})


def jar_of(opener):
    for handler in opener.handlers:
        if isinstance(handler, urllib.request.HTTPCookieProcessor):
            return handler.cookiejar
    return []
