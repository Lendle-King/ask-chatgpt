# ChatGPT Web Bridge

Drive the **logged-in ChatGPT web UI** (chatgpt.com) from any shell or coding
agent via CDP (Chrome DevTools Protocol). No OpenAI API key, no billing — it
uses your existing ChatGPT Plus/Pro browser session.

```
┌─────────────┐   python3 chatgpt_web_cli.py ask "..."    ┌──────────────────┐
│  Any agent  │ ─────────────────────────────────────────▶│  chatgpt_web_cli │
│  (Hermes /  │                                            │  (Python)        │
│   Pi / Kimi │ ◀─────────────────────────────────────────│                  │
│   / shell)  │   one line of JSON on stdout              └────────┬─────────┘
└─────────────┘                                                  CDP
                                             ┌────────────────────┴─────────┐
                                             │ headless Chrome (proxied)     │
                                             │ :9222  chatgpt.com (logged in)│
                                             └───────────────────────────────┘
```

- **Model**: GPT-5.6 Sol, effort **High** (max thinking) by default — change with `--model` / `--effort`.
- **Optional web search** via `--search` (real-time/current info).
- **Works behind the GFW**: Chrome goes through a local proxy (SSH tunnel, Clash, V2Ray...).
- **Three adapters included**: Hermes plugin, Pi extension, Kimi Code plugin — all share one driver.

> ⚠️ One shared browser tab: **never run two CLI calls concurrently** — they fight over the page.

---

## Repository layout

```
chatgpt-web-bridge/
├── chatgpt_web_cli.py        # Core driver: ask / status / ensure-browser
├── start_proxy_chrome.sh     # Starts proxied headless Chrome on CDP :9222
├── install.sh                # One-shot installer (Ubuntu / macOS)
├── AGENTS.md                 # Step-by-step self-config prompt for ANY coding agent
└── adapters/
    ├── hermes/               # Hermes Agent plugin (chatgpt_ask, chatgpt_web_status)
    ├── pi/                   # Pi coding agent extension (chatgpt-web.ts)
    └── kimi/                 # Kimi Code plugin (ask-chatgpt)
```

---

## Prerequisites

| Requirement | Ubuntu | macOS |
|---|---|---|
| Python ≥ 3.9 | `apt install python3 python3-pip` | bundled with Xcode CLT |
| Chrome/Chromium | auto-detected (Playwright cache, google-chrome, chromium) | auto-detected (Playwright cache, /Applications/Google Chrome.app) |
| `screen` (optional) | `apt install screen` | bundled (`/usr/bin/screen`) |
| **Outbound proxy** | required if chatgpt.com is blocked from your network | same |

The proxy is the only truly hard requirement: the browser must be able to
reach chatgpt.com. Typical setups: an SSH tunnel (`ssh -L 17891:127.0.0.1:7890 user@jump-host`),
Clash/V2Ray/Sing-box local ports, or a corporate proxy.

---

## Quick start (Ubuntu / macOS)

```bash
# 1. Get the code
git clone https://github.com/Lendle-King/ask-chatgpt.git && cd ask-chatgpt

# 2. Install (playwright python pkg + Chrome detection + files into ~/.hermes/)
#    Point PROXY_URL at YOUR outbound proxy first if 17891 is not yours:
export PROXY_URL=http://127.0.0.1:17891   # optional; default shown in script
bash install.sh

# 3. Start the proxied Chrome (CDP :9222)
python3 ~/.hermes/scripts/chatgpt_web_cli.py ensure-browser

# 4. Log in once (see "Login state" below), then verify:
python3 ~/.hermes/scripts/chatgpt_web_cli.py status
# → {"success": true, "logged_in": true, "composer": true, ...}

# 5. Ask a question
python3 ~/.hermes/scripts/chatgpt_web_cli.py ask "只回复 CHATGPT_PLUGIN_OK" --timeout 150
# → {"success": true, "answer": "CHATGPT_PLUGIN_OK", "model": "GPT-5.6 Sol", ...}
```

Manual install (no `install.sh`): copy `chatgpt_web_cli.py` + `start_proxy_chrome.sh`
into the **same directory** (the CLI discovers the launcher next to itself),
`pip install playwright`, and you are done. The scripts have **no other hardcoded
paths** and are location-independent.

---

## Login state

The browser profile lives in `$CHROME_DATA` (default `/tmp/chrome-proxy`).

