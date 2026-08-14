#!/usr/bin/env python3
"""chatgpt_web_cli.py — Ask questions to the ChatGPT web UI (chatgpt.com) via CDP.

Drives the logged-in Chrome instance started by start_proxy_chrome.sh
(CDP on :9222, anti-detect flags). Works standalone (Hermes,
Pi, or any shell) — outputs a single JSON object on stdout.

Usage:
  chatgpt_web_cli.py ask "<question>" [--search] [--model NAME] [--effort LVL]
                        [--timeout SEC] [--reuse-chat]
  chatgpt_web_cli.py status
  chatgpt_web_cli.py ensure-browser

Defaults: model = "GPT-5.6 Sol", effort = "high" (max thinking level as of 2026-08).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path


def _ensure_loopback_no_proxy():
    """Keep local CDP discovery out of the external HTTP proxy."""
    local = ("127.0.0.1", "localhost", "::1")
    for key in ("NO_PROXY", "no_proxy"):
        values = [item.strip() for item in os.environ.get(key, "").split(",") if item.strip()]
        known = {item.casefold() for item in values}
        values.extend(item for item in local if item.casefold() not in known)
        os.environ[key] = ",".join(values)


_ensure_loopback_no_proxy()

CDP_URL = "http://127.0.0.1:9222"
SCRIPT_DIR = Path(__file__).resolve().parent
START_SCRIPT = SCRIPT_DIR / "start_proxy_chrome.sh"
CHATGPT_HOME = "https://chatgpt.com/"
DEFAULT_MODEL = "GPT-5.6 Sol"
DEFAULT_EFFORT = "high"
EFFORT_OPTIONS = {"instant": "Instant", "medium": "Medium", "high": "High"}
README_URL = "https://github.com/Lendle-King/ask-chatgpt#readme"


def _readme_hint():
    return (f"If this is the first call or setup is incomplete, follow the "
            f"README: {README_URL}")

# ---------------------------------------------------------------------------
# JS helpers injected into the page. Each returns a JSON-serializable value.
# ---------------------------------------------------------------------------

# React menus respond to real pointer sequences, not synthetic .click().
FULLCLICK = """
const __fullClick = (el) => {
  const r = el.getBoundingClientRect();
  const x = r.left + r.width/2, y = r.top + r.height/2;
  const opts = {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0};
  el.dispatchEvent(new PointerEvent('pointerover', opts));
  el.dispatchEvent(new PointerEvent('pointerenter', opts));
  el.dispatchEvent(new PointerEvent('pointerdown', opts));
  el.dispatchEvent(new MouseEvent('mousedown', opts));
  el.dispatchEvent(new PointerEvent('pointerup', opts));
  el.dispatchEvent(new MouseEvent('mouseup', opts));
  el.dispatchEvent(new MouseEvent('click', opts));
};
const __txt = (el) => (el.innerText || '').trim().replace(/\\s+/g, ' ');
"""

JS_STATE = """() => {
  const tb = document.querySelector('textarea[aria-label*="Chat"]');
  const pill = [...document.querySelectorAll('button.__composer-pill, button[class*="composer-pill"]')]
    .map(b => (b.innerText||'').trim()).find(t => t);
  const stop = !!document.querySelector('[data-testid="stop-button"]');
  return {
    url: location.href,
    hasComposer: !!tb,
    placeholder: tb ? tb.placeholder : null,
    composerPill: pill || null,
    generating: stop,
  };
}"""

# Open the effort/model menu (the composer pill button, e.g. "High" / "Medium").
JS_OPEN_COMPOSER_MENU = FULLCLICK + """() => {
  const btn = [...document.querySelectorAll('button')]
    .find(b => (b.className||'').includes('composer-pill') || /^(High|Medium|Instant|Light)$/.test(__txt(b)));
  if (!btn) return {ok: false, err: 'composer pill button not found'};
  __fullClick(btn);
  return {ok: true, label: __txt(btn)};
}"""

# Inside the open menu: expand Advanced if needed, then expand `Model ...` and
# click the radio whose text starts with the wanted model name. Same for Effort.
JS_SELECT_MENU = FULLCLICK + """(args) => {
  const {kind, want} = args;           // kind: 'Model' | 'Effort'
  const items = () => [...document.querySelectorAll('[role="menuitem"], [role="menuitemradio"]')];
  // 1) If an "Advanced" item exists and no Model/Effort item yet, click it.
  const adv = items().find(el => __txt(el) === 'Advanced');
  if (adv && !items().some(el => __txt(el).startsWith(kind))) {
    __fullClick(adv);
  }
  // 2) Click the "Model ..." / "Effort ..." item to expand its submenu.
  const head = items().find(el => __txt(el).startsWith(kind + ' '));
  if (!head) return {ok: false, err: kind + ' menu item not found', have: items().map(el => __txt(el)).slice(0,10)};
  const current = __txt(head).slice(kind.length).trim();
  if (current.toLowerCase() === want.toLowerCase()) {
    return {ok: true, already: true, current};
  }
  __fullClick(head);
  // 3) The submenu opens; click the matching radio.
  return new Promise(resolve => setTimeout(() => {
    const radios = [...document.querySelectorAll('[role="menuitemradio"]')];
    const target = radios.find(el => __txt(el).toLowerCase().startsWith(want.toLowerCase()));
    if (!target) return resolve({ok: false, err: 'radio "' + want + '" not found', have: radios.map(el => __txt(el))});
    __fullClick(target);
    resolve({ok: true, clicked: __txt(target)});
  }, 500));
}"""

JS_ENABLE_SEARCH = FULLCLICK + """() => {
  // Open the + menu.
  const plus = document.querySelector('[data-testid="composer-plus-btn"]');
  if (!plus) return {ok: false, err: 'plus button not found'};
  __fullClick(plus);
  return new Promise(resolve => setTimeout(() => {
    // Menu items render as div rows: "<Title>\\n<desc>". Find Web search row.
    const rows = [...document.querySelectorAll('div')].filter(el => {
      const t = __txt(el);
      return t.startsWith('Web search') && el.getBoundingClientRect().width > 0 && el.children.length <= 4;
    });
    if (!rows.length) { resolve({ok: false, err: 'Web search menu item not found'}); return; }
    // Click the innermost match so the row's click handler fires.
    const target = rows.sort((a, b) => a.contains(b) ? 1 : -1)[0];
    __fullClick(target);
    setTimeout(() => {
      const tb = document.querySelector('textarea[aria-label*="Chat"]');
      resolve({ok: true, placeholder: tb ? tb.placeholder : null});
    }, 500);
  }, 700));
}"""

JS_ASK = """(question) => {
  const pm = document.querySelector('.ProseMirror[contenteditable="true"]')
          || document.querySelector('[contenteditable="true"]');
  if (!pm) return {ok: false, err: 'ProseMirror editor not found'};
  pm.focus();
  document.execCommand('insertText', false, question);
  return new Promise(resolve => setTimeout(() => {
    const send = document.querySelector('[data-testid="send-button"]');
    if (!send || send.hasAttribute('disabled')) {
      resolve({ok: false, err: 'send button not ready', content: pm.innerText.slice(0, 80)});
      return;
    }
    send.click();
    resolve({ok: true});
  }, 500));
}"""

JS_READ_ANSWER = """() => {
  const stop = !!document.querySelector('[data-testid="stop-button"]');
  const msgs = [...document.querySelectorAll('[data-message-author-role="assistant"]')];
  const last = msgs.length ? msgs[msgs.length - 1] : null;
  if (!last) return {generating: stop, count: msgs.length, text: ''};
  // Prefer the rendered markdown answer. While ChatGPT is still "Thinking",
  // the message element only holds the thought indicator ("Thinking",
  // "Thought for ..."), which must NOT be mistaken for the answer text.
  const md = [...last.querySelectorAll('.markdown')];
  let text = md.length ? md.map(el => el.innerText).join('\\n') : '';
  if (!text.trim()) {
    const t = (last.innerText || '').trim();
    if (t && !/^(Thinking|Thought for|Reasoning|Searching)/i.test(t)) text = t;
  }
  return {generating: stop, count: msgs.length, text: text.trim()};
}"""

JS_CLICK_STOP = FULLCLICK + """() => {
  const b = document.querySelector('[data-testid="stop-button"]');
  if (!b) return {ok: false, err: 'stop button not found'};
  __fullClick(b);
  return {ok: true};
}"""


def log(msg):
    sys.stderr.write(f"[chatgpt-web {time.strftime('%H:%M:%S')}] {msg}\n")
    sys.stderr.flush()


def fail(msg, **extra):
    log(f"ERROR: {msg}")
    print(json.dumps({"success": False, "error": msg, **extra}, ensure_ascii=False))
    sys.exit(1)


def connect(timeout_ms=8000, attempts=3):
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    last_err = None
    for i in range(attempts):
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=timeout_ms)
            return pw, browser
        except Exception as e:
            last_err = e
            log(f"connect attempt {i + 1}/{attempts} failed: {e}")
            time.sleep(2)
    pw.stop()
    fail(f"cannot connect to Chrome at {CDP_URL}: {last_err}. "
         f"Run {START_SCRIPT} first. {_readme_hint()}")


def get_page(browser):
    for ctx in browser.contexts:
        for page in ctx.pages:
            if page.url.startswith("https://chatgpt.com"):
                return page
    ctx = browser.contexts[0] if browser.contexts else None
    if ctx is None:
        fail("no browser context found")
    page = ctx.new_page()
    return page


def cmd_status():
    import requests
    try:
        r = requests.get(CDP_URL + "/json/version", timeout=3)
        chrome = r.json().get("Browser", "?")
    except Exception as e:
        fail(f"Chrome not reachable: {e}. Run start_proxy_chrome.sh. "
             f"{_readme_hint()}")
    pw, browser = connect()
    try:
        page = get_page(browser)
        if not page.url.startswith("https://chatgpt.com"):
            page.goto(CHATGPT_HOME, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        st = page.evaluate(JS_STATE)
        logged_in = page.evaluate(
            """() => {
                const visible = el => {
                  const style = getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style.display !== 'none' && style.visibility !== 'hidden'
                    && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
                };
                const label = el => [el.innerText, el.getAttribute('aria-label'),
                  el.getAttribute('title')].filter(Boolean).join(' ').trim();
                const controls = [...document.querySelectorAll(
                  'button, a, [role="button"], [role="link"]')];
                // An auth CTA takes precedence over any stale/ambiguous page content.
                const auth_prompt = controls.some(el => visible(el) &&
                  /\\b(?:log\\s*in|sign\\s*up|login|signup)\\b/i.test(label(el)));
                if (auth_prompt) return false;

                const welcome = [...document.querySelectorAll(
                  'h1, h2, [role="heading"]')].some(el => visible(el) &&
                  /^Hey,\\s*.+?\\s+Ready to dive in\\b/i.test(label(el)));
                const account = [...document.querySelectorAll(
                  '[data-testid="accounts-profile-button"], [aria-label*="profile menu" i], [aria-label*="account" i]')].some(visible);
                return welcome || account;
            }"""
        )
        print(json.dumps({"success": True, "chrome": chrome, "url": st["url"],
                          "logged_in": logged_in, "composer": st["hasComposer"],
                          "composerPill": st["composerPill"]}, ensure_ascii=False))
    finally:
        pw.stop()


def cmd_ensure_browser():
    import subprocess
    r = subprocess.run([str(START_SCRIPT)],
                       capture_output=True, text=True, timeout=30)
    print(json.dumps({"success": r.returncode == 0, "out": r.stdout.strip(),
                      "err": r.stderr.strip()}, ensure_ascii=False))
    sys.exit(r.returncode)


def set_model_effort(page, model, effort, steps):
    """Open composer menu and set Model/Effort if different from target."""
    state = page.evaluate(JS_STATE)
    pill = (state.get("composerPill") or "")
    want_effort_label = EFFORT_OPTIONS.get(effort.lower())
    # The pill shows current effort (e.g. "High"). Model lives inside the menu.
    r = page.evaluate(JS_OPEN_COMPOSER_MENU)
    if not r.get("ok"):
        fail("cannot open composer menu", detail=r)
    page.wait_for_timeout(700)
    # If an "Advanced" entry is present, expand it first.
    adv = page.evaluate(FULLCLICK + """() => {
      const adv = [...document.querySelectorAll('[role="menuitem"]')]
        .find(el => __txt(el) === 'Advanced');
      if (adv) { __fullClick(adv); return true; }
      return false;
    }""")
    if adv:
        steps.append("advanced")
        page.wait_for_timeout(600)
    if model:
        r = page.evaluate(JS_SELECT_MENU, {"kind": "Model", "want": model})
        steps.append({"model": r})
        if not r.get("ok"):
            fail("model select failed", detail=r)
        page.wait_for_timeout(700)
        # model submenu replaced the menu; effort submenu must be re-opened
        if effort and not r.get("already"):
            page.evaluate(JS_OPEN_COMPOSER_MENU)
            page.wait_for_timeout(700)
            page.evaluate(FULLCLICK + """() => {
              const adv = [...document.querySelectorAll('[role="menuitem"]')]
                .find(el => __txt(el) === 'Advanced');
              if (adv) __fullClick(adv);
            }""")
            page.wait_for_timeout(600)
    if effort and want_effort_label:
        r = page.evaluate(JS_SELECT_MENU, {"kind": "Effort", "want": want_effort_label})
        steps.append({"effort": r})
        if not r.get("ok"):
            fail("effort select failed", detail=r)
    # Close any leftover menu.
    page.keyboard.press("Escape")


def cmd_ask(args):
    pw, browser = connect()
    try:
        page = get_page(browser)
        log(f"connected, url={page.url}")
        steps = []
        # 1) fresh chat unless --reuse-chat
        if not args.reuse_chat or not page.url.startswith("https://chatgpt.com/c/"):
            page.goto(CHATGPT_HOME, wait_until="domcontentloaded", timeout=60000)
            log("navigated to home")
        page.wait_for_selector('textarea[aria-label*="Chat"]', timeout=30000)
        # The composer pill (Effort button) renders after the textarea.
        try:
            page.wait_for_selector('button[class*="composer-pill"]', timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)
        log("composer ready")

        # 2) model + effort
        set_model_effort(page, args.model, args.effort, steps)
        log(f"model/effort set: {steps}")
        page.wait_for_timeout(500)

        # 3) optional web search
        search_on = False
        if args.search:
            r = page.evaluate(JS_ENABLE_SEARCH)
            steps.append({"search": r})
            log(f"search toggle: {r}")
            if not r.get("ok"):
                fail("enable web search failed", detail=r)
            search_on = "search" in (r.get("placeholder") or "").lower()

        # 4) type + send
        t0 = time.time()
        r = page.evaluate(JS_ASK, args.question)
        if not r.get("ok"):
            fail("ask failed", detail=r)
        log("question sent")

        # 5) wait for generation: stop-button appears then disappears,
        #    plus text-stability fallback and stream-stall recovery.
        deadline = t0 + args.timeout
        started = False
        stalled = False
        last_text, stable_since = "", time.time()
        text_changed_at = time.time()

        def read():
            try:
                return page.evaluate(JS_READ_ANSWER)
            except Exception:
                # navigation between home and /c/<id> can destroy the context
                return {"generating": True, "count": 0, "text": ""}

        while time.time() < deadline:
            st = read()
            now = time.time()
            if st["text"] and st["text"] != last_text:
                last_text, text_changed_at = st["text"], now
            if st["generating"]:
                started = True
                stable_since = now
                # Stream stall: stop-button persists but the answer text has
                # not changed for --stall-timeout seconds (SSE tail stall).
                # Click stop and keep the generated text instead of hanging
                # until the overall timeout.
                if last_text and now - text_changed_at >= args.stall_timeout:
                    log(f"stream stalled {int(now - text_changed_at)}s "
                        f"with len={len(last_text)}; clicking stop")
                    r = page.evaluate(JS_CLICK_STOP)
                    log(f"stop click: {r}")
                    page.wait_for_timeout(2000)
                    # let the stop-button disappear / text settle (short window)
                    for _ in range(15):
                        st2 = read()
                        if not st2["generating"]:
                            break
                        page.wait_for_timeout(1000)
                    st = st2 if (st2.get("text") or "").strip() else {
                        **st2, "text": last_text}
                    stalled = True
                    break
            else:
                if st["text"] != last_text:
                    last_text, stable_since = st["text"], now
                # done: generation stopped (or never started) and text stable 4s
                if (started or st["count"] > 0) and last_text and now - stable_since >= 4:
                    # confirm twice before accepting completion
                    page.wait_for_timeout(1500)
                    st2 = read()
                    if not st2["generating"] and (st2["text"] or "").strip():
                        st = st2
                        break
                    stable_since = time.time()
            if int(now) % 15 == 0:
                log(f"waiting... gen={st['generating']} len={len(st['text'])} "
                    f"started={started} idle={int(now - text_changed_at)}s")
            page.wait_for_timeout(1000)
        else:
            fail("timeout waiting for answer", partial=last_text[:500])
        answer = (st.get("text") or "").strip()
        if not answer:
            fail("no assistant answer found", state=st)
        print(json.dumps({
            "success": True,
            "answer": answer,
            "url": page.url,
            "model": args.model,
            "effort": args.effort,
            "search": search_on,
            "stalled": stalled,
            "elapsed_s": round(time.time() - t0, 1),
            "steps": steps,
        }, ensure_ascii=False))
    finally:
        pw.stop()


def main():
    ap = argparse.ArgumentParser(description="Ask ChatGPT web UI via CDP")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--search", action="store_true", help="enable web search")
    a.add_argument("--model", default=DEFAULT_MODEL)
    a.add_argument("--effort", default=DEFAULT_EFFORT,
                   choices=list(EFFORT_OPTIONS))
    a.add_argument("--timeout", type=int, default=600)
    a.add_argument("--stall-timeout", type=int, default=45,
                   help="seconds with no answer-text change while generating "
                        "before clicking stop (stream-stall recovery)")
    a.add_argument("--reuse-chat", action="store_true",
                   help="do not start a new conversation")
    sub.add_parser("status")
    sub.add_parser("ensure-browser")
    args = ap.parse_args()
    if args.cmd == "ask":
        cmd_ask(args)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "ensure-browser":
        cmd_ensure_browser()


if __name__ == "__main__":
    main()
