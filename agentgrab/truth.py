"""Truth agent — persistent method-health store with adaptive ranking and quarantine.

Every attempt on every method is recorded here before the orchestrator moves on.
Ranking: consecutive failures (asc) → success rate (desc) → avg latency (asc).
Methods with >= QUARANTINE_THRESHOLD consecutive failures are demoted to last resort,
never removed (clouds heal; a quarantined method may recover).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config, utils

QUARANTINE_THRESHOLD = 5


class TruthStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.TRUTH_PATH)
        self._lock = threading.Lock()
        self._data: dict = {}
        self.load()

    # ---- persistence ---------------------------------------------------------
    def load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text())
        except Exception:
            self._data = {}

    def save(self) -> None:
        with self._lock:
            utils.atomic_write_json(self.path, self._data)

    def reset(self) -> None:
        self._data = {}
        self.save()

    # ---- recording -------------------------------------------------------------
    def record(self, method: str, ok: bool, ms: int, error: str | None = None) -> None:
        with self._lock:
            e = self._data.setdefault(method, {
                "attempts": 0, "successes": 0, "failures": 0,
                "consecutive_failures": 0, "avg_ms": 0,
                "last_ok": None, "last_error": None, "quarantined": False,
            })
            e["attempts"] += 1
            if ok:
                e["successes"] += 1
                e["consecutive_failures"] = 0
                e["last_ok"] = utils.utcnow_iso()
                e["last_error"] = None
            else:
                e["failures"] += 1
                e["consecutive_failures"] += 1
                e["last_error"] = (error or "unknown")[:300]
            # running average latency
            total_ms = e["avg_ms"] * (e["attempts"] - 1) + ms
            e["avg_ms"] = int(total_ms / e["attempts"])
            e["quarantined"] = e["consecutive_failures"] >= QUARANTINE_THRESHOLD
        self.save()

    # ---- ranking ---------------------------------------------------------------
    def rank(self, names: list) -> list:
        """Order method names by health. Unknown methods keep registry order at the front."""
        def key(n: str):
            e = self._data.get(n, {})
            attempts = max(e.get("attempts", 0), 1)
            rate = e.get("successes", 0) / attempts
            return (
                1 if e.get("quarantined") else 0,
                e.get("consecutive_failures", 0),
                -rate,
                e.get("avg_ms", 10**9),
            )
        known = [n for n in names if n in self._data]
        unknown = [n for n in names if n not in self._data]
        return sorted(known, key=key) + unknown

    def snapshot(self) -> dict:
        return json.loads(json.dumps(self._data))  # deep copy

    def summary_line(self, name: str) -> str:
        e = self._data.get(name)
        if not e:
            return f"{name}: no history"
        rate = f"{100 * e['successes'] / max(e['attempts'], 1):.0f}%"
        flags = " QUARANTINED" if e.get("quarantined") else ""
        return (f"{name}: {e['successes']}/{e['attempts']} ({rate})"
                f" avg={e['avg_ms']}ms{flags}")
