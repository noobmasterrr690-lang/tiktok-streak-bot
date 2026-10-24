"""
TikTok Daily Streak Automation Script (Playwright Async API).

Usage examples:
    python main.py --login       # Log into TikTok manually and save persistent session
    python main.py --dry-run     # Detect active streak chats without sending messages
    python main.py --debug-dom   # Dump HTML & text of top 5 sidebar chats to inspect selectors
    python main.py               # Run streak automation (headed mode by default)
    python main.py --headless    # Run streak automation in headless mode
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    ElementHandle,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

import config

# Ensure UTF-8 console output on Windows so emoji characters never raise UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Configure console + file logging for unattended background / cloud execution
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.AUTOMATION_LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("tiktok_streak")

STEALTH_INIT_SCRIPT = """
// Mask navigator.webdriver to evade basic automation checks
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});

// Provide standard Chrome runtime object if absent
window.chrome = window.chrome || {
    runtime: {},
};

// Spoof standard languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});
"""


@dataclass
class DetectedStreakChat:
    """Represents a sidebar chat item identified as having an active streak."""

    index: int
    name: str
    reason: str
    element: ElementHandle


# ==============================================================================
# DAILY LOCKFILE / LOGGING HELPERS
# ==============================================================================
def load_messaged_today(log_path: str = config.STREAK_LOG_FILE) -> set[str]:
    """
    Load the set of chat names already messaged today (YYYY-MM-DD) from streak_log.json.
    If the file doesn't exist or is from a previous date, returns an empty set.
    """
    today_str = date.today().isoformat()
    path = Path(log_path)

    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("date") == today_str:
            chats = data.get("messaged_chats", [])
            if isinstance(chats, list):
                return set(str(c) for c in chats)
    except Exception as exc:
        logger.warning("Could not parse %s (%s). Starting fresh log for today.", log_path, exc)

    return set()


def record_messaged_today(
    chat_name: str,
    messaged_set: set[str],
    log_path: str = config.STREAK_LOG_FILE,
) -> None:
    """Record a newly messaged chat user into streak_log.json for today's date."""
    today_str = date.today().isoformat()
    messaged_set.add(chat_name)
    payload = {
        "date": today_str,
        "messaged_chats": sorted(messaged_set),
    }
    Path(log_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ==============================================================================
# BROWSER CONTEXT MANAGEMENT
# ==============================================================================
async def create_browser_context(
    playwright_instance,
    headless: bool,
) -> tuple[Optional[Browser], BrowserContext]:
    """
    Launch either:
      1) A cloud/stateless Chromium context pre-populated from TIKTOK_STORAGE_STATE
         (used when running on GitHub Actions / cloud servers with PC turned off), OR
      2) A local persistent Chromium context (`./tiktok_profile`) so cookies and
         IndexedDB survive across local runs.
    """
    env_storage_state = os.environ.get("TIKTOK_STORAGE_STATE", "").strip()
    if env_storage_state:
        state_path = Path(config.STORAGE_STATE_FILE).resolve()
        try:
            # Validate JSON (or decode base64 if encoded)
            if not env_storage_state.startswith("{"):
                import base64
                env_storage_state = base64.b64decode(env_storage_state).decode("utf-8")
            parsed_state = json.loads(env_storage_state)
            state_path.write_text(json.dumps(parsed_state, ensure_ascii=False), encoding="utf-8")
            logger.info("Loaded session from TIKTOK_STORAGE_STATE env var into %s (headless=%s)", state_path, headless)
            browser = await playwright_instance.chromium.launch(
                headless=headless,
                args=config.BROWSER_ARGS,
            )
            context = await browser.new_context(
                storage_state=str(state_path),
                user_agent=config.USER_AGENT,
                viewport=config.VIEWPORT,
                locale="en-US",
            )
            await context.add_init_script(STEALTH_INIT_SCRIPT)
            return browser, context
        except Exception as exc:
            logger.error(
                "TIKTOK_STORAGE_STATE secret is not valid JSON (%s). "
                "Please re-paste the compact storage_state.json into GitHub Secrets!",
                exc,
            )
            sys.exit(1)

    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        logger.error(
            "Running inside GitHub Actions, but TIKTOK_STORAGE_STATE secret is empty! "
            "Please add the TIKTOK_STORAGE_STATE secret in your GitHub repo Settings -> Secrets -> Actions."
        )
        sys.exit(1)

    profile_dir = Path(config.USER_DATA_DIR).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Launching Chromium with persistent profile: %s (headless=%s)", profile_dir, headless)

    context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        user_agent=config.USER_AGENT,
        viewport=config.VIEWPORT,
        args=config.BROWSER_ARGS,
        locale="en-US",
    )
    await context.add_init_script(STEALTH_INIT_SCRIPT)
    return None, context


