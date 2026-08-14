#!/bin/bash
# install.sh — Install the ChatGPT Web Bridge (Ubuntu / macOS).
#
# - Copies chatgpt_web_cli.py + start_proxy_chrome.sh into ~/.hermes/scripts/
# - Ensures the playwright python package is available
# - Verifies Chrome/Chromium presence (or installs the Playwright one)
#
# Overrides:
#   INSTALL_DIR   target dir (default: $HOME/.hermes/scripts)
#   PROXY_URL     outbound proxy used by start_proxy_chrome.sh
#   CHROME_BIN    explicit Chrome binary path
#   NO_PLAYWRIGHT=1   skip pip install playwright
#
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/.hermes/scripts}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing into ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
cp "${SCRIPT_DIR}/chatgpt_web_cli.py" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/start_proxy_chrome.sh" "${INSTALL_DIR}/"
chmod +x "${INSTALL_DIR}/start_proxy_chrome.sh"

if [ -z "${NO_PLAYWRIGHT:-}" ]; then
  echo "==> Ensuring playwright python package"
  if python3 -c "import playwright" 2>/dev/null; then
    echo "    playwright already available"
  else
    python3 -m pip install --user playwright || python3 -m pip install playwright
  fi
fi

echo "==> Checking Chrome/Chromium"
CHROME="${CHROME_BIN:-}"
if [ -z "$CHROME" ]; then
  for p in "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome \
           "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
    [ -x "$p" ] && CHROME="$p" && break
  done
fi
if [ -z "$CHROME" ] && command -v google-chrome >/dev/null 2>&1; then
  CHROME="$(command -v google-chrome)"
fi
if [ -z "$CHROME" ]; then
  echo "    No Chrome found. Installing Playwright Chromium..."
  python3 -m playwright install chromium
else
  echo "    Using: ${CHROME}"
fi

if [ -n "${PROXY_URL:-}" ]; then
  echo "==> Setting PROXY_URL=${PROXY_URL} in start_proxy_chrome.sh"
  sed -i.bak "s|http://127.0.0.1:17891|${PROXY_URL}|" \
    "${INSTALL_DIR}/start_proxy_chrome.sh" && rm -f "${INSTALL_DIR}/start_proxy_chrome.sh.bak"
fi

echo
echo "==> Done. Next steps:"
echo "  1. Start the proxied Chrome:"
echo "     python3 ${INSTALL_DIR}/chatgpt_web_cli.py ensure-browser"
echo "  2. Verify login (see README if logged_in is false):"
echo "     python3 ${INSTALL_DIR}/chatgpt_web_cli.py status"
echo "  3. Smoke test:"
echo "     python3 ${INSTALL_DIR}/chatgpt_web_cli.py ask '只回复 CHATGPT_PLUGIN_OK' --timeout 150"
echo
echo "  Full guide: README.md  |  Agent self-setup prompt: AGENTS.md"
