# AGENTS.md — Self-configuration prompt for coding agents

> Hand this file (or its contents) to ANY coding agent — Claude Code, Codex,
> Kimi, Pi, Hermes, Cursor, ... — and it can set up this bridge from scratch on
> Ubuntu or macOS. The agent follows the steps below in order, verifying each
> one before moving on. Do NOT skip verification steps.

## Goal

Install and verify the ChatGPT Web Bridge: a Python CLI that drives a
logged-in, proxied headless Chrome (CDP :9222) to ask questions to
chatgpt.com, plus optional agent adapters. End state: `status` returns
`logged_in: true` and a marker question round-trips.

## Step 0 — Discover the environment (read-only)

```bash
uname -s            # Linux or Darwin
python3 --version   # need >= 3.9
command -v screen curl git pip3 2>/dev/null
```

## Step 1 — Install dependencies

Ubuntu:
```bash
sudo apt-get update && sudo apt-get install -y python3 python3-pip screen curl git
pip3 install --user playwright
```

macOS:
```bash
xcode-select --install   # if needed (provides python3, git)
brew install screen      # optional; script falls back to nohup
pip3 install --user playwright
```

No `sudo`/no brew? Fallback: `python3 -m venv ~/chatgpt-bridge-venv && source ~/chatgpt-bridge-venv/bin/activate && pip install playwright` and use that venv's python for all later steps.

## Step 2 — Install the bridge files

Preferred location: `~/.hermes/scripts/` (works for Hermes/Pi/Kimi adapters).

```bash
mkdir -p ~/.hermes/scripts
cp chatgpt_web_cli.py start_proxy_chrome.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/start_proxy_chrome.sh
```

The CLI and launcher MUST be in the same directory (the CLI locates the
launcher relative to itself). No other paths are hardcoded.

Check for a Chrome/Chromium binary:
```bash
ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null || \
ls ~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium 2>/dev/null || \
ls "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" 2>/dev/null || \
command -v google-chrome chromium chromium-browser 2>/dev/null
```
If nothing is found: `pip install playwright && python3 -m playwright install chromium`
(or `brew install --cask google-chrome` on macOS, or ask the user for `CHROME_BIN`).

## Step 3 — Start Chrome

```bash
python3 ~/.hermes/scripts/chatgpt_web_cli.py ensure-browser
# Expect: "Chrome up on :9222 ..."
```

If Chrome fails to reach chatgpt.com, check that the machine has working
connectivity to the site (the launcher accepts a `PROXY_URL` environment
variable if a proxy is required on this network).

## Step 4 — Ensure login state

```bash
python3 ~/.hermes/scripts/chatgpt_web_cli.py status
```

- `"logged_in": true` → proceed to Step 5.
- `"logged_in": false` → the profile (`/tmp/chrome-proxy`) has no cookies:
  1. Ask the user to log in once (open `http://127.0.0.1:9222` → pick the page
     target → interact, or point a visible Chrome with the same
     `--user-data-dir` at chatgpt.com and complete the
     login), **or**
  2. Import cookies: from a user-provided `cookies.json` (Netscape format or
     Chrome `Network.setCookie` array), apply them via CDP
     (`curl -s http://127.0.0.1:9222/json` to get `webSocketDebuggerUrl`, then
     `Network.setCookie` per cookie), then reload chatgpt.com and re-run status.
- Browser unreachable (`cannot connect to Chrome`) → rerun Step 3 first.

## Step 5 — Smoke test (mandatory)

```bash
python3 ~/.hermes/scripts/chatgpt_web_cli.py ask '只回复 CHATGPT_PLUGIN_OK' --timeout 150
```
Pass criteria: `"success": true` and `"answer"` contains `CHATGPT_PLUGIN_OK`.
Note: `"stalled": true` with a complete answer is a KNOWN quirk (SSE tail
stall), NOT a failure. High-effort thinking may show no text for 1–4 minutes —
do not kill the process early.

Optional: `... ask '今天的日期？请搜索后回答' --search --timeout 150` → answer
contains today's date.

## Step 6 — Install adapters (only if the user wants agent integration)

- **Hermes**: `mkdir -p ~/.hermes/plugins/chatgpt-web && cp adapters/hermes/* ~/.hermes/plugins/chatgpt-web/` — ensure `playwright` is importable by Hermes' own python (`uv pip install --python <hermes-venv>/bin/python playwright` if it's a uv venv), then restart hermes.
- **Pi**: `cp adapters/pi/chatgpt-web.ts ~/.pi/agent/extensions/`
- **Kimi**: `cp -r adapters/kimi ~/.kimi-code/plugins-src/ask-chatgpt`, then `/plugins install` in the Kimi TUI.

## Step 7 — Report

Summarize with concrete evidence: `status` JSON,
smoke-test answer + `elapsed_s`, and which adapters were installed (with paths).
If any step failed, report the exact error and what you verified — do not
fabricate success.

## Rules an agent must respect

1. **Never run two CLI calls concurrently** (shared single tab).
2. **Never put credentials/cookies/tokens in questions.**
3. Parse the LAST JSON object on stdout; stderr is logs.
4. `logged_in: false` → profile problem, fix via login/import — never by
   restarting Chrome blindly.
5. Don't "fix" the SSE tail stall with longer timeouts.
6. Keep the CLI and `start_proxy_chrome.sh` in the same directory.
