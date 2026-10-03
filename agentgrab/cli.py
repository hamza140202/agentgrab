"""CLI surface. Stdout = JSON (with --json) or human summary; stderr = logs.
Exit codes: 0 success | 1 download failed | 2 usage/environment error."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import __version__, config, orchestrator
from .methods import describe_methods
from .models import DownloadRequest
from .truth import TruthStore
from .utils import log, setup_logging

# ----------------------------------------------------------------------------- helpers
def _emit(data, as_json: bool, human_fn=None) -> None:
    if as_json:
        json.dump(data, sys.stdout, indent=1, default=str)
        sys.stdout.write("\n")
    else:
        if human_fn:
            human_fn(data)
        else:
            json.dump(data, sys.stdout, indent=1, default=str)
            sys.stdout.write("\n")


def _quality_type(v: str):
    if v.lower() == "max":
        return "max"
    if v.lower() in ("mp3", "m4a", "wav", "flac"):
        return v.lower()
    try:
        q = int(v)
        return q if q >= 144 else (_die(f"quality must be >= 144, mp3/m4a/wav/flac, or max"), q)[1]
    except ValueError:
        _die("quality must be an int (360..1440), audio format, or 'max'")


def _die(msg: str, code: int = 2):
    print(f"[agentgrab] error: {msg}", file=sys.stderr)
    raise SystemExit(code)


# ----------------------------------------------------------------------------- commands
def cmd_download(args) -> int:
    truth = TruthStore()
    results = []
    for url in args.urls:
        req = DownloadRequest(
            url=url, mode="audio" if args.audio else "video",
            quality=_quality_type(args.quality) if args.quality else None,
            output_dir=Path(args.output).expanduser() if args.output else None,
            filename=args.filename,
            method=args.method, timeout=args.timeout,
            verify=not args.no_verify)
        t0 = time.time()
        res = orchestrator.download(req, truth)
        results.append(res)

    payloads = [r.to_dict() for r in results]
    all_ok = all(r.ok for r in results)

    def human(_):
        for r, p in zip(results, payloads):
            if r.ok:
                print(f"saved: {p['file']}")
                print(f"  title: {p['title']!r}  duration: {p['duration']}s  size: {p['size']}B")
                print(f"  via: {p['method']} in {(time.time()-t0):.1f}s  verified: "
                      f"{p['verified']['video_codec']}/{p['verified']['audio_codec']}"
                      if p["verified"] else f"  via: {p['method']}")
            else:
                print(f"FAILED: {r.url}")
                for a in p["attempts"]:
                    print(f"  - {a['method']}: {a['error'] or 'ok'} ({a['ms']}ms)")

    if args.json:
        _emit(payloads if len(results) > 1 else payloads[0], True)
    else:
        _emit(payloads, False, human)
    return 0 if all_ok else 1


def cmd_methods(args) -> int:
    truth = TruthStore()
    items = []
    for m in describe_methods():
        m["health"] = truth.snapshot().get(m["name"], None)
        items.append(m)
    ranked = truth.rank([m["name"] for m in items])
    items.sort(key=lambda m: ranked.index(m["name"]))
    _emit({"ranked": ranked, "methods": items}, args.json,
          lambda d: [print(truth.summary_line(n)) for n in d["ranked"]])
    return 0


def cmd_truth(args) -> int:
    truth = TruthStore()
    if args.reset:
        truth.reset()
        _emit({"reset": True, "path": str(truth.path)}, args.json,
              lambda d: print(f"truth store reset: {d['path']}"))
        return 0
    _emit({"path": str(truth.path), "methods": truth.snapshot()}, args.json,
          lambda d: [print(f"{k}: {v['successes']}/{v['attempts']} "
                           f"cf={v['consecutive_failures']} q={v['quarantined']}")
                     for k, v in d["methods"].items()])
    return 0


def cmd_doctor(args) -> int:
    checks = {}

    def sh(name, cmd, ok_codes=(0,)):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            checks[name] = {"ok": p.returncode in ok_codes,
                            "detail": (p.stdout.strip().splitlines() or [""])[0][:120]}
        except Exception as e:
            checks[name] = {"ok": False, "detail": str(e)[:120]}

    sh("yt-dlp", ["yt-dlp", "--version"])
    sh("node", ["node", "--version"])
    sh("ffmpeg", ["ffmpeg", "-version"])
    sh("ffprobe", ["ffprobe", "-version"])
    try:
        import instaloader  # noqa: F401
        checks["instaloader"] = {"ok": True, "detail": "importable"}
    except Exception as e:
        checks["instaloader"] = {"ok": False, "detail": str(e)[:120]}

    for name, url in (("pot_server", config.POT_PING_URL),
                      ("egress_youtube", "https://www.youtube.com/robots.txt"),
                      ("egress_instagram", "https://www.instagram.com/robots.txt")):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.HTTP_UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                checks[name] = {"ok": r.status == 200, "detail": f"HTTP {r.status}"}
        except Exception as e:
            checks[name] = {"ok": False, "detail": str(e)[:120]}

    checks["truth_store"] = {"ok": True, "detail": str(config.TRUTH_PATH)}
    all_ok = all(c["ok"] for k, c in checks.items()
                 if k not in ("pot_server",))  # POT optional (tier-2 workhorse doesn't need it)
    _emit({"ok": all_ok, "checks": checks}, args.json,
          lambda d: [print(f"{'PASS' if c['ok'] else 'FAIL'}  {k}: {c['detail']}")
                     for k, c in d["checks"].items()])
    return 0 if all_ok else 1


def cmd_pot(args) -> int:
    def ping() -> bool:
        try:
            with urllib.request.urlopen(config.POT_PING_URL, timeout=4) as r:
                return r.status == 200
        except Exception:
            return False

    if args.action == "status":
        up = ping()
        _emit({"running": up, "ping_url": config.POT_PING_URL,
               "bgutil_home": str(config.BGUTIL_HOME)}, args.json,
              lambda d: print("POT server: RUNNING" if d["running"] else "POT server: down"))
        return 0 if up else 1

    # start
    if ping():
        _emit({"running": True, "started": False, "detail": "already healthy"}, args.json,
              lambda d: print("POT server already running"))
        return 0
    server_js = config.BGUTIL_HOME / "build" / "main.js"
    if not server_js.exists():
        log.info("cloning+building bgutil provider into %s ...", config.BGUTIL_HOME)
        repo_dir = config.BGUTIL_HOME.parent
        try:
            subprocess.run(["git", "clone", "--single-branch", "--branch", config.BGUTIL_TAG,
                            config.BGUTIL_REPO, str(config.BGUTIL_HOME.parent)],
                           check=True, capture_output=True, timeout=120)
            subprocess.run(["npm", "ci"], cwd=str(config.BGUTIL_HOME), check=True,
                           capture_output=True, timeout=300)
            subprocess.run(["npx", "tsc"], cwd=str(config.BGUTIL_HOME), check=True,
                           capture_output=True, timeout=120)
        except Exception as e:
            _die(f"bgutil setup failed: {e}")
    config.POT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.POT_LOG_PATH, "ab") as logf:
        subprocess.Popen(["node", "build/main.js"], cwd=str(config.BGUTIL_HOME),
                         stdout=logf, stderr=logf, start_new_session=True)
    for _ in range(20):
        time.sleep(0.5)
        if ping():
            break
    up = ping()
    _emit({"running": up, "started": True, "log": str(config.POT_LOG_PATH)}, args.json,
          lambda d: print(f"POT server {'started' if d['running'] else 'FAILED to start'}"
                          f" (log: {d['log']})"))
    return 0 if up else 1


def cmd_test(args) -> int:
    vectors = [("youtube", "https://www.youtube.com/watch?v=jNQXAC9IVRw")]
    if not args.quick:
        vectors.append(("instagram", "https://www.instagram.com/p/-CDUMkliABpa/"))
    truth = TruthStore()
    report = []
    for platform, url in vectors:
        # per-platform output dirs: a shared dir risks cross-platform file masquerade
        out_dir = (Path(args.output).expanduser() if args.output
                   else config.HOME_DIR / "test-downloads") / platform
        t0 = time.time()
        req = DownloadRequest(url=url, quality=360 if platform == "youtube" else None,
                              output_dir=out_dir)
        res = orchestrator.download(req, truth)
        p = res.to_dict()
        report.append({
            "platform": platform, "ok": res.ok,
            "method": p["method"], "ms": int((time.time() - t0) * 1000),
            "file": p["file"], "verified": p["verified"], "error": p["error"],
            "attempts": p["attempts"],
        })
        log.info("test %s: %s", platform, "PASS" if res.ok else "FAIL")
    all_ok = all(r["ok"] for r in report)
    _emit({"ok": all_ok, "results": report}, args.json,
          lambda d: [print(f"{'PASS' if r['ok'] else 'FAIL'} {r['platform']:9s} "
                           f"via={r['method']} {r['ms']}ms") for r in d["results"]])
    return 0 if all_ok else 1


# ----------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agrab", description="AgentGrab — yt-dlp for AI agents")
    p.add_argument("--version", action="version", version=f"agentgrab {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="download media via the fallback chain")
    d.add_argument("urls", nargs="+", help="YouTube or Instagram URL(s)")
    d.add_argument("--audio", action="store_true", help="audio only")
    d.add_argument("--quality", help="video height (360/480/720/1080/1440/max) or audio format (mp3/m4a)")
    d.add_argument("-o", "--output", help="output directory")
    d.add_argument("--filename", help="output filename stem (no extension)")
    d.add_argument("--method", help="force one method (e.g. loaderto)")
    d.add_argument("--timeout", type=int, help="per-method timeout seconds")
    d.add_argument("--no-verify", action="store_true", help="skip ffprobe verification")
    d.add_argument("--json", action="store_true", help="JSON output (agent mode)")
    d.set_defaults(fn=cmd_download)

    m = sub.add_parser("methods", help="list methods + live health, ranked")
    m.add_argument("--json", action="store_true")
    m.set_defaults(fn=cmd_methods)

    t = sub.add_parser("truth", help="truth agent health store")
    t.add_argument("--reset", action="store_true")
    t.add_argument("--json", action="store_true")
    t.set_defaults(fn=cmd_truth)

    doc = sub.add_parser("doctor", help="environment diagnostics")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(fn=cmd_doctor)

    pot = sub.add_parser("pot", help="bgutil POT server control")
    pot.add_argument("action", choices=["start", "status"])
    pot.add_argument("--json", action="store_true")
    pot.set_defaults(fn=cmd_pot)

    te = sub.add_parser("test", help="E2E self-test with real downloads")
    te.add_argument("--quick", action="store_true", help="YouTube only")
    te.add_argument("-o", "--output", help="where test files go")
    te.add_argument("--json", action="store_true")
    te.set_defaults(fn=cmd_test)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose if hasattr(args, "verbose") else False)
    try:
        rc = args.fn(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        _die("interrupted", 130)
    except Exception as e:
        log.error("unhandled: %s", e)
        _die(str(e), 2)
    sys.exit(rc)


if __name__ == "__main__":
    main()
