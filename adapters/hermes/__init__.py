"""ChatGPT-web plugin — ask chatgpt.com via the logged-in CDP browser.

Registers 2 tools (chatgpt_ask, chatgpt_web_status) into the ``chatgpt_web``
toolset. The heavy lifting lives in ~/.hermes/scripts/chatgpt_web_cli.py so
Pi coding agents can call the same driver from a plain shell.
"""

from __future__ import annotations

from .tools import (
    CHATGPT_ASK_SCHEMA,
    CHATGPT_WEB_STATUS_SCHEMA,
    _check_chatgpt_web_available,
    _handle_chatgpt_ask,
    _handle_chatgpt_web_status,
)

_TOOLS = (
    ("chatgpt_ask", CHATGPT_ASK_SCHEMA, _handle_chatgpt_ask, "💬"),
    ("chatgpt_web_status", CHATGPT_WEB_STATUS_SCHEMA, _handle_chatgpt_web_status, "🛰️"),
)


def register(ctx) -> None:
    """Register all ChatGPT-web tools. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="chatgpt_web",
            schema=schema,
            handler=handler,
            check_fn=_check_chatgpt_web_available,
            emoji=emoji,
        )
