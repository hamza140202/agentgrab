"""Orchestrator — the pipeline: detect platform → rank methods → run fallback chain
→ verify output → record truth → return DownloadResult. Every attempt is recorded
BEFORE the next one starts, so a crash mid-chain never loses telemetry."""
from __future__ import annotations

import re
import time

from . import verifier
from .errors import MethodError, VerificationError
from .methods import chain_for
from .models import Attempt, DownloadRequest, DownloadResult
from .truth import TruthStore
from .utils import log

_YT = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)/\S+", re.I)
_IG = re.compile(r"https?://(?:www\.)?instagram\.com/\S+", re.I)


def detect_platform(url: str) -> str:
    if _YT.match(url):
        return "youtube"
    if _IG.match(url):
        return "instagram"
    raise ValueError(
        f"unsupported platform for {url!r} — supported: youtube, instagram "
        f"(roadmap: tiktok, reddit, x, douyin, rednote)")


def download(req: DownloadRequest, truth: TruthStore | None = None) -> DownloadResult:
    truth = truth or TruthStore()
    attempts: list[Attempt] = []
    try:
        platform = detect_platform(req.url)
    except ValueError as e:
        return DownloadResult(ok=False, url=req.url, platform="unknown",
                              error=str(e), attempts=[])

    try:
        chain = chain_for(platform, req, truth)
    except KeyError as e:
        return DownloadResult(ok=False, url=req.url, platform=platform,
                              error=str(e), attempts=[])

    if not chain:
        return DownloadResult(ok=False, url=req.url, platform=platform,
                              error=f"no methods registered for platform {platform!r}",
                              attempts=[])

    log.info("chain [%s]: %s", platform, " -> ".join(m.name for m in chain))

    for method in chain:
        t0 = time.time()
        log.info("trying method '%s' (timeout %ss)",
                 method.name, req.timeout or method.default_timeout)
        try:
            result = method.download(req)
            ms = int((time.time() - t0) * 1000)

            verified = None
            if req.verify:
                try:
                    verified = verifier.verify_file(result.file)
                except VerificationError as e:
                    truth.record(method.name, ok=False, ms=ms, error=f"verification: {e}")
                    attempts.append(Attempt(method.name, ok=False, ms=ms,
                                            error=f"verification: {e}"))
                    log.warning("verification failed for '%s': %s", method.name, e)
                    continue
                if req.mode == "video" and verified.get("video_codec") is None:
                    truth.record(method.name, ok=False, ms=ms,
                                 error="verification: no video stream in video mode")
                    attempts.append(Attempt(method.name, ok=False, ms=ms,
                                            error="verification: no video stream in video mode"))
                    continue
                result.duration = result.duration or verified.get("duration")

            truth.record(method.name, ok=True, ms=ms)
            attempts.append(Attempt(method.name, ok=True, ms=ms))
            log.info("success via '%s' -> %s (%.0f ms)", method.name, result.file, ms)
            return DownloadResult(
                ok=True, url=req.url, platform=platform, file=result.file,
                title=result.title or None, duration=result.duration,
                size=verified["size"] if verified else result.size,
                method=method.name, verified=verified, attempts=attempts)

        except MethodError as e:
            ms = int((time.time() - t0) * 1000)
            truth.record(method.name, ok=False, ms=ms, error=str(e))
            attempts.append(Attempt(method.name, ok=False, ms=ms, error=str(e)))
            log.warning("method '%s' failed: %s", method.name, e)
            continue

    last = attempts[-1] if attempts else None
    return DownloadResult(
        ok=False, url=req.url, platform=platform,
        error=last.error if last else "unknown failure",
        attempts=attempts)
