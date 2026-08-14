#!/bin/bash
# start_proxy_chrome.sh — Start headless Chrome with a local proxy for the
# ChatGPT Web Bridge (CDP on :9222).
#
# Used when target sites are blocked for direct connection (e.g. chatgpt.com
# from mainland China): point PROXY_URL at an outbound proxy (SSH tunnel,
# Clash, V2Ray, ...). Works on Ubuntu and macOS.
#
# Overrides (environment variables):
#   CHROME_BIN   path to a Chrome/Chromium binary (auto-detected if unset)
#   PROXY_URL    outbound proxy, e.g. http://127.0.0.1:17891 (default)
#   CDP_PORT     remote debugging port (default 9222)
#   CHROME_DATA  user-data-dir (default /tmp/chrome-proxy)
#
# The chatgpt_web_cli.py driver auto-discovers this script next to itself,
# so keep both files in the same directory.

PORT="${CDP_PORT:-9222}"
PROXY="${PROXY_URL:-http://127.0.0.1:17891}"
DATA_DIR="${CHROME_DATA:-/tmp/chrome-proxy}"
LOCAL_NO_PROXY="127.0.0.1,localhost,::1"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}$LOCAL_NO_PROXY"
export no_proxy="${no_proxy:+$no_proxy,}$LOCAL_NO_PROXY"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

# --- Locate a Chrome/Chromium binary ---------------------------------------
detect_chrome() {
  # 1) explicit override
  [ -n "$CHROME_BIN" ] && [ -x "$CHROME_BIN" ] && { echo "$CHROME_BIN"; return; }
  # 2) Playwright-managed Chromium (Ubuntu)
  for p in "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  # 3) Playwright-managed Chromium (macOS)
  for p in "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  # 4) system Chrome (macOS)
  [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] && \
    { echo "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; return; }
  # 5) any chrome/chromium on PATH
  for name in google-chrome google-chrome-stable chromium chromium-browser; do
    if command -v "$name" >/dev/null 2>&1; then echo "$(command -v "$name")"; return; fi
  done
  echo ""
}

CHROME="$(detect_chrome)"
if [ -z "$CHROME" ]; then
  echo "ERROR: no Chrome/Chromium found. Set CHROME_BIN, install Google Chrome," \
       "or run: pip install playwright && playwright install chromium" >&2
  exit 1
fi

if curl -s -m 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome already running on :${PORT}"
  exit 0
fi

CHROME_ARGS=(--headless=new --no-sandbox --disable-gpu \
  --remote-debugging-port="${PORT}" \
  --proxy-server="${PROXY}" \
  --user-data-dir="${DATA_DIR}" \
  --disable-blink-features=AutomationControlled \
  --user-agent="${UA}" \
  --window-size=1920,1080 --lang=en-US about:blank)

if command -v screen >/dev/null 2>&1; then
  screen -dmS chrome-proxy "$CHROME" "${CHROME_ARGS[@]}"
else
  # macOS fallback when screen is unavailable
  nohup "$CHROME" "${CHROME_ARGS[@]}" >/tmp/chrome-proxy.log 2>&1 &
fi

sleep 3
if curl -s -m 5 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome up on :${PORT} via proxy ${PROXY} (bin: ${CHROME})"
else
  echo "FAILED to start Chrome" >&2
  exit 1
fi
