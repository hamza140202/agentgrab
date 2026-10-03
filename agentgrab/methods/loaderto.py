"""loaderto — YouTube workhorse method via the loader.to keyless AJAX resolver API.

Their clean-IP server farm performs the YouTube handshake; our flagged IP only ever
talks to loader.to and their CDN. Protocol (verified end-to-end during the original
build):
  1. GET  https://loader.to/ajax/download.php?format=<F>&url=<enc>  -> {"success":true,"id":..,"progress_url":..}
  2. Poll progress_url every LOADERTO_POLL_INTERVAL until progress==1000 -> {"download_url":..}
  3. GET download_url (CDN, possibly different domain) -> media bytes
Courtesy guardrails: poll throttle + submit-rate ceiling + bounded budget.
"""
from __future__ import annotations

import threading
import time
import urllib.parse

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod

_submit_lock = threading.Lock()
_last_submit = 0.0


class LoadertoMethod(DownloadMethod):
    name = "loaderto"
    platforms = ("youtube",)
    default_timeout = config.DEFAULT_TIMEOUTS["loaderto"]

    # format keys accepted by loader.to
    _AUDIO = {"mp3", "m4a", "wav", "flac"}

    def _resolve_format(self, req: DownloadRequest) -> str:
        if req.mode == "audio":
            fmt = str(req.quality or "mp3").lower()
            return fmt if fmt in self._AUDIO else "mp3"
        if req.quality is None:
            return str(config.LOADERTO_DEFAULT_VIDEO_FORMAT)
        if req.quality == "max":
            return str(config.LOADERTO_VIDEO_FORMATS[0])  # 1440
        try:
            want = int(req.quality)
        except (TypeError, ValueError):
            return str(config.LOADERTO_DEFAULT_VIDEO_FORMAT)
        supported = sorted(config.LOADERTO_VIDEO_FORMATS)  # [360,480,720,1080,1440]
        for f in supported:
            if want <= f:
                return str(f)
        return str(config.LOADERTO_VIDEO_FORMATS[0])

    def download(self, req: DownloadRequest) -> MethodResult:
        vid = self._youtube_id(req.url)
        fmt = self._resolve_format(req)
        ext = fmt if fmt in self._AUDIO else "mp4"

        # --- courtesy submit throttle ------------------------------------------
        global _last_submit
        with _submit_lock:
            wait = config.LOADERTO_MIN_SUBMIT_INTERVAL - (time.time() - _last_submit)
            if wait > 0:
                time.sleep(wait)
            _last_submit = time.time()

        # --- 1. submit ----------------------------------------------------------
        q = urllib.parse.urlencode({"format": fmt, "url": req.url})
        t0 = time.time()
        try:
            sub = utils.http_json(f"{config.LOADERTO_SUBMIT_URL}?{q}", timeout=30)
        except Exception as e:
            raise MethodError(f"submit failed: {utils._one_line(e)}") from None
        if not sub.get("success"):
            raise MethodError(f"submit rejected: {utils._one_line(sub)[:120]}")
        pid = sub.get("id")
        if not pid:
            raise MethodError("submit returned no job id")
        progress_url = sub.get("progress_url") or f"{config.LOADERTO_SUBMIT_URL.rsplit('/', 1)[0]}/progress.php?id={pid}"
        utils.log.debug("loaderto job=%s fmt=%s", pid, fmt)

        # --- 2. poll ------------------------------------------------------------
        budget = max(req.timeout or self.default_timeout, 30) - 12
        null_streak = 0
        dl_url, title = None, None
        t_poll = time.time()
        while time.time() - t_poll < budget:
            time.sleep(config.LOADERTO_POLL_INTERVAL)
            try:
                p = utils.http_json(progress_url, timeout=20)
            except Exception as e:
                utils.log.debug("poll error: %s", utils._one_line(e))
                continue
            progress = p.get("progress")
            dl_url = p.get("download_url")
            title = p.get("title") or title
            if dl_url:
                break
            if progress == 1000 and not dl_url:
                null_streak += 1
                if null_streak >= config.LOADERTO_MAX_PROGRESS_NULL:
                    raise MethodError("progress complete but no download_url after retries")
        if not dl_url:
            raise MethodError(f"no download_url within budget ({budget}s) — resolver busy or rate-limited")

        # --- 3. download ---------------------------------------------------------
        stem = utils.slugify(req.filename or title or f"youtube_{vid}")
        dest = req.output_dir / f"{stem}.{ext}"
        size = utils.download_to_file(dl_url, dest, timeout=120)
        utils.log.info("loaderto: %s (%.0f bytes) in %.1fs", dest, size, time.time() - t0)
        return MethodResult(file=dest, title=title or f"youtube_{vid}",
                            size=size, meta={"job_id": pid, "format": fmt, "video_id": vid})
