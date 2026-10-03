"""ytdlp_pot — YouTube fast-path: yt-dlp + Node JS runtime (EJS challenge solving)
+ bgutil POT server (proof-of-origin tokens), player clients tv/visionos/web_safari.

On flagged datacenter IPs this is non-deterministic (measured ~1/12 during the
original build) — the orchestrator keeps it as tier 1 because it is fast and
highest-quality when a flag window is open, and retries are cheap.
"""
from __future__ import annotations

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod


class YtdlpPotMethod(DownloadMethod):
    name = "ytdlp_pot"
    platforms = ("youtube",)
    default_timeout = config.DEFAULT_TIMEOUTS["ytdlp_pot"]

    def _format(self, req: DownloadRequest) -> str:
        if req.mode == "audio":
            return "ba/b"
        if req.quality is None or req.quality == "max":
            return "bv*+ba/b"
        try:
            h = int(req.quality)
        except (TypeError, ValueError):
            return "bv*+ba/b"
        return f"bv*[height<={h}]+ba/b[height<={h}]/b"

    def _postprocess(self, req: DownloadRequest) -> list:
        if req.mode == "audio":
            fmt = str(req.quality or "mp3").lower()
            return ["-x", "--audio-format", fmt if fmt in ("mp3", "m4a", "wav", "flac") else "mp3",
                    "--audio-quality", "0"]
        return []

    def download(self, req: DownloadRequest) -> MethodResult:
        clients = ",".join(config.YT_PLAYER_CLIENTS)
        out_tmpl = str(req.output_dir / (req.filename or "%(title).120B [%(id)s]") ) + ".%(ext)s"
        cmd = [
            config.YTDLP_BIN,
            "--no-warnings", "--no-playlist", "--quiet",
            "--js-runtimes", config.YT_JS_RUNTIME,
            "--extractor-args", f"youtube:player_client={clients}",
            "--sleep-requests", "1",
            "--socket-timeout", "25", "--retries", "2", "--fragment-retries", "2",
            "-f", self._format(req),
            *self._postprocess(req),
            "-o", out_tmpl,
            "--print", "after_move:filepath",
            "--print", "after_move:title",
            "--print", "after_move:%(duration)s",
            "--", req.url,
        ]
        rc, out, err = utils.run(cmd, timeout=req.timeout or self.default_timeout)
        if rc != 0:
            cause = self._clean_error(err)
            if "not a bot" in cause or "Sign in" in cause:
                cause = f"bot_check: {cause}"
            raise MethodError(cause)

        lines = [l for l in (out or "").splitlines() if l.strip()]
        if len(lines) < 3:
            raise MethodError(f"unexpected yt-dlp output (rc=0, {len(lines)} print lines)")
        from pathlib import Path
        fpath = Path(lines[-3].strip())
        title = lines[-2].strip()
        try:
            duration = float(lines[-1].strip())
        except ValueError:
            duration = None
        if not fpath.exists():
            raise MethodError(f"yt-dlp reported {fpath} but file is missing")
        return MethodResult(file=fpath, title=title, duration=duration,
                            size=fpath.stat().st_size,
                            meta={"clients": clients, "js_runtime": config.YT_JS_RUNTIME})
