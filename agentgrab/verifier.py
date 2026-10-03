"""Verifier — ffprobe oracle. Files are guilty until proven innocent."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config
from .errors import VerificationError


def verify_file(path: Path) -> dict:
    """Validate a downloaded file is real, playable media.

    Returns {"container", "video_codec", "audio_codec", "duration", "size"}.
    Raises VerificationError with a one-line root cause otherwise.
    """
    path = Path(path)
    if not path.exists():
        raise VerificationError("file does not exist")
    size = path.stat().st_size
    if size < config.MIN_FILE_BYTES:
        raise VerificationError(f"file too small ({size}B < {config.MIN_FILE_BYTES}B) — likely an error page")

    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", "--", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise VerificationError("ffprobe binary not found (install ffmpeg)") from None
    except subprocess.TimeoutExpired:
        raise VerificationError("ffprobe timed out") from None

    if proc.returncode != 0:
        raise VerificationError(f"ffprobe rejected file: {_tail(proc.stderr)}")

    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise VerificationError("ffprobe returned unparseable output") from None

    streams = info.get("streams", [])
    fmt = info.get("format", {})
    real_video = [s for s in streams if s.get("codec_type") == "video"
                  and s.get("codec_name") not in config.IMAGE_CODECS]
    image_video = [s for s in streams if s.get("codec_type") == "video"
                   and s.get("codec_name") in config.IMAGE_CODECS]
    audio = [s for s in streams if s.get("codec_type") == "audio"]

    if not real_video and not audio:
        if image_video:
            raise VerificationError("image file masquerading as media (thumbnail degrade)")
        raise VerificationError("no audio or video streams found")

    duration = None
    for source in (fmt.get("duration"), *(s.get("duration") for s in streams)):
        try:
            if source is not None:
                duration = float(source)
                break
        except (TypeError, ValueError):
            continue
    if duration is not None and duration < config.MIN_DURATION_S:
        raise VerificationError(f"duration {duration:.2f}s below minimum {config.MIN_DURATION_S}s")

    return {
        "container": fmt.get("format_name", "unknown"),
        "video_codec": real_video[0].get("codec_name") if real_video else None,
        "audio_codec": audio[0].get("codec_name") if audio else None,
        "duration": duration,
        "size": size,
    }


def _tail(text: str, max_len: int = 160) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return (lines[-1] if lines else "unknown ffprobe error")[:max_len]
