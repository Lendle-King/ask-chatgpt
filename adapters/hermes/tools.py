"""ChatGPT-web tools for Hermes (registered via plugins/chatgpt-web).

Thin wrapper around ~/.hermes/scripts/chatgpt_web_cli.py, which drives the
logged-in Chrome (CDP :9222) that start_proxy_chrome.sh manages. The same CLI
is directly usable by Pi or any shell, so both agents share one driver.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hermes_constants import get_hermes_home
from tools.registry import tool_error, tool_result


def _script_path(name: str) -> Path:
    return get_hermes_home() / "scripts" / name


# Hermes' default concurrent-tool timeout is 420s; keep tool default below it.
DEFAULT_TIMEOUT = 360
VALID_EFFORTS = {"instant", "medium", "high"}
README_URL = "https://github.com/Lendle-King/ask-chatgpt#readme"

def _readme_hint() -> str:
    """Guide agents to the setup docs when the bridge is not configured."""
    return (f"If this is the first call or setup is incomplete, follow the "
            f"README: {README_URL}")

def _run_cli(argv: list[str], timeout_s: int) -> dict:
    """Run chatgpt_web_cli.py and parse its single JSON stdout line."""
    try:
        proc = subprocess.run(
            [sys.executable, _script_path("chatgpt_web_cli.py"), *argv],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"success": False,
                "error": f"CLI timed out after {timeout_s}s (ChatGPT may still be "
                         "generating; retry with a longer --timeout or check the page)."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"CLI launch failed: {type(exc).__name__}: {exc}"}

    # stdout is one JSON object; tolerate stray log lines by scanning backwards.
    data = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if data is None:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        return {"success": False,
                "error": f"CLI produced no JSON (rc={proc.returncode}): {' | '.join(tail)}"}
    return data


def _browser_reachable() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3):
            return True
    except Exception:
        return False


def _check_chatgpt_web_available() -> bool:
    return _browser_reachable()


def _handle_chatgpt_ask(args: dict, **kw) -> str:
    question = str(args.get("question") or "").strip()
    if not question:
        return tool_error("question is required")

    if not _browser_reachable():
        return tool_error(
            "ChatGPT browser not reachable on CDP :9222. Start it with: "
            f"bash {_script_path('start_proxy_chrome.sh')} (requires the "
            "imported login cookies). " + _readme_hint())

    search = bool(args.get("search", False))
    model = str(args.get("model") or "GPT-5.6 Sol").strip()
    effort = str(args.get("effort") or "high").strip().lower()
    if effort not in VALID_EFFORTS:
        return tool_error(f"effort must be one of {sorted(VALID_EFFORTS)}")
    try:
        timeout = int(args.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(30, min(timeout, 900))

    argv = ["ask", question, "--model", model, "--effort", effort,
            "--timeout", str(timeout)]
    if search:
        argv.append("--search")
    if args.get("reuse_chat"):
        argv.append("--reuse-chat")

    data = _run_cli(argv, timeout_s=timeout + 120)
    if not data.get("success"):
        return tool_error(data.get("error") or "chatgpt-web ask failed",
                          detail=data)
    # Keep the payload lean for the model: answer + provenance.
    return tool_result({
        "answer": data.get("answer"),
        "model": data.get("model"),
        "effort": data.get("effort"),
        "search": data.get("search"),
        "url": data.get("url"),
        "elapsed_s": data.get("elapsed_s"),
    })


def _handle_chatgpt_web_status(args: dict, **kw) -> str:
    if not _browser_reachable():
        return tool_result({
            "browser": "down",
            "hint": f"run: bash {_script_path('start_proxy_chrome.sh')}",
            "docs": README_URL,
        })
    data = _run_cli(["status"], timeout_s=90)
    if not data.get("success"):
        return tool_error(data.get("error") or "status failed",
                          detail=data,
                          docs=README_URL)
    return tool_result({"browser": "up", **data})


COMMON_STR = {"type": "string"}

CHATGPT_ASK_SCHEMA = {
    "name": "chatgpt_ask",
    "description": (
        "Ask the ChatGPT web UI (chatgpt.com) a question and return its answer. "
        "Uses the user's logged-in account with model GPT-5.6 Sol at max thinking "
        "effort (High) by default. Enable search=true to turn on ChatGPT's web "
        "search for current/real-time info. Answers can take 1-5 minutes when "
        "thinking effort is high — prefer this for hard reasoning or deep "
        "research questions, not quick lookups."),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string",
                         "description": "The question/prompt to send to ChatGPT."},
            "search": {"type": "boolean",
                       "description": "Enable ChatGPT web search (for real-time/current info). Default false."},
            "model": {"type": "string",
                      "description": "ChatGPT model name as shown in the UI. Default 'GPT-5.6 Sol'."},
            "effort": {"type": "string", "enum": ["instant", "medium", "high"],
                       "description": "Thinking effort. Default 'high' (max)."},
            "timeout": {"type": "integer",
                        "description": "Seconds to wait for the answer. Default 360."},
            "reuse_chat": {"type": "boolean",
                           "description": "Ask in the current conversation instead of a fresh chat. Default false."},
        },
        "required": ["question"],
    },
}

CHATGPT_WEB_STATUS_SCHEMA = {
    "name": "chatgpt_web_status",
    "description": "Check the ChatGPT-web browser (CDP :9222), login state, and current model/effort.",
    "parameters": {"type": "object", "properties": {}},
}
