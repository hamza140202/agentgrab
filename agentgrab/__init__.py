"""AgentGrab — yt-dlp for AI agents. Cookieless YouTube & Instagram downloads with self-healing fallback chains."""

__version__ = "1.0.0"

from .models import DownloadRequest, DownloadResult, MethodResult  # noqa: F401
from .orchestrator import download, detect_platform  # noqa: F401
