"""Method contract. One method = one class = one file. Raise MethodError, never return None."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..models import DownloadRequest, MethodResult


class DownloadMethod(ABC):
    name: str = "base"
    platforms: tuple = ()          # e.g. ("youtube",) or ("instagram",)
    default_timeout: int = 180

    @abstractmethod
    def download(self, req: DownloadRequest) -> MethodResult:
        """Download req.url. Return MethodResult on success, raise MethodError(root_cause) on failure."""

    # ---- shared helpers --------------------------------------------------------
    @staticmethod
    def _shortcode_from_url(url: str) -> str:
        m = re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
        if not m:
            raise MethodError("cannot extract shortcode from URL")
        return m.group(1)

    @staticmethod
    def _youtube_id(url: str) -> str:
        m = (re.search(r"(?:v=|/shorts/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})", url)
             or re.search(r"/(?:live/)/([A-Za-z0-9_-]{11})", url))
        if not m:
            raise MethodError("cannot extract YouTube video id from URL")
        return m.group(1)

    @staticmethod
    def _clean_error(stderr: str) -> str:
        """Extract the ERROR line from yt-dlp output, collapsed to one line."""
        for line in (stderr or "").splitlines():
            line = line.strip()
            if line.startswith("ERROR:"):
                line = line[len("ERROR:"):].strip()
                # collapse known verbose prefixes
                line = re.sub(r"^\[[^\]]+\]\s*\S+:\s*", "", line)
                return line[:220]
        tail = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
        return (tail[-1] if tail else "unknown error")[:220]
