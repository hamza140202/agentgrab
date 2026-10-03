"""Data contracts shared across the engine. All JSON-safe via to_dict()."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class DownloadRequest:
    url: str
    mode: str = "video"                    # "video" | "audio"
    quality: Optional[Any] = None          # height (video) or audio format (mp3|m4a)
    output_dir: Path = None                # type: ignore[assignment]  (set in __post_init__)
    filename: Optional[str] = None
    method: Optional[str] = None           # force a single method by name
    timeout: Optional[int] = None          # override per-method timeout
    verify: bool = True

    def __post_init__(self):
        from . import config
        if self.output_dir is None:
            self.output_dir = config.DEFAULT_OUTPUT_DIR
        self.output_dir = Path(self.output_dir).expanduser()
        if self.mode not in ("video", "audio"):
            raise ValueError(f"mode must be 'video' or 'audio', got {self.mode!r}")


@dataclass
class MethodResult:
    file: Path
    title: str = ""
    duration: Optional[float] = None
    size: int = 0
    meta: dict = field(default_factory=dict)


@dataclass
class Attempt:
    method: str
    ok: bool
    ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {"method": self.method, "ok": self.ok, "ms": self.ms, "error": self.error}


@dataclass
class DownloadResult:
    ok: bool
    url: str
    platform: str
    file: Optional[Path] = None
    title: Optional[str] = None
    duration: Optional[float] = None
    size: Optional[int] = None
    method: Optional[str] = None
    verified: Optional[dict] = None
    attempts: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "url": self.url,
            "platform": self.platform,
            "file": str(self.file) if self.file else None,
            "title": self.title,
            "duration": self.duration,
            "size": self.size,
            "method": self.method,
            "verified": self.verified,
            "attempts": [a.to_dict() for a in self.attempts],
            "error": self.error,
        }
