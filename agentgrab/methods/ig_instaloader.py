"""ig_instaloader — Instagram workhorse: instaloader single-post anonymous download.

Verified during the original build: anonymous MP4 + JPG + JSON for a public post
from a flagged datacenter IP. Scope: SINGLE POSTS ONLY (anonymous profile/hashtag
enumeration is dead — 401/429 walls). Judged by produced files, not log noise
(instaloader emits 401 warnings and still succeeds).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod


class IgInstaloaderMethod(DownloadMethod):
    name = "ig_instaloader"
    platforms = ("instagram",)
    default_timeout = config.DEFAULT_TIMEOUTS["ig_instaloader"]

    def download(self, req: DownloadRequest) -> MethodResult:
        shortcode = self._shortcode_from_url(req.url)
        req.output_dir.mkdir(parents=True, exist_ok=True)
        target_dir = req.output_dir / shortcode

        # Anti-contamination: snapshot pre-existing mp4s. The fallback must only
        # ever accept files instaloader produced DURING this run — a shared output
        # dir otherwise lets an unrelated earlier file masquerade as this post.
        t0 = time.time()
        pre_existing = set()
        for d in (req.output_dir, target_dir):
            if d.exists():
                pre_existing |= {p.resolve() for p in d.glob("*.mp4")}

        cmd = ["instaloader", "--dirname", str(req.output_dir), "--no-compress-json",
               "--", shortcode]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=req.timeout or self.default_timeout)
        except FileNotFoundError:
            raise MethodError("instaloader binary not found (pip install instaloader)") from None
        except subprocess.TimeoutExpired:
            raise MethodError(f"instaloader timeout after {req.timeout or self.default_timeout}s") from None

        # instaloader may exit non-zero on partial warnings; judge by NEW files only.
        candidates = []
        for d in (target_dir, req.output_dir):
            if d.exists():
                candidates.extend(
                    p for p in d.glob("*.mp4")
                    if p.resolve() not in pre_existing
                    and p.stat().st_mtime >= t0 - 5)
        if not candidates:
            cause = self._extract_error(proc.stderr) or "no new .mp4 produced (rate-limited or gated)"
            raise MethodError(cause)
        mp4 = max(candidates, key=lambda p: p.stat().st_size)
        title, duration, user = shortcode, None, None
        for jf in target_dir.glob("*.json"):
            try:
                meta = json.loads(jf.read_text())
                node = (meta.get("node") or {}) if isinstance(meta, dict) else {}
                caption = (node.get("edge_media_to_caption", {}).get("edges") or [{}])[0].get("node", {}).get("text")
                user = node.get("owner", {}).get("username") or user
                if caption:
                    title = utils.slugify(caption, 80)
                    break
            except Exception:
                continue
        if user and title == shortcode:
            title = f"ig_{user}_{shortcode}"

        # normalize the filename to our stem (keep the original as fallback)
        final = req.output_dir / f"{title}.mp4"
        if final.resolve() != mp4.resolve():
            try:
                mp4 = mp4.rename(final)
            except OSError:
                final = mp4

        utils.log.info("instaloader: %s in %.1fs", final, time.time() - t0)
        return MethodResult(file=final, title=title, duration=duration,
                            size=final.stat().st_size,
                            meta={"shortcode": shortcode, "user": user})

    @staticmethod
    def _extract_error(stderr: str) -> str | None:
        for line in (stderr or "").splitlines():
            line = line.strip()
            if line.startswith("Error:") or "login" in line.lower() and "required" in line.lower():
                return utils._one_line(line)
        return None
