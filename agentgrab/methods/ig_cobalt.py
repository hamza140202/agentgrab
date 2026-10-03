"""ig_cobalt — Instagram last-resort via a public cobalt instance.

Independent code path (different service family). KNOWN TRAP: instances may
degrade to a .jpg thumbnail when they cannot resolve the video — the returned
filename and content type are checked and image results raise MethodError so the
orchestrator moves on. The verifier double-checks the bytes regardless.
"""
from __future__ import annotations

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod


class IgCobaltMethod(DownloadMethod):
    name = "ig_cobalt"
    platforms = ("instagram",)
    default_timeout = config.DEFAULT_TIMEOUTS["ig_cobalt"]

    def download(self, req: DownloadRequest) -> MethodResult:
        shortcode = self._shortcode_from_url(req.url)
        last_err = "no instances attempted"
        for instance in config.COBALT_INSTANCES:
            try:
                return self._via(instance, req, shortcode)
            except MethodError as e:
                last_err = f"{instance}: {e}"
                utils.log.debug("ig_cobalt %s failed: %s", instance, last_err)
        raise MethodError(last_err)

    def _via(self, instance: str, req: DownloadRequest, shortcode: str) -> MethodResult:
        payload = {"url": req.url, "filenameStyle": "basic"}
        if req.mode == "audio":
            payload["downloadMode"] = "audio"
            payload["audioFormat"] = str(req.quality or "mp3").lower()
        body, headers = utils.http_post_json(instance, payload, timeout=25)
        if not isinstance(body, dict):
            raise MethodError(f"non-JSON response ({headers.get('Content-Type', '?') if headers else 'no headers'})")
        status = body.get("status")
        if status in ("tunnel", "redirect") and body.get("url"):
            url = body["url"]
        elif status == "error":
            err = body.get("error")
            code = err.get("code") if isinstance(err, dict) else (err or "unknown")
            raise MethodError(f"api error {code}")
        else:
            raise MethodError(f"unexpected status {status!r}")

        # trap check: filename/content hints
        filename = (body.get("filename") or "").lower()
        if filename.endswith((".jpg", ".jpeg", ".png", ".webp")):
            raise MethodError(f"instance returned thumbnail ({filename}), not video")

        stem = utils.slugify(req.filename or f"ig_{shortcode}")
        ext = "mp3" if req.mode == "audio" else "mp4"
        dest = req.output_dir / f"{stem}.{ext}"
        size = utils.download_to_file(url, dest, timeout=90)
        return MethodResult(file=dest, title=stem, size=size,
                            meta={"shortcode": shortcode, "instance": instance})
