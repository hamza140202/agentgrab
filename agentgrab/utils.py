"""Shared utilities: subprocess discipline, HTTP, JSON atomicity, logging, filenames."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import ssl
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .errors import MethodError

log = logging.getLogger("agentgrab")
_ctx = ssl.create_default_context()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="[agentgrab] %(levelname).1s %(message)s",
    )


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd: list, timeout: int) -> tuple:
    """Run a subprocess, hard-bounded. Returns (rc, stdout, stderr). Never raises on rc!=0."""
    t0 = time.time()
    env = dict(os.environ)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        ms = int((time.time() - t0) * 1000)
        raise MethodError(f"timeout after {timeout}s (killed at {ms}ms)") from None
    except FileNotFoundError:
        raise MethodError(f"binary not found: {cmd[0]}") from None
    return rc, out, err


def http_get(url: str, timeout: int = config.HTTP_TIMEOUT, headers: dict | None = None,
             max_bytes: int | None = None) -> bytes:
    h = {"User-Agent": config.HTTP_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as resp:
        if max_bytes:
            return resp.read(max_bytes)
        return resp.read()


def http_json(url: str, timeout: int = config.HTTP_TIMEOUT, headers: dict | None = None) -> dict:
    return json.loads(http_get(url, timeout=timeout, headers=headers).decode("utf-8", "replace"))


def http_post_json(url: str, payload: dict, timeout: int = config.HTTP_TIMEOUT,
                   headers: dict | None = None) -> tuple:
    """POST JSON body. Returns (status_dict_or_None, raw_bytes, http_headers)."""
    body = json.dumps(payload).encode()
    h = {"User-Agent": config.HTTP_UA, "Accept": "application/json",
         "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as resp:
            return _try_json(resp.read()), resp.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        return _try_json(raw), e.headers


def _try_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


def download_to_file(url: str, dest: Path, timeout: int = 120, headers: dict | None = None) -> int:
    """Stream a URL to dest. Returns byte count. Raises MethodError on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = {"User-Agent": config.HTTP_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as resp, \
                open(dest, "wb") as f:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
    except Exception as e:
        raise MethodError(f"stream download failed: {_one_line(e)}") from None
    return total


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_truth_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w\s.-]", "", text or "", flags=re.UNICODE).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:max_len] or "media"


def _one_line(e: Exception | str, max_len: int = 220) -> str:
    s = str(e).replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_len]