async def export_storage_state(context: BrowserContext) -> None:
    """
    Export cookies and essential localStorage to storage_state.json for cloud/GitHub Actions use.
    Strips bulky TikTok translation/telemetry caches (`text.*`, `f_s_1`, `ppf_eligibility_v2`)
    so the file stays under ~8 KB (well below GitHub's 48 KB secret limit and Linux's 128 KB env limit).
    """
    try:
        state_path = Path(config.STORAGE_STATE_FILE).resolve()
        raw_state = await context.storage_state()
        for origin_entry in raw_state.get("origins", []):
            ls = origin_entry.get("localStorage", [])
            origin_entry["localStorage"] = [
                item
                for item in ls
                if not item.get("name", "").startswith(("text.", "version.", "f_s_", "ppf_eligibility"))
                and len(item.get("value", "")) < 4000
            ]
        state_path.write_text(
            json.dumps(raw_state, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        logger.info(
            "Exported compact cloud-ready session state to %s (%d bytes)",
            state_path,
            state_path.stat().st_size,
        )
    except PlaywrightError as exc:
        logger.debug("Could not export storage_state.json: %s", exc)


async def get_active_page(context: BrowserContext) -> Page:
    """Return the first open page in the persistent context or create a new one."""
    if context.pages:
        return context.pages[0]
    return await context.new_page()


# ==============================================================================
# MODE 1: MANUAL LOGIN (--login)
# ==============================================================================
async def run_login_flow() -> None:
    """
    Launch browser in headed mode, navigate to TikTok login page, and wait for the user
    to complete authentication (e.g., QR code scan) and either press Enter or close the browser.
    """
    async with async_playwright() as p:
        browser, context = await create_browser_context(p, headless=False)
        page = await get_active_page(context)

        logger.info("Navigating to %s ...", config.TIKTOK_LOGIN_URL)
        try:
            await page.goto(
                config.TIKTOK_LOGIN_URL,
                wait_until="domcontentloaded",
                timeout=config.NAVIGATION_TIMEOUT_MS,
            )
        except PlaywrightError as exc:
            logger.warning("Initial navigation warning: %s", exc)

        print("\n" + "=" * 72)
        print("  MANUAL LOGIN MODE")
        print("=" * 72)
        print("1. Log in to your TikTok account in the opened Chromium window (e.g. via QR code).")
        print("2. Wait until you are redirected to your feed or https://www.tiktok.com/messages.")
        print("3. Once logged in, press ENTER here in the terminal (or close the browser window)")
        print("   to save your session inside ./tiktok_profile and storage_state.json.")
        print("=" * 72 + "\n")

        browser_closed_event = asyncio.Event()
        context.on("close", lambda _: browser_closed_event.set())
        page.on("close", lambda _: browser_closed_event.set())

        loop = asyncio.get_running_loop()
        enter_task = loop.run_in_executor(None, sys.stdin.readline)
        close_wait_task = asyncio.create_task(browser_closed_event.wait())

        done, pending = await asyncio.wait(
            [enter_task, close_wait_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        await export_storage_state(context)

        try:
            await context.close()
            if browser:
                await browser.close()
        except PlaywrightError:
            pass

        logger.info("Login session saved to %s.", Path(config.USER_DATA_DIR).resolve())


async def run_export_session_only() -> None:
    """Export the existing persistent profile's cookies & localStorage into storage_state.json."""
    async with async_playwright() as p:
        browser, context = await create_browser_context(p, headless=True)
        page = await get_active_page(context)
        try:
            await page.goto(
                config.TIKTOK_MESSAGES_URL,
                wait_until="domcontentloaded",
                timeout=config.NAVIGATION_TIMEOUT_MS,
            )
            await asyncio.sleep(3.0)
            await export_storage_state(context)
        finally:
            try:
                await context.close()
                if browser:
                    await browser.close()
            except PlaywrightError:
                pass


# ==============================================================================
# SIDEBAR LOADING, SCROLLING & DOM HELPERS
# ==============================================================================
async def wait_for_chat_sidebar(page: Page) -> Optional[str]:
    """
    Wait for the conversation list items to appear in the left sidebar.
    Returns the matching selector string, or None if no chat items loaded within timeout.
    """
    combined_selector = ", ".join(config.CHAT_LIST_ITEM_SELECTORS)
    try:
        await page.wait_for_selector(
            combined_selector,
            state="attached",
            timeout=config.SIDEBAR_LOAD_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        return None

    for selector in config.CHAT_LIST_ITEM_SELECTORS:
        items = await page.query_selector_all(selector)
        if items:
            # Wait briefly if the virtualized list is still hydrating its initial batch
            if len(items) < 5:
                await asyncio.sleep(2.5)
                items = await page.query_selector_all(selector)
            logger.info("Found %d chat item(s) using selector: %s", len(items), selector)
            return selector

    return None


async def scroll_conversation_sidebar(page: Page, item_selector: str) -> None:
    """
    Scroll the left conversation list container slightly to ensure top conversations
    are rendered into the DOM, then scroll back to the top.
    """
    items = await page.query_selector_all(item_selector)
    if not items:
        return

    logger.info("Scrolling conversation sidebar slightly to ensure top chats are loaded...")
    try:
        first_item = items[0]
        box = await first_item.bounding_box()
        if box:
            await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            for _ in range(config.SIDEBAR_SCROLL_STEPS):
                await page.mouse.wheel(0, config.SIDEBAR_SCROLL_PIXELS)
                await asyncio.sleep(
                    random.uniform(config.SIDEBAR_SCROLL_PAUSE_MIN, config.SIDEBAR_SCROLL_PAUSE_MAX)
                )
            # Scroll back up so top conversations are in view
            for _ in range(config.SIDEBAR_SCROLL_STEPS):
                await page.mouse.wheel(0, -config.SIDEBAR_SCROLL_PIXELS)
                await asyncio.sleep(0.4)
    except PlaywrightError as exc:
        logger.debug("Sidebar scroll skipped due to minor DOM issue: %s", exc)


async def extract_chat_name(item: ElementHandle, fallback_index: int) -> str:
    """Extract the display name or username from a sidebar chat item."""
    for selector in config.CHAT_NICKNAME_SELECTORS:
        el = await item.query_selector(selector)
        if el:
            text = (await el.inner_text()).strip()
            if text:
                # Strip out trailing fire emoji or streak numbers if embedded inside the nickname node
                cleaned = text.split("\n")[0].strip()
                if cleaned:
                    return cleaned

    # Fallback: take the first non-empty line of the item's inner text
    try:
        raw_text = (await item.inner_text()).strip()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if lines:
            return lines[0]
    except PlaywrightError:
        pass

    return f"chat_item_{fallback_index}"


def is_within_lookback_days(time_str: str, max_days: int) -> tuple[bool, str]:
    """
    Determine whether a TikTok sidebar timestamp string represents activity today
    or within `max_days` (catching unlit / gray streaks that haven't been messaged today).
    """
    t = time_str.strip()
    if not t:
        return False, ""

    # 1. Today's timestamp (e.g. "21:45" or "9:45 PM")
    import re
    if re.match(r"^\d{1,2}:\d{2}(\s*[AP]M)?$", t, flags=re.IGNORECASE):
        return True, f"Active today ({t})"

    # 2. "Yesterday" or relative day strings (e.g. "Yesterday", "1d", "2d")
    t_lower = t.lower()
    if t_lower == "yesterday":
        return max_days >= 1, "Unlit/not flaming yet today (last active: Yesterday)"

    rel_match = re.match(r"^(\d+)\s*d$", t_lower)
    if rel_match:
        days_ago = int(rel_match.group(1))
        if days_ago <= max_days:
            return True, f"Unlit/not flaming yet (last active: {t} ago)"

    # 3. Calendar date formats used by TikTok Web (e.g. "10/21/2026" or "2026-10-21")
    today = date.today()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed_date = datetime.strptime(t, fmt).date()
            delta_days = (today - parsed_date).days
            if 0 <= delta_days <= max_days:
                state_label = (
                    "Active today"
                    if delta_days == 0
                    else f"Unlit/not flaming yet ({delta_days}d since last msg on {t})"
                )
                return True, state_label
        except ValueError:
            continue

    return False, ""


async def evaluate_streak_status(item: ElementHandle, chat_name: str) -> tuple[bool, str]:
    """
    Multi-layered streak detection for a single sidebar conversation item
    (supporting both lit/flaming streaks AND unlit/gray 'not flaming up' streaks):
      a) Check if the chat item contains '🔥'/'⏳' emoji text nodes or streak keywords
         (including unlit/paused streak notices when INCLUDE_UNLIT_STREAKS is True).
      b) Check if the chat item contains streak/flame SVGs, images, or attributes
         (both lit orange and unlit gray flame icons).
      c) Check if the chat name matches the FALLBACK_STREAK_USERS whitelist in config.py.
      d) Check if the chat is a 1-on-1 conversation (`data-conv-id^="0:1:"`) active today
         or within `STREAK_LOOKBACK_DAYS` (catching unlit streaks before a message is sent today).
    Returns (is_target_streak, match_reason).
    """
    include_unlit = getattr(config, "INCLUDE_UNLIT_STREAKS", True)

    try:
        full_item_text = (await item.inner_text()).strip()
        full_item_lower = full_item_text.lower()
    except PlaywrightError:
        full_item_text = ""
        full_item_lower = ""

    is_lost_or_unlit_text = "streak" in full_item_lower and (
        "lost" in full_item_lower or "ended" in full_item_lower or "restore" in full_item_lower
    )

    # 1. Check DOM/Text match for 🔥 / ⏳ emoji text nodes inside the chat item
    if not is_lost_or_unlit_text or include_unlit:
        try:
            has_emoji_text_node = await item.evaluate(
                """(el, indicators) => {
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
                    let node;
                    while ((node = walker.nextNode())) {
                        const val = node.nodeValue || '';
                        for (const indicator of indicators) {
                            if (val.includes(indicator)) {
                                return indicator;
                            }
                        }
                    }
                    return null;
                }""",
                config.STREAK_EMOJI_INDICATORS,
            )
            if has_emoji_text_node:
                return True, f"DOM text node contains '{has_emoji_text_node}'"
        except PlaywrightError:
            pass

        # 2. Check streak text keywords (e.g. "17-day Streak", unlit/paused streak notices)
        if include_unlit:
            for kw in getattr(config, "STREAK_TEXT_KEYWORDS", ["streak"]):
                if kw.lower() in full_item_lower:
                    return True, f"Unlit/streak keyword match ('{kw}' in sidebar preview)"

        # 3. Check streak-related attributes / SVGs / images (lit orange or unlit gray flame)
        for streak_sel in config.STREAK_ICON_SELECTORS:
            try:
                badge = await item.query_selector(streak_sel)
                if badge:
                    return True, f"Matched streak icon selector `{streak_sel}`"
            except PlaywrightError:
                continue

    # 4. Check optional fallback username whitelist in config.py
    normalized_name = chat_name.strip().lower()
    for fallback_user in config.FALLBACK_STREAK_USERS:
        target = fallback_user.strip().lower()
        if target and (target == normalized_name or target in normalized_name):
            return True, f"Matched FALLBACK_STREAK_USERS ('{fallback_user}')"

    # 5. Check 1-on-1 conversations within STREAK_LOOKBACK_DAYS (catches unlit/gray streaks)
    if getattr(config, "DETECT_1ON1_BY_RECENCY", True):
        lookback_days = int(getattr(config, "STREAK_LOOKBACK_DAYS", 3))
        if not include_unlit:
            lookback_days = 0
        try:
            conv_time_str = await item.evaluate(
                """(el) => {
                    const convId = el.getAttribute('data-conv-id') || '';
                    if (!convId.startsWith('0:1:')) return null;
                    const timeEl = el.querySelector('span[class*="SpanInfoTime"]');
                    return timeEl ? (timeEl.textContent || '').trim() : null;
                }"""
            )
            if conv_time_str:
                matched, label = is_within_lookback_days(conv_time_str, lookback_days)
                if matched:
                    return True, f"1-on-1 Streak ({label})"
        except PlaywrightError:
            pass

    return False, ""


# ==============================================================================
# MODE 2: DEBUG DOM (--debug-dom)
# ==============================================================================
async def dump_debug_dom(page: Page, item_selector: str) -> None:
    """
    Print the outer HTML and text content of the first N chat list items in the sidebar
    so the user can easily inspect and update selectors in config.py if TikTok updates its UI.
    """
    items = await page.query_selector_all(item_selector)
    limit = min(len(items), config.DEBUG_DOM_MAX_ITEMS)

    print("\n" + "=" * 80)
    print(f"  DEBUG DOM OUTPUT (First {limit} of {len(items)} chat items matching `{item_selector}`)")
    print("=" * 80)

    for idx in range(limit):
        item = items[idx]
        name = await extract_chat_name(item, idx + 1)
        is_streak, reason = await evaluate_streak_status(item, name)
        try:
            text_content = (await item.inner_text()).strip().replace("\n", " | ")
            outer_html = await item.evaluate("el => el.outerHTML")
        except PlaywrightError as exc:
            text_content = f"<error reading text: {exc}>"
            outer_html = f"<error reading outerHTML: {exc}>"

        print(f"\n--- [Chat Item #{idx + 1}] Extracted Name: {name!r} ---")
        print(f"Streak Detected : {is_streak} ({reason or 'No streak marker matched'})")
        print(f"Text Content    : {text_content}")
        print(f"Outer HTML      :\n{outer_html}")
        print("-" * 80)


# ==============================================================================
# MESSAGE SENDING HELPERS
# ==============================================================================
async def find_message_input(page: Page) -> Optional[ElementHandle]:
    """Locate the message input box inside an open TikTok conversation."""
    combined = ", ".join(config.MESSAGE_INPUT_SELECTORS)
    try:
        await page.wait_for_selector(
            combined,
            state="visible",
            timeout=config.MESSAGE_INPUT_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        return None

    for selector in config.MESSAGE_INPUT_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                return el
        except PlaywrightError:
            continue

    return None


async def send_human_like_message(page: Page, chat: DetectedStreakChat) -> bool:
    """
    Click the target streak chat, wait a human-like randomized delay, focus the input box,
    type a random message character-by-character, and press Enter.
    """
    logger.info("Opening streak chat with '%s' (%s)...", chat.name, chat.reason)

    try:
        await chat.element.scroll_into_view_if_needed()
        await chat.element.click()
    except PlaywrightError as exc:
        logger.error("Failed to click chat item for '%s': %s", chat.name, exc)
        return False

    open_delay = random.uniform(config.CHAT_OPEN_DELAY_MIN, config.CHAT_OPEN_DELAY_MAX)
    logger.info("Waiting %.2fs after opening chat...", open_delay)
    await asyncio.sleep(open_delay)

    input_box = await find_message_input(page)
    if not input_box:
        logger.error(
            "Could not locate message input box for '%s'. Check MESSAGE_INPUT_SELECTORS in config.py.",
            chat.name,
        )
        return False

    message = random.choice(config.MESSAGES_POOL)
    typing_delay_ms = random.randint(config.TYPING_DELAY_MIN_MS, config.TYPING_DELAY_MAX_MS)

    logger.info(
        "Typing message %r to '%s' (per-key delay=%dms)...",
        message,
        chat.name,
        typing_delay_ms,
    )

    try:
        await input_box.click()
        await asyncio.sleep(random.uniform(0.3, 0.7))
        await page.keyboard.type(message, delay=typing_delay_ms)
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.keyboard.press("Enter")
    except PlaywrightError as exc:
        logger.error("Error while typing/sending message to '%s': %s", chat.name, exc)
        return False

    logger.info("Successfully sent %r to '%s'!", message, chat.name)
    return True


# ==============================================================================
# MAIN STREAK AUTOMATION FLOW
# ==============================================================================
async def scan_and_process_sidebar(
    page: Page,
    item_selector: str,
    dry_run: bool,
) -> int:
    """
    Scan all loaded sidebar conversation items and IMMEDIATELY send a streak message
    the moment an inactive/unlit (not yet messaged today) streak chat is detected.
    Re-queries the virtualized sidebar list after each sent message so DOM nodes never go stale.
    Returns the number of messages sent during this pass.
    """
    messaged_today = load_messaged_today()
    raw_items = await page.query_selector_all(item_selector)
    if not raw_items:
        await asyncio.sleep(2.0)
        raw_items = await page.query_selector_all(item_selector)

    logger.info("Scanning %d conversation item(s) for inactive/active streaks...", len(raw_items))

    streak_chats: list[DetectedStreakChat] = []
    seen_names: set[str] = set()
    sent_count = 0

    idx = 0
    while True:
        raw_items = await page.query_selector_all(item_selector)
        if idx >= len(raw_items):
            break

        item = raw_items[idx]
        idx += 1

        name = await extract_chat_name(item, idx)
        if name in seen_names:
            continue

        is_streak, reason = await evaluate_streak_status(item, name)
        if not is_streak:
            continue

        seen_names.add(name)
        chat_obj = DetectedStreakChat(
            index=idx,
            name=name,
            reason=reason,
            element=item,
        )
        streak_chats.append(chat_obj)

        if name in messaged_today:
            logger.info("[#%02d] '%s' already messaged today (%s) — skipping.", idx, name, reason)
            continue

        if dry_run:
            logger.info("[#%02d] Detected unmessaged streak '%s' (%s) [DRY-RUN].", idx, name, reason)
            continue

        # Immediately send message upon detecting an unmessaged / inactive streak!
        logger.info(
            "IMMEDIATE TRIGGER: Detected unmessaged/inactive streak '%s' (%s) — sending now!",
            name,
            reason,
        )
        success = await send_human_like_message(page, chat_obj)
        if success:
            record_messaged_today(name, messaged_today)
            sent_count += 1
            post_delay = random.uniform(
                config.POST_SEND_DELAY_MIN,
                config.POST_SEND_DELAY_MAX,
            )
            logger.info("Waiting %.2fs before continuing sidebar scan...", post_delay)
            await asyncio.sleep(post_delay)
            # Reset index to 0 so we re-scan from the top of the re-rendered virtual list
            # (seen_names and messaged_today prevent re-processing already handled chats)
            idx = 0

    if not streak_chats:
        logger.info("No streak conversations matched during this scan.")
        return 0

    print("\n" + "=" * 72)
    print(f"  STREAK SCAN SUMMARY ({len(streak_chats)} streak chat(s) tracked)")
    print("=" * 72)
    for s in streak_chats:
        status = "MESSAGED TODAY" if s.name in messaged_today else "PENDING"
        print(f"  [#{s.index:02d}] {s.name:<28} | {s.reason} | {status}")
    print("=" * 72 + "\n")

    return sent_count


async def run_streak_automation(
    dry_run: bool,
    debug_dom: bool,
    headless: bool,
    watch: bool = False,
) -> None:
    """
    Navigate to TikTok Messages, detect active/inactive streak conversations, and
    immediately send streak messages upon detection (with optional continuous `--watch` mode).
    """
    messaged_today = load_messaged_today()
    if messaged_today:
        logger.info(
            "Loaded daily lockfile (%s): %d chat(s) already messaged today (%s).",
            config.STREAK_LOG_FILE,
            len(messaged_today),
            ", ".join(sorted(messaged_today)),
        )

    async with async_playwright() as p:
        browser, context = await create_browser_context(p, headless=headless)
        page = await get_active_page(context)

        try:
            logger.info("Navigating to %s ...", config.TIKTOK_MESSAGES_URL)
            await page.goto(
                config.TIKTOK_MESSAGES_URL,
                wait_until="domcontentloaded",
                timeout=config.NAVIGATION_TIMEOUT_MS,
            )

            # Give dynamic React/DraftJS view a moment to settle
            await asyncio.sleep(2.5)

            # Check if redirected to login or if login modal/page is active
            if "/login" in page.url.lower():
                if headless:
                    logger.error(
                        "Redirected to login page (%s) in headless mode. "
                        "Please run `python main.py --login` first!",
                        page.url,
                    )
                    return

                logger.warning(
                    "Not logged in yet (%s). Please log into TikTok in the opened browser window. "
                    "Waiting up to 5 minutes for login to complete...",
                    page.url,
                )
                try:
                    await page.wait_for_url(
                        lambda url: "/login" not in url.lower(),
                        timeout=300_000,
                    )
                    logger.info("Login detected! Navigating to %s ...", config.TIKTOK_MESSAGES_URL)
                    await asyncio.sleep(2.0)
                    if "/messages" not in page.url.lower():
                        await page.goto(
                            config.TIKTOK_MESSAGES_URL,
                            wait_until="domcontentloaded",
                            timeout=config.NAVIGATION_TIMEOUT_MS,
                        )
                        await asyncio.sleep(2.5)
                except PlaywrightTimeoutError:
                    logger.error("Timed out waiting for manual login.")
                    return

            item_selector = await wait_for_chat_sidebar(page)
            if not item_selector and not headless:
                logger.warning(
                    "Conversation sidebar not visible yet on %s. "
                    "If a login prompt or captcha is shown in the browser, please complete it now (waiting up to 3 minutes)...",
                    page.url,
                )
                for _ in range(36):
                    await asyncio.sleep(5.0)
                    if "/messages" not in page.url.lower() and "/login" not in page.url.lower():
                        try:
                            await page.goto(
                                config.TIKTOK_MESSAGES_URL,
                                wait_until="domcontentloaded",
                                timeout=config.NAVIGATION_TIMEOUT_MS,
                            )
                        except PlaywrightError:
                            pass
                    item_selector = await wait_for_chat_sidebar(page)
                    if item_selector:
                        break

            if not item_selector:
                logger.error(
                    "Timed out waiting for conversation sidebar on %s. "
                    "Ensure you are logged in (`python main.py --login`) or inspect with `--debug-dom`.",
                    page.url,
                )
                return

            # Scroll sidebar slightly so top conversations are loaded into the DOM
            await scroll_conversation_sidebar(page, item_selector)

            # If --debug-dom is requested, dump the top 5 chat list items and exit
            if debug_dom:
                await dump_debug_dom(page, item_selector)
                return

            while True:
                sent_count = await scan_and_process_sidebar(page, item_selector, dry_run=dry_run)
                await export_storage_state(context)

                if not watch or dry_run:
                    logger.info(
                        "Run complete! Sent %d streak message(s) in this run (total messaged today: %d).",
                        sent_count,
                        len(load_messaged_today()),
                    )
                    break

                poll_sec = getattr(config, "WATCH_POLL_INTERVAL_SEC", 30)
                logger.info(
                    "Watch mode active (--watch): sleeping %ds before next real-time check...",
                    poll_sec,
                )
                await asyncio.sleep(poll_sec)
        finally:
            try:
                await context.close()
                if browser:
                    await browser.close()
            except PlaywrightError:
                pass


# ==============================================================================
# CLI ARGUMENT PARSER & ENTRYPOINT
# ==============================================================================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate daily TikTok streaks via TikTok Web using Playwright (async)."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Launch browser in headed mode to log into TikTok manually and persist session.",
    )
    parser.add_argument(
        "--export-session",
        action="store_true",
        help="Export cookies and localStorage from ./tiktok_profile to storage_state.json for cloud/GitHub Actions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and log active streak chats without sending any messages.",
    )
    parser.add_argument(
        "--debug-dom",
        action="store_true",
        help="Print outer HTML and text content of the first 5 sidebar chat items.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (ignored when --login is used).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor TikTok Messages and immediately message any streak the moment it turns inactive/unlit.",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    if args.login:
        await run_login_flow()
    elif args.export_session:
        await run_export_session_only()
    else:
        await run_streak_automation(
            dry_run=args.dry_run,
            debug_dom=args.debug_dom,
            headless=args.headless,
            watch=args.watch,
        )


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Exiting cleanly.")

