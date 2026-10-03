"""ytdlp_instagram — plain yt-dlp IG extractor. Works only on clean/residential
IPs (the /api/v1/media/{id}/info/ endpoint 302s to login from datacenter IPs and
the web GraphQL doc_id returns an HTML wall). Kept as the final IG tier: on clean
egress the truth agent will naturally rank it up."""
from __future__ import annotations

from pathlib import Path

from .. import config, utils
from ..errors import MethodError
from ..models import DownloadRequest, MethodResult
from .base import DownloadMethod


class YtdlpInstagramMethod(DownloadMethod):
    name = "ytdlp_instagram"
    platforms = ("instagram",)
    default_timeout = config.DEFAULT_TIMEOUTS["ytdlp_instagram"]

    def download(self, req: DownloadRequest) -> MethodResult:
        out_tmpl = str(req.output_dir / (req.filename or "%(title).120B [%(id)s]")) + ".%(ext)s"
        cmd = [
            config.YTDLP_BIN,
            "--no-warnings", "--no-playlist", "--quiet",
            "--socket-timeout", "25", "--retries", "2",
            "-f", "b" if req.mode == "video" else "ba/b",
            *(["-x", "--audio-format", str(req.quality or "mp3"), "--audio-quality", "0"]
              if req.mode == "audio" else []),
            "-o", out_tmpl,
            "--print", "after_move:filepath",
            "--print", "after_move:title",
            "--", req.url,
        ]
        rc, out, err = utils.run(cmd, timeout=req.timeout or self.default_timeout)
        if rc != 0:
            cause = self._clean_error(err)
            if "empty media response" in cause or "login" in cause.lower():
                cause = f"ig_login_gate: {cause}"
            raise MethodError(cause)
        lines = [l for l in (out or "").splitlines() if l.strip()]
        if not lines:
            raise MethodError("yt-dlp produced no output path")
        fpath = Path(lines[0].strip())
        title = lines[1].strip() if len(lines) > 1 else fpath.stem
        if not fpath.exists():
            raise MethodError(f"yt-dlp reported {fpath} but file is missing")
        return MethodResult(file=fpath, title=title, size=fpath.stat().st_size)