- **First time**: the profile is empty → `status` reports `logged_in: false`.
  Log in manually via the CDP tab:
  ```bash
  # find the page target, then open it in a normal browser:
  curl -s http://127.0.0.1:9222/json | grep -o 'http://[^"]*devtools[^"]*' | head -1
  # OR drive it with playwright from Python: connect_over_cdp, page.goto("https://chatgpt.com"),
  # then let a human complete the login in the same profile.
  ```
  Practical approach on a headless server: use `--headless` only **after** the
  profile is logged in — log in once from a visible Chrome started with the same
  `--user-data-dir` and `--proxy-server` flags, then switch to headless.
  Alternatively import cookies via CDP `Network.setCookie` for each session.
- **After a machine reboot**: `/tmp/chrome-proxy` is wiped → cookies are gone.
  Re-import them (copy the profile from persistent storage) or re-login.
- `logged_in: false` from `status` while the browser is up = profile lost →
  re-import cookies, don't "fix" the browser.

---

## CLI contract

```sh
python3 chatgpt_web_cli.py ask "<question>" [--search] [--model NAME] [--effort instant|medium|high] [--timeout SEC] [--stall-timeout SEC] [--reuse-chat]
python3 chatgpt_web_cli.py status
python3 chatgpt_web_cli.py ensure-browser
```

- **stdout**: exactly ONE line of JSON. **stderr**: progress logs (discardable).
- Success: `{"success": true, "answer", "model", "effort", "search", "stalled", "elapsed_s", "url"}`
- Failure: exit 1 + `{"success": false, "error", "partial"?}` (partial may hold truncated text)
- `stalled: true` = the SSE stream tail hung; the bridge clicked stop and kept
  the rendered text. The tail MAY be truncated — relay the flag, don't hide it.

### Timing expectations (measured)

- Simple marker question: 15–75 s. With `--search`: ~20–90 s.
- High-effort thinking produces **no answer text for 1–4 min** — normal. The
  wait loop only arms stall detection once real answer text exists.
- Long architecture review: ~250 s. Use `--timeout 300` (default 600) or `420` for reviews.

---

## Adapters

All three adapters call the same CLI — install the core first.

### Hermes Agent plugin

```bash
mkdir -p ~/.hermes/plugins/chatgpt-web
cp adapters/hermes/* ~/.hermes/plugins/chatgpt-web/
# restart hermes → tools chatgpt_ask + chatgpt_web_status appear
```
Requires `playwright` importable by the interpreter Hermes runs under
(`uv pip install --python <hermes-venv-python> playwright` for uv-managed venvs).

### Pi coding agent extension

```bash
mkdir -p ~/.pi/agent/extensions
cp adapters/pi/chatgpt-web.ts ~/.pi/agent/extensions/
```
Registers the `chatgpt_ask` tool with a complex-question policy (ambiguous /
high-risk / repeated-error → ask the user first).

### Kimi Code plugin

```bash
cp -r adapters/kimi ~/.kimi-code/plugins-src/ask-chatgpt
# then in the Kimi TUI: /plugins install
```
No `ask_user` tool (per design). The skill/command reference
`$HOME/.hermes/scripts/chatgpt_web_cli.py` — adjust if you installed elsewhere.

---

## Verification recipes

```bash
# Smoke: marker question (answer must echo the marker)
python3 chatgpt_web_cli.py ask '只回复 CHATGPT_PLUGIN_OK' --timeout 150

# Search regression: date question with --search returns current date + sources
python3 chatgpt_web_cli.py ask '今天的日期？请搜索后回答' --search --timeout 150

# Long thinking: a multi-paragraph review prompt must NOT stall during the
# 1–4 min text-less thinking phase, and must return the full markdown body.
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'playwright'` | install it in the interpreter that runs the CLI (`pip install playwright`) |
| `net::ERR_PROXY_CONNECTION_FAILED` | proxy port mismatch — check `start_proxy_chrome.sh` `PROXY_URL` vs your actual proxy port |
| `net::ERR_CONNECTION_CLOSED` / `HTTP 403` | proxy is reachable but upstream is dead (check `curl -x $PROXY https://www.google.com`), or Cloudflare blocked a plain curl UA (use the browser, not curl) |
| `logged_in: false` | profile cookies missing (first run or reboot wiped `/tmp/chrome-proxy`) — log in / re-import cookies |
| Answer stuck with stop-button visible | SSE tail stall — the CLI auto-clicks stop and returns `stalled: true`; do not "fix" by raising timeouts |
| `"Thinking"` returned as the answer | extraction grabbed the thinking indicator — should not happen (`.markdown` preferred); report as a bug |
| Chrome dies | rerun `ensure-browser` / `start_proxy_chrome.sh` |

---

## Security notes

- Never include credentials, cookies, tokens, or non-exportable code/data **in the question**.
- The Pi extension redacts secrets from tool output; other adapters surface `error` verbatim — keep questions clean.
- Your ChatGPT account is a paid web subscription; treat the session as private infrastructure (don't share the profile, don't post questions containing secrets).

## License

MIT
