#!/usr/bin/env bash
# AgentGrab — bgutil POT server one-shot setup + run.
# Idempotent: skips clone/build when build/main.js already exists.
set -euo pipefail

BGUTIL_HOME="${AGENTGRAB_BGUTIL_HOME:-$HOME/bgutil-ytdlp-pot-provider/server}"
TAG="2.0.1"

if [ -f "$BGUTIL_HOME/build/main.js" ]; then
  echo "[pot] server already built at $BGUTIL_HOME"
else
  echo "[pot] cloning bgutil-ytdlp-pot-provider@$TAG ..."
  git clone --single-branch --branch "$TAG" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    "$(dirname "$BGUTIL_HOME")"
  echo "[pot] npm ci ..."
  (cd "$BGUTIL_HOME" && npm ci)
  echo "[pot] transpiling ..."
  (cd "$BGUTIL_HOME" && npx tsc)
fi

echo "[pot] starting server on 127.0.0.1:4416 (Ctrl+C to stop)"
exec node "$BGUTIL_HOME/build/main.js"
