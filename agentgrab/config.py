"""Central configuration: paths, defaults, constants. Env overrides use AGENTGRAB_* prefix."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "agentgrab"

# --- Paths -------------------------------------------------------------------
HOME_DIR = Path(os.environ.get("AGENTGRAB_HOME", str(Path.home() / f".{APP_NAME}")))
TRUTH_PATH = HOME_DIR / "truth.json"
POT_LOG_PATH = HOME_DIR / "pot-server.log"
DEFAULT_OUTPUT_DIR = Path(os.environ.get("AGENTGRAB_OUTPUT_DIR", str(Path.home() / "Downloads")))

# --- bgutil POT server -------------------------------------------------------
POT_PING_URL = os.environ.get("AGENTGRAB_POT_PING_URL", "http://127.0.0.1:4416/ping")
# Where the bgutil-ytdlp-pot-provider checkout lives (server/build/main.js expected inside)
BGUTIL_HOME = Path(
    os.environ.get(
        "AGENTGRAB_BGUTIL_HOME",
        str(Path.home() / "bgutil-ytdlp-pot-provider" / "server"),
    )
)
BGUTIL_REPO = "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
BGUTIL_TAG = "2.0.1"

# --- YouTube (ytdlp_pot) -----------------------------------------------------
YTDLP_BIN = os.environ.get("AGENTGRAB_YTDLP_BIN", "yt-dlp")
YT_PLAYER_CLIENTS = ["tv", "visionos", "web_safari"]
YT_JS_RUNTIME = "node"
# loader.to
LOADERTO_SUBMIT_URL = "https://loader.to/ajax/download.php"
LOADERTO_VIDEO_FORMATS = [1440, 1080, 720, 480, 360]
LOADERTO_DEFAULT_VIDEO_FORMAT = 1080
LOADERTO_POLL_INTERVAL = 2.5          # seconds — courtesy throttle, do not lower
LOADERTO_MIN_SUBMIT_INTERVAL = 1.1    # seconds between submits, class-wide
LOADERTO_MAX_PROGRESS_NULL = 4        # consecutive polls with progress but no url before giving up

# --- Instagram ---------------------------------------------------------------
IG_APP_ID = "936619743392459"
IG_GRAPHQL_DOC_ID = "27128499623469141"
IG_GRAPHQL_RETRIES = 2
IG_GRAPHQL_RETRY_JITTER = (2.0, 4.5)  # seconds between attempts
IG_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
COBALT_INSTANCES = ["https://co.otomir23.me/"]

# --- Method default timeouts (seconds) ---------------------------------------
DEFAULT_TIMEOUTS = {
    "ytdlp_pot": 300,
    "loaderto": 180,
    "ig_graphql": 90,
    "ig_instaloader": 150,
    "ig_cobalt": 120,
    "ytdlp_instagram": 180,
}
MAX_METHOD_TIMEOUT = 900

# --- Verifier ----------------------------------------------------------------
MIN_FILE_BYTES = 10_000
IMAGE_CODECS = {"mjpeg", "png", "jpeg", "webp", "bmp", "gif", "tiff"}
MIN_DURATION_S = 0.3

# --- Network -----------------------------------------------------------------
HTTP_UA = IG_BROWSER_UA
HTTP_TIMEOUT = 30
