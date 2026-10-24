"""
Configuration settings for the TikTok Streak Automation tool.
Customize your message pool, human delay ranges, fallback users, and DOM selectors here.
"""

from pathlib import Path

# ==============================================================================
# PATHS & URLS
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent

# Persistent Chromium profile directory (stores cookies, session, localStorage)
USER_DATA_DIR: str = str(BASE_DIR / "tiktok_profile")

# Local JSON lockfile to prevent messaging the same streak chat twice in one day
STREAK_LOG_FILE: str = str(BASE_DIR / "streak_log.json")

# Exported Playwright storage state (cookies + localStorage) for cloud/GitHub Actions runs
STORAGE_STATE_FILE: str = str(BASE_DIR / "storage_state.json")

# Persistent file log for unattended / scheduled runs
AUTOMATION_LOG_FILE: str = str(BASE_DIR / "streak_automation.log")

# TikTok Web endpoints
TIKTOK_LOGIN_URL: str = "https://www.tiktok.com/login"
TIKTOK_MESSAGES_URL: str = "https://www.tiktok.com/messages"


# ==============================================================================
# CUSTOM MESSAGE POOL & FALLBACK WHITELIST
# ==============================================================================
# A random message from this pool is chosen for each active streak chat
MESSAGES_POOL: list[str] = [
    "🔥",
    "⚡",
    "👋",
    "streak!",
    "yo 🔥",
]

# Optional fallback list of usernames or display names (case-insensitive).
# Use this if you want to hardcode or supplement specific friends regardless of DOM badges.
FALLBACK_STREAK_USERS: list[str] = [
    "nyx",
    "🌷",
]

# Include unlit ("not flaming up" / gray flame), expiring (⏳), or paused streak chats
INCLUDE_UNLIT_STREAKS: bool = True

# TikTok Web's desktop sidebar (`dm-new-conversation-item`) hides the mobile flame icon
# when the last message is a normal text/video/sticker.
# When True, 1-on-1 chats (`data-conv-id^="0:1:"`) with activity today (`HH:MM`),
# "Yesterday", or within `STREAK_LOOKBACK_DAYS` are treated as streak chats (catching
# unlit/gray streaks before anyone messages today).
DETECT_1ON1_BY_RECENCY: bool = True
STREAK_LOOKBACK_DAYS: int = 3


# ==============================================================================
# HUMAN-LIKE TIMING & DELAYS
# ==============================================================================
# Delay (in seconds) after clicking a chat item before focusing the input box
CHAT_OPEN_DELAY_MIN: float = 1.2
CHAT_OPEN_DELAY_MAX: float = 2.2

# Delay (in milliseconds) between individual keystrokes during human typing simulation
TYPING_DELAY_MIN_MS: int = 40
TYPING_DELAY_MAX_MS: int = 90

# Delay (in seconds) after sending a message before moving to the next streak chat
POST_SEND_DELAY_MIN: float = 2.0
POST_SEND_DELAY_MAX: float = 4.0

# Real-time watcher polling interval (in seconds) when running with `--watch`
WATCH_POLL_INTERVAL_SEC: int = 30

# Sidebar scroll settings to ensure top conversations are rendered in the DOM
SIDEBAR_SCROLL_STEPS: int = 3
SIDEBAR_SCROLL_PIXELS: int = 300
SIDEBAR_SCROLL_PAUSE_MIN: float = 0.7
SIDEBAR_SCROLL_PAUSE_MAX: float = 1.4

# Timeouts (in milliseconds)
NAVIGATION_TIMEOUT_MS: int = 45_000
SIDEBAR_LOAD_TIMEOUT_MS: int = 30_000
MESSAGE_INPUT_TIMEOUT_MS: int = 15_000

# Number of sidebar conversation items to inspect when running `--debug-dom`
DEBUG_DOM_MAX_ITEMS: int = 5


# ==============================================================================
# BROWSER & ANTI-DETECTION (STEALTH) SETTINGS
# ==============================================================================
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

VIEWPORT: dict[str, int] = {"width": 1366, "height": 850}

BROWSER_ARGS: list[str] = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-default-browser-check",
    "--no-first-run",
]


# ==============================================================================
# DOM SELECTORS
# ==============================================================================
# Conversation list item selectors in the left sidebar (tried in order)
CHAT_LIST_ITEM_SELECTORS: list[str] = [
    '[data-e2e="dm-new-conversation-item"]',
    '[data-e2e="chat-list-item"]',
    'div[class*="DivItemWrapper"]',
    'div[class*="ChatListItem"]',
    'li[data-e2e*="chat-list"]',
]

# Selectors inside a chat list item to extract the user's nickname / handle
CHAT_NICKNAME_SELECTORS: list[str] = [
    '[data-e2e="dm-new-conversation-nickname"]',
    '[data-e2e="chat-nickname"]',
    'p[class*="PInfoNickname"]',
    'span[class*="SpanNickname"]',
    'div[class*="DivItemInfo"] p:first-child',
]

# Selectors targeting the chat item header / title container for streak badge checks
CHAT_ITEM_HEADER_SELECTORS: list[str] = [
    '[data-e2e="chat-nickname"]',
    'div[class*="DivItemInfo"]',
    'div[class*="Header"]',
    'p[class*="Nickname"]',
]

# Emoji / text indicators that signify a lit (🔥) or unlit/expiring (⏳) streak
STREAK_EMOJI_INDICATORS: list[str] = [
    "🔥",
    "⏳",
]

# Case-insensitive text keywords inside a chat item that indicate a streak (lit or unlit)
STREAK_TEXT_KEYWORDS: list[str] = [
    "streak",
]

# CSS selectors for streak icons (both lit/flaming and unlit/gray SVGs, images, or badges)
STREAK_ICON_SELECTORS: list[str] = [
    '[data-e2e*="streak" i]',
    '[class*="Streak"]',
    '[class*="streak"]',
    '[class*="Flame"]',
    '[class*="flame"]',
    '[class*="FireIcon"]',
    'svg[class*="streak" i]',
    'svg[class*="flame" i]',
    'svg[class*="fire" i]',
    'svg[aria-label*="streak" i]',
    'img[alt*="🔥"]',
    'img[alt*="⏳"]',
    'img[alt*="streak" i]',
    'img[src*="streak" i]',
    'img[src*="fire" i]',
    'img[src*="flame" i]',
    '[aria-label*="streak" i]',
]

# Message input box selectors inside an active conversation view (tried in order)
MESSAGE_INPUT_SELECTORS: list[str] = [
    '[data-e2e="dm-new-input-editor"] [contenteditable="true"]',
    '[data-e2e="message-input-area"] [contenteditable="true"]',
    'div.public-DraftEditor-content[role="textbox"]',
    'div.public-DraftEditor-content[contenteditable="true"]',
    '[data-e2e="message-input-area"] div[role="textbox"]',
    '[data-e2e="message-input-area"]',
    'div[contenteditable="true"][role="textbox"]',
    '[contenteditable="true"]',
]

