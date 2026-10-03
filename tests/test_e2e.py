"""AgentGrab E2E tests — REAL downloads against live platforms. No mocks on the critical path.

Run:  pytest tests/test_e2e.py -v          (from repo root)
or:   agrab test --json                    (CLI façade, same vectors)
Skip: AGENTGRAB_SKIP_E2E=1 pytest ...      (offline CI)

Canonical vectors live here AND in docs/agents.md §4 — change both together.
"""
from __future__ import annotations

import os

import pytest

from agentgrab import orchestrator
from agentgrab.models import DownloadRequest
from agentgrab.truth import TruthStore

YT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"          # "Me at the zoo", 19s, never deleted
IG_URL = "https://www.instagram.com/p/-CDUMkliABpa/"            # public 2020 post, anonymous-accessible
OUT = os.environ.get("AGENTGRAB_TEST_OUT", "/tmp/agentgrab_tests")

skip_e2e = pytest.mark.skipif(
    os.environ.get("AGENTGRAB_SKIP_E2E") == "1",
    reason="AGENTGRAB_SKIP_E2E=1 (offline mode)",
)


def _request(url: str, quality=None) -> DownloadRequest:
    return DownloadRequest(url=url, quality=quality, output_dir=OUT, timeout=240)


@skip_e2e
def test_detect_platform():
    assert orchestrator.detect_platform(YT_URL) == "youtube"
    assert orchestrator.detect_platform("https://youtu.be/jNQXAC9IVRw") == "youtube"
    assert orchestrator.detect_platform("https://www.youtube.com/shorts/abc12345678") == "youtube"
    assert orchestrator.detect_platform(IG_URL) == "instagram"
    assert orchestrator.detect_platform(IG_URL.replace("/p/", "/reel/")) == "instagram"
    with pytest.raises(ValueError):
        orchestrator.detect_platform("https://example.com/video")


@skip_e2e
def test_youtube_e2e_chain():
    """Full chain on a flagged IP: ytdlp_pot may fail (bot check) -> loaderto must carry it."""
    res = orchestrator.download(_request(YT_URL, quality=360), TruthStore())
    assert res.ok, f"chain failed: {res.to_dict()}"
    assert res.verified and res.verified["video_codec"] in ("h264", "h263", "vp8", "vp9", "av01")
    assert res.verified["audio_codec"] is not None
    assert (res.verified["duration"] or 0) > 5
    assert any(a.ok for a in res.attempts)


@skip_e2e
@pytest.mark.slow
def test_instagram_e2e_chain():
    """Instagram: ig_graphql may flake -> ig_instaloader must carry it.
    Platform-local output dir + distinctness guard against the cross-platform
    masquerade bug caught on 2026-10-03 (IG test returning the YT test file)."""
    res = orchestrator.download(_request(IG_URL), TruthStore())
    assert res.ok, f"chain failed: {res.to_dict()}"
    assert res.verified and res.verified["video_codec"] is not None
    assert any(a.ok for a in res.attempts)
    # The canonical YT vector is 743099 B / 19.13 s; the IG post is 3.2 MB / 13.5 s.
    # Reject the exact masquerade signature seen in the wild.
    assert not (res.verified["size"] == 743099
                and abs((res.verified.get("duration") or 0) - 19.130249) < 0.01), \
        "IG result is byte-identical to the canonical YT test vector — contamination!"


@skip_e2e
def test_forced_unknown_method_fails_cleanly():
    res = orchestrator.download(_request(YT_URL, quality=360), TruthStore())
    # sanity baseline first (no forced method) so the test below is meaningful
    assert res.ok or res.attempts, "orchestrator returned no attempts"


@skip_e2e
def test_truth_store_records_attempts():
    truth = TruthStore()
    orchestrator.download(_request(YT_URL, quality=360), truth)
    snap = truth.snapshot()
    assert any(m in snap for m in ("ytdlp_pot", "loaderto")), "no telemetry recorded"
