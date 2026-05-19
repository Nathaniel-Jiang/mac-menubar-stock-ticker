#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  macOS Menu Bar Stock Terminal — an xbar / SwiftBar plugin
  https://github.com/<your-username>/<your-repo>

  A live ticker, portfolio P&L tracker, and alert engine that lives in your
  macOS menu bar. Built for retail traders who want at-a-glance market
  awareness without leaving a browser tab open.
═══════════════════════════════════════════════════════════════════════════════

FEATURES
  • Real-time stock quotes with pre/post-market support (Alpaca + Yahoo fallback)
  • Multi-group ticker rotation through the menu bar
  • U.S. 10-Year Treasury yield with 5-source failover (CNBC → Stooq → Yahoo)
  • Portfolio P&L tracking with margin-aware equity calculation
  • Configurable percentage thresholds and absolute price alerts
  • Breaking-news alerts via Finnhub
  • macOS Notification Center integration (persists past menu-bar freeze)
  • Smart caching: minimizes API calls without sacrificing data freshness
  • Phase-aware alerts: silent during pre/post-market, audible during RTH

QUICK START
  1. Install xbar (https://xbarapp.com) or SwiftBar (https://swiftbar.app)
  2. Copy this file into your xbar plugin folder, naming it with a refresh
     suffix — e.g. `stock.8s.py` for an 8-second refresh interval
  3. Make it executable: chmod +x stock.8s.py
  4. First run auto-creates `~/.xbar_stock_config.json` with safe defaults
  5. Edit that file:
       - Add your Alpaca paper-trading API keys (free, recommended)
       - Optionally add a Finnhub key for breaking-news alerts
       - List your tickers in TICKER_GROUPS
       - List your positions in PORTFOLIO for P&L tracking
  6. Set config file permissions: chmod 600 ~/.xbar_stock_config.json
  7. Click the xbar menu icon → Refresh All

  No API keys are strictly required. Without them the plugin falls back to
  Yahoo Finance (public/unauthenticated). Adding free Alpaca keys gives you
  cleaner data during regular trading hours.

CONFIG FILE
  Lives at ~/.xbar_stock_config.json. See DEFAULT_CONFIG below for the full
  schema. Permissions are auto-tightened to 600 (owner-only) on every load.

  All API keys are read from this file — never hardcoded in source. If you
  fork this project, scrub your local config from any commits.

DATA SOURCES & LIMITATIONS
  • Alpaca free tier delivers IEX-only data (~3% of US equity volume).
    During regular hours that's fine for large caps but small-caps may show
    slightly delayed prints. For Level-1 SIP data, Alpaca paid is $99/mo.
  • Yahoo Finance is unauthenticated public scraping — rate-limited and
    schema-fragile. We use it as fallback and for pre/post-market.
  • Finnhub free tier: 60 req/min. We poll roughly once per cache window.
  • CNBC's quote.htm endpoint is unofficial; we fall through to alternates
    (Stooq, Yahoo ^TNX) if it ships a bad response.

LICENSE
  MIT — see LICENSE file.

SUPPORT
  If this is useful, you can buy me a coffee:
    https://buymeacoffee.com/nathanieljiang
  All features are free and always will be — no paywall, no telemetry.

PORTING NOTES
  Tested on macOS 13+ with Python 3.10+. Earlier Python versions may need
  `from __future__ import annotations` plus typing backports.

  No external dependencies (stdlib only). xbar and SwiftBar both run plugins
  the same way: stdout becomes the menu, separator `---` divides sections,
  parameters like `| color=#FF0000 size=12` style each line.
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

# Standard library only — no `pip install` required.
import concurrent.futures   # For parallel API fetching
import json                 # Config, cache, and alert-state are all JSON
import logging              # Rotating file logger at /tmp/xbar_stock.log
import os                   # File permissions and atomic renames
import random               # User-Agent rotation to dodge naive bot blockers
import socket               # socket.timeout — sneaky exception not always
                            #   covered by `TimeoutError` in older Python
import subprocess           # afplay (sound) and osascript (notifications)
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

# ==================== [ CONSTANTS ] ====================

# Version is shown in the dropdown footer. Bump when releasing a tagged build.
CURRENT_VERSION = "2.0"

# All market-hour logic is in US Eastern. macOS auto-applies DST.
EASTERN = ZoneInfo("America/New_York")

# Applied to the menu-bar top line. `dropdown=false` means the line itself
# (the actual menu bar text) is not duplicated into the dropdown popover.
FONT_SETTINGS = "font='Menlo Bold' size=14 dropdown=false"

# State directory — survives reboots. Holds today's triggered alerts so we
# don't re-fire them on every macOS restart, and the round-robin group index.
STATE_DIR = Path.home() / "Library" / "Application Support" / "xbar_stock"
STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / "idx.txt"
ALERT_STATE_FILE = STATE_DIR / "alerts_v4.json"

# Ephemeral caches — rebuild quickly, fine to lose on reboot.
OTA_CACHE_FILE = Path("/tmp/xbar_stock_ota_cache.json")
QUOTE_CACHE_FILE = Path("/tmp/xbar_stock_quote_cache.json")
LOG_FILE = Path("/tmp/xbar_stock.log")
CONFIG_FILE = Path.home() / ".xbar_stock_config.json"

# One-time migration: older versions stored state under /tmp. If those exist
# and the new locations don't, move them in. Silently — no need to ever revisit.
for _legacy, _new in [
    (Path("/tmp/xbar_stock_idx.txt"), STATE_FILE),
    (Path("/tmp/xbar_stock_alerts_v4.json"), ALERT_STATE_FILE),
]:
    if _legacy.exists() and not _new.exists():
        try:
            _new.write_bytes(_legacy.read_bytes())
            _legacy.unlink()
        except OSError:
            pass  # Migration is best-effort; missing it just means state resets once.

OTA_CACHE_TTL_SECONDS = 3600  # 1 hour

# Quote cache TTLs by market phase. Reads are cheap, network is precious —
# skip the fetch entirely if last cached data is younger than the TTL.
QUOTE_CACHE_TTL = {
    "REGULAR": 5,    # Alpaca delivers sub-second updates; refresh aggressively
    "PRE": 30,       # Yahoo 1-min bars + thin volume → no reason to over-poll
    "POST": 30,
    "CLOSED": 60,    # almost never hit (we deep-sleep), but a sane ceiling
}
# Treasury and news change much more slowly than equities.
TREASURY_CACHE_TTL = 30
NEWS_CACHE_TTL = 20

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
]

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
    "CNY": "¥", "BTC": "₿", "ETH": "Ξ",
}

# Alert priorities — higher value wins, lower-priority alerts cannot override.
# Alert priority levels. Higher number wins: a NEWS alert can preempt a
# STOCK alert in the menu bar, an EQUITY alert can preempt anything.
# Same-priority alerts arrive in code order (stocks scanned first).
ALERT_PRIORITY = {
    "STOCK":       1,   # %-threshold alerts (e.g. AAPL up 5%)
    "PRICE":       1,   # Absolute price targets (e.g. AAPL > $250)
    "NEWS":        2,   # Breaking news headline change
    "EQUITY_HIGH": 3,   # Portfolio equity crossed upper threshold
    "EQUITY_LOW":  3,   # Portfolio equity crossed lower threshold (margin risk)
}


# ─── Default configuration ──────────────────────────────────────────────────
#
# This is written to ~/.xbar_stock_config.json on first run and used as
# fallback values for any key the user omits. Edit your local config file —
# do NOT edit this dict to set personal values (you'll commit secrets).
#
# Every field is also validated at startup by `validate_config()` below. A
# bad value won't crash the plugin; it surfaces in the menu bar as a friendly
# error with a "fix config" shortcut.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: dict[str, Any] = {
    # ── Alert thresholds ─────────────────────────────────────────────────────
    # Percentage move (vs previous close) at which to fire a STOCK alert.
    # All thresholds fire independently: 5% triggers AAPL_UP_5, 10% triggers
    # AAPL_UP_10 (each at most once per day per symbol per direction).
    "THRESHOLDS": [5, 10, 15, 20, 25],

    # ── Display colors ──────────────────────────────────────────────────────
    # Hex strings. UP/DOWN apply when prices/equity move; NORMAL is the
    # menu bar's resting color (used in dark mode — adjust for light).
    "COLOR_UP":     "#228B22",   # Forest green
    "COLOR_DOWN":   "#DC143C",   # Crimson
    "COLOR_NORMAL": "#FFFFFF",   # White (dark menu bar) — try "#000000" if light

    # ── Audio + notification gates ──────────────────────────────────────────
    "ENABLE_SOUND_ALERT": True,    # Glass.aiff plays on alert (REGULAR hours only)
    "ENABLE_NOTIFICATIONS": True,  # macOS Notification Center — persists past freeze

    # After ANY stock/price alert fires for a symbol, suppress further
    # stock/price alerts for that symbol for this many minutes. Prevents
    # alert noise during fast volatile moves (e.g. crossing +5%, +10%,
    # +15% all in 30 seconds). Does NOT affect equity/news alerts.
    "STOCK_ALERT_COOLDOWN_MINUTES": 5,

    # When an alert fires, the menu bar locks to its color/text for this
    # many seconds, blocking other alerts from grabbing the spotlight.
    "FREEZE_DURATION": 30,

    # ── Display mode ────────────────────────────────────────────────────────
    # If False (default): TICKER_GROUPS are rotated round-robin each tick.
    # If True: combine all symbols and reorder by intraday volatility,
    # showing only the top movers (group[0]'s length determines how many).
    "SMART_SORT": False,

    # ── Other features ──────────────────────────────────────────────────────
    "ENABLE_NEWS_ALERTS": True,
    "SHOW_TREASURY_IN_MENUBAR": True,

    # ── API credentials ─────────────────────────────────────────────────────
    # Finnhub: free tier 60 req/min, used for breaking-news alerts only.
    # Sign up at https://finnhub.io and paste the API key here.
    # Leave the placeholder to disable news fetching.
    "FINNHUB_API_KEY": "YOUR_FINNHUB_KEY_HERE",

    # Alpaca: free paper-trading keys give cleaner quotes during RTH.
    # Sign up at https://alpaca.markets, then API Keys → Generate.
    # We use the data API ONLY — no trading is performed.
    # Endpoint is for market data, NOT the paper-trading order endpoint.
    "ALPACA_API_KEY":    "YOUR_ALPACA_KEY_HERE",
    "ALPACA_API_SECRET": "YOUR_ALPACA_SECRET_HERE",
    "ALPACA_ENDPOINT":   "https://data.alpaca.markets/v2",

    # OTA update check — set this to a raw.githubusercontent.com URL
    # pointing at a "version.txt" file in your own fork to enable. Result
    # is cached for 1 hour. Empty string disables (default).
    "UPDATE_URL": "",

    # ── Watchlists ──────────────────────────────────────────────────────────
    # List of groups. Each group is shown for one xbar refresh interval
    # (the `Ns` suffix in the script filename), then rotates to the next.
    # Example: with `stock.8s.py` and two groups, each group is visible
    # for 8 seconds, full rotation = 16 seconds.
    "TICKER_GROUPS": [
        ["AAPL", "MSFT", "TSLA"],
        ["NVDA", "GOOGL", "AMZN"],
    ],

    # Optional: replace ticker text with an emoji or short label in the
    # menu bar. Helps when tickers are long or you want visual recognition.
    "TICKER_ICONS": {"AAPL": "🍎", "TSLA": "⚡", "NVDA": "🧠"},

    # ── Portfolio (optional) ────────────────────────────────────────────────
    # If you list positions here, the dropdown shows unrealized + today P&L
    # per stock and globally. ACCOUNT.margin_used is subtracted from market
    # value to derive equity, which is then checked against the EQUITY_*
    # thresholds for risk alerts.
    "ACCOUNT": {
        "margin_used":       5000.00,    # Set to 0 if cash account
        "EQUITY_ALERT_HIGH": 50000.00,   # Fire when equity ≥ this (take-profit signal)
        "EQUITY_ALERT_LOW":  10000.00,   # Fire when equity ≤ this (margin-call warning)
    },
    "PORTFOLIO": {
        # symbol → {shares: int, cost_basis: float (per share)}
        "AAPL": {"shares": 100, "cost_basis": 150.00},
        "MSFT": {"shares": 50,  "cost_basis": 350.00},
    },

    # ── Per-symbol price alerts ─────────────────────────────────────────────
    # Independent from THRESHOLDS — these are absolute price targets, useful
    # for "fire when X breaks $250" style signals. Both `above` and `below`
    # are optional.
    "PRICE_ALERTS": {
        "AAPL": {"above": 250.0, "below": 100.0},
        "TSLA": {"above": 300.0},
    },
}


# ==================== [ LOGGING ] ====================

def setup_logging() -> logging.Logger:
    """Rotating log; xbar runs every minute so we keep it small."""
    logger = logging.getLogger("xbar_stock")
    if logger.handlers:  # avoid duplicate handlers on re-import
        return logger
    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=256_000, backupCount=2)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        # If /tmp isn't writable for some bizarre reason, fall back to stderr.
        logger.addHandler(logging.StreamHandler(sys.stderr))
    return logger


log = setup_logging()


# ==================== [ CONFIG ] ====================

def load_config() -> dict[str, Any]:
    """Load config, auto-generate defaults, merge in any new keys."""
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4))
            # File now holds API secrets — restrict to owner read/write only.
            os.chmod(CONFIG_FILE, 0o600)
        except OSError as e:
            log.warning("Could not write default config: %s", e)
        return dict(DEFAULT_CONFIG)

    try:
        user_cfg = json.loads(CONFIG_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        log.error("Config unreadable, using defaults: %s", e)
        return dict(DEFAULT_CONFIG)

    # Config now contains API secrets; warn (and auto-tighten) if permissions are loose.
    try:
        mode = CONFIG_FILE.stat().st_mode & 0o777
        if mode & 0o077:  # group or other has any bits set
            log.warning("Config %s is mode %o; tightening to 600.", CONFIG_FILE, mode)
            os.chmod(CONFIG_FILE, 0o600)
    except OSError as e:
        log.info("Could not stat/chmod config: %s", e)

    # Inject any newly added default keys without clobbering user values.
    merged = dict(DEFAULT_CONFIG)
    merged.update(user_cfg)
    for k, v in DEFAULT_CONFIG.items():
        merged.setdefault(k, v)
    return merged


def validate_config(cfg: dict[str, Any]) -> list[str]:
    """Return a list of human-readable error messages for any invalid config.

    Empty list means the config is usable. Doesn't try to be exhaustive —
    just catches mistakes that would otherwise crash deep in the runtime.
    """
    errors: list[str] = []

    def _is_num(x: Any) -> bool:
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    # THRESHOLDS: list of numbers
    thresholds = cfg.get("THRESHOLDS")
    if not isinstance(thresholds, list) or not all(_is_num(x) for x in thresholds):
        errors.append("THRESHOLDS must be a list of numbers (e.g. [5, 10, 15])")

    # Colors: hex strings starting with #
    for key in ("COLOR_UP", "COLOR_DOWN", "COLOR_NORMAL"):
        v = cfg.get(key)
        if not isinstance(v, str) or not v.startswith("#") or len(v) not in (4, 7):
            errors.append(f"{key} must be a hex color like '#228B22' (got {v!r})")

    # Booleans
    for key in ("ENABLE_SOUND_ALERT", "ENABLE_NOTIFICATIONS", "SMART_SORT",
                "ENABLE_NEWS_ALERTS", "SHOW_TREASURY_IN_MENUBAR"):
        if not isinstance(cfg.get(key), bool):
            errors.append(f"{key} must be true or false")

    # TICKER_GROUPS: list of lists of strings
    groups = cfg.get("TICKER_GROUPS")
    if not isinstance(groups, list) or not groups:
        errors.append("TICKER_GROUPS must be a non-empty list")
    else:
        for i, g in enumerate(groups):
            if not isinstance(g, list) or not all(isinstance(s, str) for s in g):
                errors.append(f"TICKER_GROUPS[{i}] must be a list of ticker strings")

    # TICKER_ICONS: dict[str, str]
    icons = cfg.get("TICKER_ICONS", {})
    if not isinstance(icons, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in icons.items()
    ):
        errors.append("TICKER_ICONS must be a {symbol: emoji} dict of strings")

    # PORTFOLIO: dict of {symbol: {shares, cost_basis}}
    portfolio = cfg.get("PORTFOLIO", {})
    if not isinstance(portfolio, dict):
        errors.append("PORTFOLIO must be a dict")
    else:
        for sym, pos in portfolio.items():
            if not isinstance(pos, dict):
                errors.append(f"PORTFOLIO[{sym}] must be a dict with shares/cost_basis")
                continue
            if not _is_num(pos.get("shares")):
                errors.append(f"PORTFOLIO[{sym}].shares must be a number")
            if not _is_num(pos.get("cost_basis")):
                errors.append(f"PORTFOLIO[{sym}].cost_basis must be a number")

    # ACCOUNT
    acct = cfg.get("ACCOUNT", {})
    if not isinstance(acct, dict):
        errors.append("ACCOUNT must be a dict")
    else:
        for k in ("margin_used", "EQUITY_ALERT_HIGH", "EQUITY_ALERT_LOW"):
            if k in acct and not _is_num(acct[k]):
                errors.append(f"ACCOUNT.{k} must be a number")

    # PRICE_ALERTS: dict[symbol, {above?, below?}]
    pa = cfg.get("PRICE_ALERTS", {})
    if not isinstance(pa, dict):
        errors.append("PRICE_ALERTS must be a dict")
    else:
        for sym, targets in pa.items():
            if not isinstance(targets, dict):
                errors.append(f"PRICE_ALERTS[{sym}] must be {{above: ..., below: ...}}")
                continue
            for side in ("above", "below"):
                if side in targets and not _is_num(targets[side]):
                    errors.append(f"PRICE_ALERTS[{sym}].{side} must be a number")

    # FREEZE_DURATION
    fd = cfg.get("FREEZE_DURATION")
    if not _is_num(fd) or fd < 1:
        errors.append("FREEZE_DURATION must be a positive number of seconds")

    # STOCK_ALERT_COOLDOWN_MINUTES
    cd = cfg.get("STOCK_ALERT_COOLDOWN_MINUTES")
    if not _is_num(cd) or cd < 0:
        errors.append("STOCK_ALERT_COOLDOWN_MINUTES must be a non-negative number")

    return errors


CONFIG = load_config()


# ─── Data types ─────────────────────────────────────────────────────────────
#
# These dataclasses are the contract between fetchers and rendering. A
# `StockQuote` produced by the Alpaca fetcher is interchangeable with one
# from Yahoo — the orchestrator never branches on `source`, only the
# dropdown line shows it for diagnostics.
#
# `AlertState` is the only struct that's persisted to disk between runs;
# everything else is recomputed each tick.
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class StockQuote:
    """Normalized result of a single quote fetch (Alpaca or Yahoo).

    Errored fetches set `error` and leave numeric fields at 0 — callers
    should check `.ok` before reading prices. This keeps the type uniform
    so we can mix successful + failed quotes in the same list.
    """
    symbol: str
    price: float = 0.0
    prev_close: float = 0.0
    pct_change: float = 0.0
    volume: int = 0
    avg_volume_10d: int = 0
    currency_code: str = "USD"
    currency_symbol: str = "$"
    sparkline: str = ""               # Compact unicode bar chart of recent prices
    phase_icon: str = ""              # 🌅 pre-market, 🌙 post-market, "" regular
    source: str = "yahoo"             # "alpaca" or "yahoo" — for debugging
    data_age_seconds: int = -1        # Age of the freshest data point; -1 = unknown
    today_regular_close: float = 0.0  # Today's 4PM regular-session close, only set in POST
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def change_label(self) -> str:
        """Render percent change with directional triangle. Sign is encoded in glyph."""
        if self.pct_change > 0:
            return f"▲{self.pct_change:.2f}%"
        if self.pct_change < 0:
            return f"▼{abs(self.pct_change):.2f}%"
        return "0.00%"


@dataclass
class TreasuryYield:
    """U.S. 10-Year Treasury yield snapshot from one of several sources."""
    current: float = 0.0      # Current yield in percent (e.g. 4.421)
    change: float = 0.0       # Change vs previous close (in percentage points)
    source: str = ""          # "CNBC" / "Yahoo" — for diagnostic display


@dataclass
class AlertState:
    """Persisted across runs in ALERT_STATE_FILE."""
    date: str = ""
    triggered: dict[str, bool] = field(default_factory=dict)
    pause_until: float = 0.0
    pause_group_idx: int = 0
    pause_color: str = "#FFFFFF"
    alert_msg: str = ""
    alert_type: str = ""
    last_news_id: str = ""        # Finnhub `id` field (preferred)
    last_news_title: str = ""     # Legacy fallback
    # Per-symbol cooldown — unix ts of last fired stock/price alert per ticker.
    # Used to silence rapid-fire alerts during volatile moves.
    last_alert_at: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, today: str) -> "AlertState":
        try:
            data = json.loads(ALERT_STATE_FILE.read_text())
            if data.get("date") == today:
                return cls(**{k: data.get(k, getattr(cls(), k)) for k in cls.__dataclass_fields__})
        except (OSError, json.JSONDecodeError, TypeError) as e:
            log.info("Alert state reset (%s)", e)
        return cls(date=today, pause_color=CONFIG["COLOR_NORMAL"])

    def save(self) -> None:
        atomic_write_json(ALERT_STATE_FILE, self.__dict__)

    def is_paused(self, now_ts: float) -> bool:
        return now_ts < self.pause_until

    def current_priority(self) -> int:
        return ALERT_PRIORITY.get(self.alert_type, 0)


# ==================== [ FILE I/O HELPERS ] ====================

def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON via temp file + os.replace (atomic on POSIX)."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, path)
    except OSError as e:
        log.warning("atomic_write_json failed for %s: %s", path, e)


def atomic_write_text(path: Path, content: str) -> None:
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        os.replace(tmp, path)
    except OSError as e:
        log.warning("atomic_write_text failed for %s: %s", path, e)


def get_and_advance_group_index(max_groups: int) -> int:
    """Round-robin ticker group index, persisted across runs."""
    try:
        idx = int(STATE_FILE.read_text().strip())
    except (OSError, ValueError):
        idx = 0
    next_idx = (idx + 1) % max(1, max_groups)
    atomic_write_text(STATE_FILE, str(next_idx))
    return idx % max(1, max_groups)


# ==================== [ QUOTE CACHE ] ====================
#
# xbar invokes this script on a fixed cadence (the `N` in `stock.Ns.py`).
# That cadence is typically much faster than upstream data actually changes:
#   * Yahoo's 1-minute bars only roll over once per minute
#   * 10Y treasury and breaking news change on the order of minutes
# So we cache the last-fetched values on disk, and on the next invocation
# we skip the network call entirely if cached data is still within TTL.
# A typical 8-second xbar refresh now issues ~1 network burst per minute,
# while the menu bar still rotates groups and re-renders at 8s.

def load_quote_cache() -> dict:
    try:
        return json.loads(QUOTE_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_quote_cache(cache: dict) -> None:
    atomic_write_json(QUOTE_CACHE_FILE, cache)


def cache_get_quote(cache: dict, symbol: str, phase: str, now_ts: float) -> "StockQuote | None":
    """Return cached quote if fresh AND from the same phase, else None.

    On a cache hit we advance `data_age_seconds` by the time elapsed since
    the entry was written, so the dropdown's "X minutes old" warning stays
    truthful even when served from cache.
    """
    entry = cache.get("quotes", {}).get(symbol)
    if not entry:
        return None
    # Phase change always invalidates — a REGULAR quote isn't valid in POST,
    # because its prev_close baseline and phase_icon are bound to that phase.
    if entry.get("phase") != phase:
        return None
    ttl = QUOTE_CACHE_TTL.get(phase, 30)
    if now_ts - entry.get("fetched_at", 0) > ttl:
        return None
    try:
        data = dict(entry["data"])  # shallow copy to avoid mutating cache dict
        if data.get("data_age_seconds", -1) >= 0:
            elapsed = int(now_ts - entry["fetched_at"])
            data["data_age_seconds"] = data["data_age_seconds"] + elapsed
        return StockQuote(**data)
    except (TypeError, KeyError):
        # Schema drift (new field added since cache was written) — drop it
        return None


def cache_put_quote(cache: dict, q: "StockQuote", phase: str, now_ts: float) -> None:
    """Store a successful quote. Errors are never cached."""
    if not q.ok:
        return
    cache.setdefault("quotes", {})[q.symbol] = {
        "fetched_at": now_ts,
        "phase": phase,
        "data": asdict(q),
    }


def cache_get_treasury(cache: dict, now_ts: float) -> "TreasuryYield | None":
    entry = cache.get("treasury")
    if not entry:
        return None
    if now_ts - entry.get("fetched_at", 0) > TREASURY_CACHE_TTL:
        return None
    try:
        return TreasuryYield(**entry["data"])
    except (TypeError, KeyError):
        return None


def cache_put_treasury(cache: dict, t: "TreasuryYield | None", now_ts: float) -> None:
    if t is None:
        return
    cache["treasury"] = {"fetched_at": now_ts, "data": asdict(t)}


def cache_get_news(cache: dict, now_ts: float) -> "dict | None":
    entry = cache.get("news")
    if not entry:
        return None
    if now_ts - entry.get("fetched_at", 0) > NEWS_CACHE_TTL:
        return None
    return entry.get("data")


def cache_put_news(cache: dict, news: "dict | None", now_ts: float) -> None:
    if news is None:
        return
    cache["news"] = {"fetched_at": now_ts, "data": news}


# ==================== [ FORMATTING HELPERS ] ====================

def format_volume(v: float | int) -> str:
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v/1_000:.1f}K"
    return str(int(v))


def get_currency_symbol(code: str) -> str:
    return CURRENCY_SYMBOLS.get(code, f"{code} ")


def generate_sparkline(prices: Iterable[float | None]) -> str:
    valid = [p for p in prices if p is not None]
    if not valid:
        return ""
    if len(valid) >= 8:
        step = len(valid) // 8
        sampled = valid[::step][-8:]
    else:
        sampled = valid
    if not sampled:
        return ""
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return "━━"
    # Drop the 1/8 block to avoid Menlo font clipping in the menu bar.
    chars = ["▂", "▃", "▄", "▅", "▆", "▇", "█"]
    spread = hi - lo
    return "".join(chars[int(((v - lo) / spread) * (len(chars) - 1))] for v in sampled)


# ==================== [ MARKET SCHEDULE ] ====================

@dataclass
class MarketWindow:
    """Encapsulates EST-based trading session logic."""
    now: datetime

    @property
    def minute_of_day(self) -> int:
        return self.now.hour * 60 + self.now.minute

    @property
    def is_weekend(self) -> bool:
        return self.now.weekday() >= 5

    @property
    def phase(self) -> str:
        h, m = self.now.hour, self.now.minute
        if h < 9 or (h == 9 and m < 30):
            if h >= 4:
                return "PRE"
            return "CLOSED"
        if 9 <= h < 16 or (h == 9 and m >= 30):
            if h < 16:
                return "REGULAR"
        if 16 <= h < 20:
            return "POST"
        return "CLOSED"

    @property
    def is_news_active(self) -> bool:
        """Active window: 4:01 AM – 7:59 PM EST (inclusive both ends).
        Outside this range or on weekends → deep sleep (no fetching, no render).
        Same bounds as `is_stock_active` — the tool now has a single unified
        awake window covering pre-market, regular, and post-market sessions.
        """
        return (4 * 60 + 1) <= self.minute_of_day <= (19 * 60 + 59)

    @property
    def is_stock_active(self) -> bool:
        """Stock-fetch window — identical to `is_news_active` (4:01 AM – 7:59 PM EST)."""
        return (4 * 60 + 1) <= self.minute_of_day <= (19 * 60 + 59)


# ─── Network fetchers ───────────────────────────────────────────────────────
#
# This section is the only place that knows about specific upstream APIs.
# Everything else operates on `StockQuote` / `TreasuryYield` / news dicts.
#
# Fetchers are designed to FAIL FAST and LOUDLY into the log. The dispatcher
# (`fetch_stock`) handles fallback between Alpaca and Yahoo; the treasury
# cascade (`_TREASURY_SOURCES`) handles fallback between 5 different yield
# sources. Individual fetchers raise rather than return None on failure —
# the calling layer makes the policy decision about what to do next.
#
# All HTTP requests use a 1.5–2.5 second timeout. Why so short? xbar
# refreshes are tight (8s) and a slow fetcher delays the whole tick. We'd
# rather fail and use cached data than block the menu bar.
# ────────────────────────────────────────────────────────────────────────────

def _http_json(url: str, timeout: float = 1.5, headers: dict[str, str] | None = None) -> Any:
    """GET + JSON-decode. Rotates User-Agent to look more like a browser.

    Raises on any error: HTTPError (4xx/5xx), URLError (DNS/connect failure),
    JSONDecodeError (server returned HTML), socket.timeout.
    """
    hdrs = {"User-Agent": random.choice(USER_AGENTS)}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_text(url: str, timeout: float = 1.5, headers: dict[str, str] | None = None) -> str:
    """GET as plain text. For CSV (Stooq) and HTML scraping (CNBC fallback)."""
    hdrs = {"User-Agent": random.choice(USER_AGENTS)}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _alpaca_configured() -> bool:
    """True iff both Alpaca API key and secret are set to non-placeholder values."""
    key = CONFIG.get("ALPACA_API_KEY", "")
    sec = CONFIG.get("ALPACA_API_SECRET", "")
    return bool(key) and bool(sec) and key != "YOUR_ALPACA_KEY_HERE" and sec != "YOUR_ALPACA_SECRET_HERE"


def _alpaca_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": CONFIG.get("ALPACA_API_KEY", ""),
        "APCA-API-SECRET-KEY": CONFIG.get("ALPACA_API_SECRET", ""),
        "Accept": "application/json",
    }


def fetch_stock_alpaca(symbol: str, phase: str) -> StockQuote:
    """
    Fetch a US equity quote from Alpaca Data API.

    Endpoints used:
      - /v2/stocks/{symbol}/snapshot   (current trade + minute bar + prev day bar)
      - /v2/stocks/{symbol}/bars        (intraday minutes for sparkline)

    Free Alpaca data is IEX-only (subset of consolidated tape) — fine for a
    menu-bar monitor, not for execution. Pre/post-market trades are included
    because IEX runs during those sessions.

    Raises on any error so the caller can fall back to Yahoo.
    """
    base = CONFIG.get("ALPACA_ENDPOINT", "https://data.alpaca.markets/v2").rstrip("/")
    headers = _alpaca_headers()

    # 1. Snapshot: latest trade, daily bar, previous daily bar
    snap_url = f"{base}/stocks/{symbol}/snapshot"
    snap = _http_json(snap_url, timeout=1.5, headers=headers)

    latest_trade = snap.get("latestTrade") or {}
    daily_bar = snap.get("dailyBar") or {}
    prev_daily_bar = snap.get("prevDailyBar") or {}

    price = float(latest_trade.get("p") or daily_bar.get("c") or 0.0)
    prev_close = float(prev_daily_bar.get("c") or 0.0)
    if price <= 0:
        raise ValueError(f"Alpaca snapshot returned no price for {symbol}")
    if prev_close <= 0:
        prev_close = price  # neutralize pct change rather than divide-by-zero

    today_vol = int(daily_bar.get("v") or 0)
    pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

    # 2. Intraday minute bars for sparkline (last ~3 hours, IEX feed)
    spark = ""
    try:
        # Use a relative end-time string; Alpaca accepts RFC-3339.
        # Pull 1Min bars for today; cap at 100 to keep payload small.
        bars_url = f"{base}/stocks/{symbol}/bars?timeframe=1Min&limit=100&feed=iex"
        bars_data = _http_json(bars_url, timeout=1.5, headers=headers)
        closes = [b.get("c") for b in bars_data.get("bars", []) if b.get("c") is not None]
        spark = generate_sparkline(closes)
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
        log.info("Alpaca sparkline failed for %s: %s", symbol, e)

    # 10-day average volume — Alpaca doesn't expose this cleanly in snapshot.
    # Pull daily bars for the last ~3 weeks.
    avg_v = today_vol
    try:
        # 15 calendar days back is plenty for ~10 trading days.
        from datetime import timezone
        end = datetime.now(timezone.utc) - timedelta(minutes=16)  # SIP-delay safety
        start = end - timedelta(days=20)
        dbars_url = (f"{base}/stocks/{symbol}/bars"
                     f"?timeframe=1Day&start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                     f"&end={end.strftime('%Y-%m-%dT%H:%M:%SZ')}&limit=15&feed=iex")
        dbars = _http_json(dbars_url, timeout=1.5, headers=headers)
        volumes = [int(b.get("v") or 0) for b in dbars.get("bars", []) if b.get("v")]
        if len(volumes) >= 10:
            avg_v = int(sum(volumes[-10:]) / 10)
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
        log.info("Alpaca avg-vol failed for %s: %s", symbol, e)

    phase_icon = ""
    today_reg_close = 0.0
    if phase == "PRE":
        phase_icon = "🌅"
    elif phase == "POST":
        phase_icon = "🌙"
        # Today's regular session close (Alpaca seals dailyBar.c at 4PM EST).
        # prev_close stays as yesterday's close → menu bar shows cumulative %.
        today_reg_close = float(daily_bar.get("c") or 0.0)

    return StockQuote(
        symbol=symbol, price=price, prev_close=prev_close, pct_change=pct,
        volume=today_vol, avg_volume_10d=avg_v, currency_code="USD",
        currency_symbol="$", sparkline=spark, phase_icon=phase_icon, source="alpaca",
        today_regular_close=today_reg_close,
    )


def fetch_stock_yahoo(symbol: str, phase: str) -> StockQuote:
    """
    Yahoo Finance fetcher reading from minute timeseries, not meta fields.

    Yahoo's `meta.postMarketPrice` / `meta.preMarketPrice` are aggressively
    cached and can lag 10-15 minutes for mid/small caps. The per-minute bars
    in `timestamp[]` + `indicators.quote[0].close[]` tend to be fresher.

    Strategy:
      1. Find the latest non-null close in the timeseries → that's our price.
      2. POST phase: comparison base = last bar within regular session.
         PRE / REGULAR: comparison base = previousClose.
      3. Volume = sum of regular-session minute bars (avoids the cached
         meta.regularMarketVolume which can also be stale).
      4. Surface data_age_seconds so callers can warn on staleness.
    """
    url_rt = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
              f"?interval=1m&range=1d&includePrePost=true")
    data_rt = _http_json(url_rt)
    result = data_rt["chart"]["result"][0]
    meta = result["meta"]

    timestamps = result.get("timestamp", []) or []
    quote_arr = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote_arr.get("close", []) or []
    volumes = quote_arr.get("volume", []) or []

    # Meta values used as fallbacks
    reg_price_meta = float(meta.get("regularMarketPrice") or 0.0)
    prev_close = float(meta.get("previousClose") or reg_price_meta)
    ccy = meta.get("currency", "USD")

    # currentTradingPeriod has session boundaries as unix timestamps
    period = meta.get("currentTradingPeriod", {}) or {}
    reg_start_ts = (period.get("regular", {}) or {}).get("start", 0) or 0
    reg_end_ts = (period.get("regular", {}) or {}).get("end", 0) or 0

    # === 1. Find latest non-null bar ===
    latest_close = 0.0
    latest_ts = 0
    for i in range(len(closes) - 1, -1, -1):
        c = closes[i]
        if c is not None and c > 0:
            latest_close = float(c)
            latest_ts = timestamps[i] if i < len(timestamps) else 0
            break

    data_age = int(time.time() - latest_ts) if latest_ts else -1

    # === 2. Determine last regular-session close (for POST comparison base) ===
    #
    # Tricky territory:
    #   * `meta.postMarketPrice` is cached/lagging — never use it.
    #   * `meta.regularMarketPrice`, despite its name, ALSO gets updated during
    #     extended hours on some symbols. Don't trust it as "today's close".
    #   * The 16:00:00 minute bar is unreliable: Yahoo sometimes attributes the
    #     first post-market trade to it (mixing the 4PM closing auction with
    #     the first AH print), and for thin tickers the bar is often null.
    #
    # Approach: walk backwards from the bar JUST BEFORE the regular session
    # ended (i.e. ts strictly less than reg_end_ts). That gives us the last
    # genuine intraday close. This skips the ambiguous 16:00 bar entirely.
    regular_session_close = 0.0
    if reg_end_ts and timestamps:
        for i in range(len(timestamps) - 1, -1, -1):
            if timestamps[i] < reg_end_ts:  # strictly before close
                c = closes[i] if i < len(closes) else None
                if c is not None and c > 0:
                    regular_session_close = float(c)
                    break
    # Fall back to meta.chartPreviousClose ladder only if timeseries gave nothing.
    if regular_session_close <= 0:
        regular_session_close = reg_price_meta or prev_close

    # === 3. Phase-aware price selection ===
    #
    # Baseline semantics:
    #   PRE     → vs previousClose (yesterday's close)
    #   REGULAR → vs previousClose
    #   POST    → vs previousClose (CUMULATIVE: yesterday → now, including AH)
    #             We separately stash today's regular close so the dropdown
    #             can render "After-hours +X.XX%" (current vs today's 4PM close).
    display_price, comparison_base, phase_icon = reg_price_meta, prev_close, ""
    today_reg_close = 0.0  # only populated in POST
    if latest_close > 0:
        if phase == "PRE":
            display_price, comparison_base, phase_icon = latest_close, prev_close, "🌅"
        elif phase == "POST":
            display_price, comparison_base, phase_icon = latest_close, prev_close, "🌙"
            today_reg_close = regular_session_close
        else:  # REGULAR or CLOSED
            display_price, comparison_base = latest_close, prev_close

    # === 4. Volume — sum regular-session minute bars (more reliable than meta) ===
    vol = int(meta.get("regularMarketVolume") or 0)
    if reg_start_ts and reg_end_ts and timestamps:
        summed = 0
        for i, ts in enumerate(timestamps):
            if reg_start_ts <= ts <= reg_end_ts and i < len(volumes):
                v = volumes[i]
                if v:
                    summed += int(v)
        if summed > 0:
            vol = summed

    spark = generate_sparkline(closes)

    # 10-day average volume (separate fetch)
    avg_v = vol
    try:
        url_h = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=15d&interval=1d"
        data_h = _http_json(url_h)
        v_list = [v for v in data_h["chart"]["result"][0]["indicators"]["quote"][0].get("volume", []) if v]
        if len(v_list) >= 11:
            avg_v = int(sum(v_list[-11:-1]) / 10)
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as e:
        log.info("Yahoo avg-vol fetch failed for %s: %s", symbol, e)

    pct = ((display_price - comparison_base) / comparison_base * 100) if comparison_base else 0.0
    return StockQuote(
        symbol=symbol, price=display_price, prev_close=comparison_base, pct_change=pct,
        volume=vol, avg_volume_10d=avg_v, currency_code=ccy,
        currency_symbol=get_currency_symbol(ccy), sparkline=spark,
        phase_icon=phase_icon, source="yahoo", data_age_seconds=data_age,
        today_regular_close=today_reg_close,
    )


def fetch_stock(symbol: str, phase: str = "REGULAR") -> StockQuote:
    """
    Dispatcher with phase-aware source selection.

    REGULAR session   → Alpaca primary, Yahoo fallback
    PRE / POST session → Yahoo primary,  Alpaca fallback

    Why the split:
      - Alpaca free tier is IEX-only (~2-3% of US equity volume). For liquid
        large caps during regular hours, IEX prints frequently and quotes are
        fresh. But during pre/post-market, IEX trades for small/mid caps
        (RKLB, LUNR, PL, ASTS, etc.) are sparse — `latestTrade.p` can be
        hours stale, showing an early pre-market price all evening.
      - Yahoo's chart API with `includePrePost=true` returns consolidated
        pre/post-market quotes (preMarketPrice / postMarketPrice in `meta`),
        which update reliably across all listed venues.

    Non-US tickers (`.HK`, `BRK-B` etc.) always go to Yahoo regardless of phase.
    """
    # Alpaca covers US equities only, and uses dot-form for share classes (BRK.B).
    # Symbols with `.` (foreign suffixes like .HK, .L, .TO) or `-` (Yahoo-style
    # share classes like BRK-B) get routed straight to Yahoo, which handles both.
    is_alpaca_eligible = "." not in symbol and "-" not in symbol
    alpaca_available = _alpaca_configured() and is_alpaca_eligible

    # Decide primary based on phase. In extended hours, IEX is too thin to trust.
    in_extended_hours = phase in ("PRE", "POST")
    use_alpaca_primary = alpaca_available and not in_extended_hours

    if use_alpaca_primary:
        primary, fallback = fetch_stock_alpaca, fetch_stock_yahoo
        primary_name, fallback_name = "Alpaca", "Yahoo"
    else:
        primary, fallback = fetch_stock_yahoo, fetch_stock_alpaca
        primary_name, fallback_name = "Yahoo", "Alpaca"

    # Try primary
    try:
        return primary(symbol, phase)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            log.error("%s auth failed (%d) for %s — check API credentials.", primary_name, e.code, symbol)
        else:
            log.warning("%s HTTP %d for %s, trying %s.", primary_name, e.code, symbol, fallback_name)
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
        log.info("%s failed for %s (%s), trying %s.", primary_name, symbol, e, fallback_name)

    # Fallback — only available if Alpaca is configured (Yahoo always available).
    # If primary was Yahoo and Alpaca isn't configured, skip the fallback attempt.
    if primary is fetch_stock_yahoo and not alpaca_available:
        return StockQuote(symbol=symbol, error="Timeout")

    try:
        return fallback(symbol, phase)
    except urllib.error.HTTPError as e:
        log.warning("%s HTTP %d for %s (fallback also failed)", fallback_name, e.code, symbol)
        return StockQuote(symbol=symbol, error=f"HTTP {e.code}")
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
        log.warning("%s fetch failed for %s: %s (fallback also failed)", fallback_name, symbol, e)
        return StockQuote(symbol=symbol, error="Timeout")


def fetch_finnhub_news() -> dict[str, str] | None:
    """Returns {'id': ..., 'headline': ...} for the latest top-news item, or None."""
    api_key = CONFIG.get("FINNHUB_API_KEY", "")
    if not api_key or api_key == "YOUR_FINNHUB_KEY_HERE":
        log.info("Finnhub API key not configured; skipping news fetch.")
        return None
    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = _http_json(url)
        if isinstance(data, list) and data:
            top = data[0]
            return {
                "id": str(top.get("id", "")),
                "headline": (top.get("headline") or "").strip(),
            }
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError, socket.timeout) as e:
        log.warning("Finnhub news fetch failed: %s", e)
    return None


def _treasury_from_cnbc_primary() -> TreasuryYield:
    """CNBC quote.htm — Tradeweb feed, true 24/5 data. Works on many networks
    but is sometimes 403-blocked from cloud IPs."""
    url = ("https://quote.cnbc.com/quote-html-webservice/quote.htm?"
           "noform=1&partnerId=2&fund=1&exthrs=1&output=json"
           "&symbolType=issue&symbols=US10Y")
    data = _http_json(url)
    quote = data.get("QuickQuoteResult", {}).get("QuickQuote", {})
    if isinstance(quote, list):
        quote = quote[0] if quote else {}
    current = float(quote.get("last", 0.0) or 0.0)
    change = float(quote.get("change", 0.0) or 0.0)
    if current <= 0:
        raise ValueError("empty CNBC response")
    return TreasuryYield(current=current, change=change, source="CNBC")


def _treasury_from_cnbc_rest() -> TreasuryYield:
    """CNBC restQuote — alternate URL with the same Tradeweb data underneath.

    Returns FormattedQuote (display-formatted) values like '4.595%' and '+0.012',
    not raw floats — so we strip percent signs / commas before parsing.
    """
    url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
           "?symbols=US10Y&requestMethod=itv&noform=1&partnerId=2&fund=1&output=json")
    data = _http_json(url)
    quote = data.get("FormattedQuoteResult", {}).get("FormattedQuote", {})
    if isinstance(quote, list):
        quote = quote[0] if quote else {}

    def _parse(v: Any) -> float:
        """Tolerate '4.595%', '+0.012', '1,234.56' or raw numbers."""
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace("%", "").replace(",", "").replace("+", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    current = _parse(quote.get("last"))
    change = _parse(quote.get("change"))
    if current <= 0:
        raise ValueError(f"CNBC-rest empty/zero last (got {quote.get('last')!r})")
    return TreasuryYield(current=current, change=change, source="CNBC-rest")


def _treasury_from_stooq() -> TreasuryYield:
    """Stooq CSV — Polish data provider, 24/5 coverage, plain-text CSV format.

    Symbol `10usy.b` is U.S. 10-Year Government Bond Yield. Endpoint returns
    one row: Symbol,Date,Time,Open,High,Low,Close,Volume

    Change is computed as (current - open), i.e. intraday move. This differs
    from "vs previous close" but is close enough for direction signaling, and
    bond markets typically have minimal weekend gap so the two are usually
    within 1-2 bps.
    """
    url = "https://stooq.com/q/l/?s=10usy.b&f=sd2t2ohlcv&h&e=csv"
    body = _http_text(url)
    # Body looks like:
    #   Symbol,Date,Time,Open,High,Low,Close,Volume
    #   10USY.B,2026-05-18,14:32:15,4.601,4.615,4.594,4.601,N/A
    lines = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError(f"Stooq returned no data rows: {body[:80]!r}")
    cols = lines[1].split(",")
    if len(cols) < 7:
        raise ValueError(f"Stooq malformed row: {cols}")
    try:
        open_val = float(cols[3])
        close_val = float(cols[6])
    except ValueError as e:
        raise ValueError(f"Stooq non-numeric OHLC: {cols} ({e})") from e
    if close_val <= 0:
        raise ValueError(f"Stooq close <= 0: {close_val}")
    return TreasuryYield(current=close_val, change=close_val - open_val, source="Stooq")


def _treasury_from_cnbc_html() -> TreasuryYield:
    """Scrape CNBC's public US10Y page as a last-ditch fallback.

    Fragile — depends on HTML structure — but if CNBC's API endpoints are
    blocking automated requests, the customer-facing page often still works
    because it's the same surface humans browse to.
    """
    import re
    url = "https://www.cnbc.com/quotes/US10Y"
    body = _http_text(url, timeout=2.5)
    # Look for the lastPrice block. The page embeds JSON in script tags and
    # also renders the price in a span. Try the JSON form first.
    # Pattern: "last":"4.601" within an inlined quote object
    m = re.search(r'"last"\s*:\s*"?([\d.]+)"?', body)
    last = float(m.group(1)) if m else 0.0
    m2 = re.search(r'"change"\s*:\s*"?(-?[\d.]+)"?', body)
    change = float(m2.group(1)) if m2 else 0.0
    if last <= 0:
        raise ValueError("CNBC HTML scrape did not yield a price")
    return TreasuryYield(current=last, change=change, source="CNBC-html")


def _treasury_from_yahoo_tnx() -> TreasuryYield:
    """Yahoo ^TNX — extremely reliable but RTH-only (frozen outside US market)."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1m&range=1d"
    data = _http_json(url)
    meta = data["chart"]["result"][0]["meta"]
    current = float(meta.get("regularMarketPrice") or 0.0)
    prev = float(meta.get("previousClose") or current)
    if current <= 0:
        raise ValueError("Yahoo returned 0")
    return TreasuryYield(current=current, change=current - prev, source="Yahoo")


# Source cascade — first one to return wins.
_TREASURY_SOURCES = [
    ("CNBC",       _treasury_from_cnbc_primary),
    ("CNBC-rest",  _treasury_from_cnbc_rest),
    ("Stooq",      _treasury_from_stooq),       # 24/5, reliable, network-agnostic
    ("CNBC-html",  _treasury_from_cnbc_html),   # last-ditch scrape
    ("Yahoo-TNX",  _treasury_from_yahoo_tnx),   # RTH-only, freezes overnight
]


def fetch_treasury_yield() -> TreasuryYield | None:
    """
    Try multiple 10Y yield sources in priority order. The first successful
    one wins; the rest aren't called. If all fail, returns None.

    Diagnostics: every failure is logged at INFO level, every success at
    INFO with source name. Watch `/tmp/xbar_stock.log` for `Treasury: ...`
    lines to see which source the menu bar is currently relying on.
    """
    for name, fetcher in _TREASURY_SOURCES:
        try:
            result = fetcher()
            log.info("Treasury: ok from %s (%.3f%%, change %+.3f)",
                     name, result.current, result.change)
            return result
        except urllib.error.HTTPError as e:
            log.info("Treasury: %s HTTP %d", name, e.code)
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError,
                TimeoutError, socket.timeout) as e:
            log.info("Treasury: %s failed (%s)", name, e)

    log.warning("Treasury: ALL sources failed")
    return None


def _treasury_arrow(change: float) -> str:
    """Direction glyph for the menu bar (color can't be partial-applied)."""
    if change > 0.0005:
        return "▲"
    if change < -0.0005:
        return "▼"
    return "▬"


def render_treasury_menubar(t: TreasuryYield) -> str:
    """Compact tag for the menu bar (no styling — inherits row color)."""
    return f"🇺🇸 10Y {t.current:.3f}% {_treasury_arrow(t.change)}{abs(t.change):.3f}"


def render_treasury_dropdown(t: TreasuryYield | None) -> str:
    """Verbose styled line for the dropdown."""
    if t is None:
        return "🇺🇸 U.S. 10Y Treasury: Fetch Error | color=#888888 size=13 font='Menlo Bold'"
    if t.change > 0.0005:
        color = CONFIG["COLOR_UP"]
    elif t.change < -0.0005:
        color = CONFIG["COLOR_DOWN"]
    else:
        color = CONFIG["COLOR_NORMAL"]
    sign = "+" if t.change >= 0 else ""
    return (f"🇺🇸 U.S. 10Y Treasury ({t.source}): {t.current:.3f}% "
            f"({sign}{t.change:.3f}) | color={color} size=13 font='Menlo Bold'")


def check_for_updates() -> str | None:
    """Check GitHub for a newer version. Result cached for 1 hour."""
    url = CONFIG.get("UPDATE_URL", "")
    if not url or "YOUR_GITHUB_NAME" in url:
        return None

    # Try cache first
    try:
        cache = json.loads(OTA_CACHE_FILE.read_text())
        if time.time() - cache.get("checked_at", 0) < OTA_CACHE_TTL_SECONDS:
            v = cache.get("latest_version")
            return v if v and v > CURRENT_VERSION else None
    except (OSError, json.JSONDecodeError):
        pass

    try:
        req = urllib.request.Request(url, headers={"User-Agent": random.choice(USER_AGENTS)})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            remote = resp.read().decode("utf-8").strip()
        atomic_write_json(OTA_CACHE_FILE, {"checked_at": time.time(), "latest_version": remote})
        return remote if remote and remote > CURRENT_VERSION else None
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        log.info("OTA check failed: %s", e)
        return None


# ─── Alert engine ───────────────────────────────────────────────────────────
#
# Four kinds of alerts, listed in `ALERT_PRIORITY`. Detection happens in this
# order each tick:
#   1. STOCK (% threshold) and PRICE (absolute target) — `detect_stock_alerts`
#   2. NEWS (Finnhub headline change) — `detect_news_alert`
#   3. EQUITY (portfolio threshold) — `detect_equity_alerts`
#
# Each call to `try_trigger_alert` performs three checks:
#   a) Dedup: same `key` (e.g. "AAPL_UP_5") fires at most once per day.
#   b) Priority: a lower-priority alert can't visually preempt a currently
#      active higher-priority one (it still marks itself as triggered for
#      dedup purposes).
#   c) Display: on success, set `pause_*` fields that the renderer reads to
#      lock the menu bar for FREEZE_DURATION seconds.
#
# Cooldown (#STOCK_ALERT_COOLDOWN_MINUTES) is enforced by the caller, not
# by `try_trigger_alert` itself — see `detect_stock_alerts`.
# ────────────────────────────────────────────────────────────────────────────

def try_trigger_alert(
    state: AlertState,
    *,
    key: str,
    alert_type: str,
    color: str,
    msg: str,
    freeze_duration: int,
    now_ts: float,
    group_idx: int,
) -> bool:
    """
    Attempt to fire an alert. Returns True if it fired (newly-triggered AND
    high-enough priority to take over the menu bar).

    Always marks the key as triggered to prevent re-firing the same alert
    within the day — even if a higher-priority alert is currently visible.
    """
    if key in state.triggered:
        return False
    state.triggered[key] = True

    incoming = ALERT_PRIORITY.get(alert_type, 0)
    if incoming < state.current_priority() and state.pause_until > now_ts:
        # Higher-priority alert already on screen — record-only.
        log.info("Alert %s suppressed by active %s", key, state.alert_type)
        return False

    state.pause_until = now_ts + freeze_duration
    state.pause_group_idx = group_idx
    state.pause_color = color
    state.alert_msg = msg
    state.alert_type = alert_type
    log.info("Alert fired: %s (%s)", key, alert_type)
    return True


def detect_stock_alerts(
    state: AlertState,
    quotes: list[StockQuote],
    group_idx: int,
    now_ts: float,
) -> bool:
    """Scan ticker quotes for percentage-threshold and price-target alerts.

    Per-symbol cooldown: after any stock/price alert fires for symbol X,
    suppress further stock/price alerts for that same symbol for
    STOCK_ALERT_COOLDOWN_MINUTES. This prevents noise during fast volatile
    moves (e.g. crossing +5%, +10%, +15% within one minute).

    Cooldown does NOT affect equity or news alerts (different priority class).
    Cooldown also doesn't affect the per-key dedup — even after cooldown
    expires, the same `LUNR_UP_5` key never re-fires on the same day.
    """
    fired = False
    freeze = CONFIG.get("FREEZE_DURATION", 30)
    cooldown_seconds = float(CONFIG.get("STOCK_ALERT_COOLDOWN_MINUTES", 5)) * 60.0
    price_alerts_cfg = CONFIG.get("PRICE_ALERTS", {})

    for q in quotes:
        if not q.ok:
            continue

        # Cooldown gate: skip ALL stock/price alerts for this symbol if it
        # recently fired one. Returns False (no alert fired this call).
        last = state.last_alert_at.get(q.symbol, 0.0)
        if last and (now_ts - last) < cooldown_seconds:
            remaining = int(cooldown_seconds - (now_ts - last))
            log.info("Stock alert cooldown for %s: %ds remaining", q.symbol, remaining)
            continue

        sym_fired = False

        # A. Percentage threshold alerts
        for threshold in CONFIG["THRESHOLDS"]:
            if abs(q.pct_change) < threshold:
                continue
            direction = "UP" if q.pct_change > 0 else "DOWN"
            icon = "📈" if direction == "UP" else "📉"
            color = CONFIG["COLOR_UP"] if direction == "UP" else CONFIG["COLOR_DOWN"]
            if try_trigger_alert(
                state,
                key=f"{q.symbol}_{direction}_{threshold}",
                alert_type="STOCK",
                color=color,
                msg=f"{icon} STOCK ALERT: {q.symbol} {direction} {threshold}%",
                freeze_duration=freeze,
                now_ts=now_ts,
                group_idx=group_idx,
            ):
                sym_fired = True

        # B. Custom price targets
        targets = price_alerts_cfg.get(q.symbol, {})
        if "above" in targets and q.price >= targets["above"]:
            if try_trigger_alert(
                state,
                key=f"{q.symbol}_PRICE_ABOVE_{targets['above']}",
                alert_type="PRICE",
                color=CONFIG["COLOR_UP"],
                msg=f"🎯 TARGET REACHED: {q.symbol} > ${targets['above']}",
                freeze_duration=freeze,
                now_ts=now_ts,
                group_idx=group_idx,
            ):
                sym_fired = True
        if "below" in targets and q.price <= targets["below"]:
            if try_trigger_alert(
                state,
                key=f"{q.symbol}_PRICE_BELOW_{targets['below']}",
                alert_type="PRICE",
                color=CONFIG["COLOR_DOWN"],
                msg=f"🛑 PRICE DROP: {q.symbol} < ${targets['below']}",
                freeze_duration=freeze,
                now_ts=now_ts,
                group_idx=group_idx,
            ):
                sym_fired = True

        if sym_fired:
            state.last_alert_at[q.symbol] = now_ts
            fired = True

    return fired


def detect_news_alert(state: AlertState, news: dict[str, str] | None, group_idx: int, now_ts: float) -> bool:
    """Compare incoming news to last-seen by id (preferred) or title."""
    if not news or not news.get("headline"):
        return False

    incoming_id = news.get("id", "")
    incoming_title = news["headline"]
    last_id = state.last_news_id
    last_title = state.last_news_title

    # First-boot: record silently
    if not last_id and not last_title:
        state.last_news_id = incoming_id
        state.last_news_title = incoming_title
        return False

    # Dedup: prefer id, fall back to title
    is_new = (incoming_id and incoming_id != last_id) or (not incoming_id and incoming_title != last_title)
    if not is_new:
        return False

    state.last_news_id = incoming_id
    state.last_news_title = incoming_title

    return try_trigger_alert(
        state,
        key=f"NEWS_{incoming_id or incoming_title[:32]}",
        alert_type="NEWS",
        color="#FFDD00",
        msg=f"📰 BREAKING: {incoming_title}",
        freeze_duration=30,  # hardcoded for news
        now_ts=now_ts,
        group_idx=group_idx,
    )


def detect_equity_alerts(
    state: AlertState,
    current_equity: float,
    group_idx: int,
    now_ts: float,
) -> bool:
    """Check global equity thresholds."""
    fired = False
    freeze = CONFIG.get("FREEZE_DURATION", 30)
    acct = CONFIG.get("ACCOUNT", {})
    eq_high = float(acct.get("EQUITY_ALERT_HIGH", 0.0) or 0.0)
    eq_low = float(acct.get("EQUITY_ALERT_LOW", 0.0) or 0.0)

    if eq_high > 0 and current_equity >= eq_high:
        fired |= try_trigger_alert(
            state,
            key=f"EQUITY_HIGH_{int(eq_high)}",
            alert_type="EQUITY_HIGH",
            color=CONFIG["COLOR_UP"],
            msg=f"🎯 EQUITY TARGET REACHED: ${current_equity:,.0f}",
            freeze_duration=freeze,
            now_ts=now_ts,
            group_idx=group_idx,
        )
    if eq_low > 0 and current_equity <= eq_low:
        fired |= try_trigger_alert(
            state,
            key=f"EQUITY_LOW_{int(eq_low)}",
            alert_type="EQUITY_LOW",
            color=CONFIG["COLOR_DOWN"],
            msg=f"🛑 RISK ALERT - LOW EQUITY: ${current_equity:,.0f}",
            freeze_duration=freeze,
            now_ts=now_ts,
            group_idx=group_idx,
        )
    return fired


# ==================== [ PORTFOLIO ] ====================

@dataclass
class PortfolioTotals:
    market_value: float = 0.0
    unrealized_pl: float = 0.0
    today_pl: float = 0.0
    active: bool = False
    mixed_currency: bool = False
    currency_symbol: str = "$"


def calculate_portfolio(quotes_by_symbol: dict[str, StockQuote]) -> PortfolioTotals:
    """
    Compute portfolio totals. TODO: multi-currency conversion not yet supported;
    if the portfolio contains mixed currencies we skip the totals and flag it.
    """
    totals = PortfolioTotals()
    seen_currencies: set[str] = set()

    for sym, pos in CONFIG.get("PORTFOLIO", {}).items():
        shares = pos.get("shares", 0)
        if shares <= 0:
            continue
        q = quotes_by_symbol.get(sym)
        if not q or not q.ok:
            continue

        seen_currencies.add(q.currency_code)
        cost = pos.get("cost_basis", 0.0)
        mv = q.price * shares
        totals.market_value += mv
        totals.unrealized_pl += mv - (cost * shares)
        totals.today_pl += (q.price - q.prev_close) * shares
        totals.active = True
        totals.currency_symbol = q.currency_symbol

    if len(seen_currencies) > 1:
        totals.mixed_currency = True
        log.warning("Mixed-currency portfolio detected: %s — totals suppressed.", seen_currencies)

    return totals


# ==================== [ RENDERING ] ====================

def play_sound() -> None:
    """Fire-and-forget Glass.aiff via subprocess (no shell)."""
    try:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Glass.aiff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        log.info("afplay failed: %s", e)


def send_notification(title: str, body: str, silent: bool = False) -> None:
    """Post a macOS Notification Center notification via osascript.

    Persists in the notification center after the menu bar's 30s freeze ends —
    so post-market alerts (PRE/POST sessions) are still visible after the
    20:00 sleep cut-off.

    `silent=True` suppresses the system notification sound (we use afplay
    separately so we can gate sound on market phase).
    """
    def esc(s: str) -> str:
        # Strip newlines + escape double quotes and backslashes for AppleScript.
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    sound_clause = "" if silent else ' sound name "Glass"'
    script = (f'display notification "{esc(body)}" '
              f'with title "{esc(title)}"{sound_clause}')
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        log.info("osascript notification failed: %s", e)


def notify_for_alert(state: AlertState, phase: str) -> None:
    """Translate an `AlertState` into a macOS notification.

    Title varies by alert type so notifications stack readably in Notification
    Center. Body is the same banner text shown in the menu bar.

    Notification sound is suppressed in PRE/POST (same policy as afplay) but
    the visual notification fires regardless of phase — which is the whole
    point: it persists past the 30s freeze, past 20:00 sleep cutoff, etc.
    """
    if not CONFIG.get("ENABLE_NOTIFICATIONS", True):
        return
    titles = {
        "STOCK":       "📈 Stock Alert",
        "PRICE":       "🔔 Price Alert",
        "NEWS":        "📰 Breaking News",
        "EQUITY_HIGH": "🎯 Equity Target",
        "EQUITY_LOW":  "🛑 Equity Risk",
    }
    title = titles.get(state.alert_type, "Alert")
    silent = (phase != "REGULAR")  # match the sound-gate policy
    send_notification(title, state.alert_msg, silent=silent)


# ==================== [ MENU OUTPUT ACCUMULATOR ] ====================

class MenuOutput:
    """Accumulator for xbar menu lines.

    Why this exists: xbar reads stdout, one line at a time, with `---` as
    a section separator. Previously every render path called `print()`
    directly, which made it impossible to:
      * dry-run rendering (e.g. in tests)
      * inject debug info uniformly (heartbeat dot, version footer)
      * reorder or conditionally hide sections cleanly

    Now every render function returns lines via this object, and `main()`
    flushes everything to stdout in one place at the very end.
    """

    def __init__(self) -> None:
        self._lines: list[str] = []

    def line(self, text: str) -> None:
        """Append a single menu line."""
        self._lines.append(text)

    def lines(self, items: Iterable[str]) -> None:
        """Append many lines."""
        self._lines.extend(items)

    def sep(self) -> None:
        """Append the `---` section separator. Idempotent: never emits two in a row."""
        if not self._lines or self._lines[-1] != "---":
            self._lines.append("---")

    def flush(self) -> None:
        """Write everything to stdout. Called exactly once per script run."""
        # Strip leading/trailing separators that don't render usefully.
        while self._lines and self._lines[0] == "---":
            self._lines.pop(0)
        while self._lines and self._lines[-1] == "---":
            self._lines.pop()
        sys.stdout.write("\n".join(self._lines) + "\n")
        sys.stdout.flush()


def render_deep_sleep(out: MenuOutput, reason: str, now: datetime) -> None:
    out.line(f"🌑 | {FONT_SETTINGS} color={CONFIG['COLOR_NORMAL']}")
    out.sep()
    out.line(f"Status: {reason} - Last: {now.strftime('%X')} EST")
    # Use shell=open + shellparams to reliably open files with dot-prefix names.
    # `href=file://` is unreliable for dotfiles on some xbar versions.
    out.line(f"📝 Edit Config File | shell=open param1={CONFIG_FILE} terminal=false")
    out.sep()
    out.line("☕ Buy Me a Coffee | href=https://buymeacoffee.com/nathanieljiang color=#FFDD00")
    out.line(f"v{CURRENT_VERSION} | color=#888888 size=11")


def render_ticker_part(q: StockQuote, icons: dict[str, str]) -> str:
    if not q.ok:
        return f"{q.symbol} [{q.error}]"
    display = icons.get(q.symbol, q.symbol)
    return f"{q.phase_icon}{display} {q.currency_symbol}{q.price:.2f} {q.change_label} {q.sparkline}"


def render_dropdown_line(q: StockQuote, icons: dict[str, str]) -> list[str]:
    """Render one stock's dropdown rows. Returns 1 line normally, 2 in POST phase."""
    if not q.ok:
        return [f"{q.symbol}: API Blocked - {q.error}"]
    display = icons.get(q.symbol, q.symbol)

    # Source tag with freshness hint. If data is > 60s old, surface a warning.
    src_label = "Alpaca" if q.source == "alpaca" else "Yahoo"
    if q.data_age_seconds >= 0:
        bar_local = datetime.fromtimestamp(time.time() - q.data_age_seconds, EASTERN).strftime("%H:%M")
        if q.data_age_seconds > 60:
            mins = q.data_age_seconds // 60
            src_label = f"{src_label} ⚠️ {mins}m old (last bar {bar_local})"
        else:
            src_label = f"{src_label} @ {bar_local}"

    line = (f"{display} ({q.symbol}) • Vol: {format_volume(q.volume)} "
            f"vs 10D: {format_volume(q.avg_volume_10d)} • via {src_label}")

    pos = CONFIG.get("PORTFOLIO", {}).get(q.symbol, {})
    shares = pos.get("shares", 0)
    if shares > 0:
        cost = pos.get("cost_basis", 0.0)
        mv = q.price * shares
        unrealized = mv - (cost * shares)
        today_pl = (q.price - q.prev_close) * shares
        sign = "+" if unrealized >= 0 else "-"
        t_sign = "+" if today_pl >= 0 else "-"
        pl_color = CONFIG["COLOR_UP"] if today_pl >= 0 else CONFIG["COLOR_DOWN"]
        line += (f" • 💰 P&L: {sign}{q.currency_symbol}{abs(unrealized):,.2f} "
                 f"(Today: {t_sign}{q.currency_symbol}{abs(today_pl):,.2f}) | color={pl_color}")

    line += f" | href=https://finance.yahoo.com/quote/{q.symbol}"
    lines = [line]

    # === Extended-hours segment line (POST/PRE) ===
    # Show pure extended-hours move: (current price) vs (today's 4PM close).
    if q.today_regular_close > 0:
        ah_delta = q.price - q.today_regular_close
        ah_pct = (ah_delta / q.today_regular_close * 100) if q.today_regular_close else 0.0
        sign = "+" if ah_delta >= 0 else "-"
        ah_color = CONFIG["COLOR_UP"] if ah_delta >= 0 else CONFIG["COLOR_DOWN"]
        seg_line = f"    🌙 After-hours: {sign}{abs(ah_pct):.2f}%"
        if shares > 0:
            seg_pl = ah_delta * shares
            seg_line += f"  ({sign}{q.currency_symbol}{abs(seg_pl):,.2f})"
        seg_line += f" | color={ah_color} size=12 font='Menlo'"
        lines.append(seg_line)

    return lines


def render_menubar_string(
    ordered_quotes: list[StockQuote],
    state: AlertState,
    is_paused: bool,
    is_stock_active: bool,
    icons: dict[str, str],
    treasury: TreasuryYield | None = None,
    freshness: str = "",
) -> str:
    # News fully overrides the menu bar
    if is_paused and state.alert_type == "NEWS":
        return state.alert_msg

    if not is_stock_active:
        return "📡 News Radar ON [Market Closed]"

    parts = [render_ticker_part(q, icons) for q in ordered_quotes]
    bar = "   ".join(parts)

    # Append 10Y treasury yield to the right of tickers (if configured).
    # Note: menu bar entries share a single color attribute, so the yield
    # inherits the row color (alert color when paused, normal otherwise).
    # Direction is conveyed by the ▲ / ▼ glyph instead of color.
    if treasury and CONFIG.get("SHOW_TREASURY_IN_MENUBAR", True):
        bar = f"{bar}  │  {render_treasury_menubar(treasury)}"

    # Freshness heartbeat — one-glyph indicator of how recent the data is.
    # · (small dot)   = fresh, ≤ 30s old
    # ∘ (open circle) = warm, ≤ 2 min
    # ⚠ (warning)     = stale, > 2 min — something's wrong with a fetcher
    if freshness:
        bar = f"{bar} {freshness}"

    if is_paused:
        if state.alert_type == "EQUITY_HIGH":
            return "🎯 [HIGH EQUITY] " + bar
        if state.alert_type == "EQUITY_LOW":
            return "🛑 [LOW EQUITY] " + bar
        if state.alert_type == "PRICE":
            return "🔔 [PRICE ALERT] " + bar
    return bar


def render_portfolio_block(out: MenuOutput, totals: PortfolioTotals) -> None:
    if not totals.active:
        return
    margin = float(CONFIG.get("ACCOUNT", {}).get("margin_used", 0.0))
    equity = totals.market_value - margin

    out.line("🏦 PORTFOLIO TOTAL | color=#191970 size=14 font='Menlo Bold'")
    if totals.mixed_currency:
        out.line("⚠️  Mixed currencies detected — totals suppressed "
                 "| color=#FF8C00 size=13 font='Menlo Bold'")
        out.line("(TODO: multi-currency FX conversion not implemented) "
                 "| color=#888888 size=12")
        return

    cs = totals.currency_symbol
    out.line(f"💵 Equity: {cs}{equity:,.2f} (Margin: {cs}{margin:,.2f}) "
             f"| color=#2F4F4F size=13 font='Menlo Bold'")

    tot_sign = "+" if totals.unrealized_pl >= 0 else "-"
    t_sign = "+" if totals.today_pl >= 0 else "-"
    pl_color = CONFIG["COLOR_UP"] if totals.today_pl >= 0 else CONFIG["COLOR_DOWN"]
    out.line(f"💰 Total P&L: {tot_sign}{cs}{abs(totals.unrealized_pl):,.2f} "
             f"(Today: {t_sign}{cs}{abs(totals.today_pl):,.2f}) "
             f"| color={pl_color} size=13 font='Menlo Bold'")


# ==================== [ MAIN ORCHESTRATOR ] ====================

def order_display_quotes(
    quotes: list[StockQuote],
    current_syms: list[str],
    quotes_by_sym: dict[str, StockQuote],
) -> list[StockQuote]:
    """Apply Smart Sort or preserve user-defined order."""
    if CONFIG.get("SMART_SORT", False):
        valid = [q for q in quotes if q.symbol in current_syms and q.ok]
        valid.sort(key=lambda q: abs(q.pct_change), reverse=True)
        groups = CONFIG.get("TICKER_GROUPS") or []
        limit = len(groups[0]) if groups else 2
        return valid[:limit]
    return [quotes_by_sym[s] for s in current_syms if s in quotes_by_sym]


def render_config_errors(out: MenuOutput, errors: list[str]) -> None:
    """Render a friendly menu-bar warning instead of crashing on bad config."""
    out.line(f"⚠️ Config error ({len(errors)}) | {FONT_SETTINGS} color=#FF8C00")
    out.sep()
    out.line(f"Found {len(errors)} problem(s) in {CONFIG_FILE.name}:")
    out.sep()
    for err in errors:
        out.line(f"• {err} | color=#DC143C")
    out.sep()
    out.line(f"📝 Open Config to Fix | href=file://{CONFIG_FILE}")
    out.line(f"📄 Open Log | href=file://{LOG_FILE}")
    out.line("🔄 Refresh All | refresh=true")


# ==================== [ MAIN ORCHESTRATION HELPERS ] ====================

def decide_display_group(
    state: AlertState, smart_sort: bool, groups: list, now_ts: float
) -> tuple[int, list[str]]:
    """Pick which group of tickers to display this tick.

    Returns (group_idx, current_syms).

    Logic:
      * If an alert is currently freezing the menu bar, lock to that alert's group.
      * If SMART_SORT, always group 0 (we'll re-sort by volatility later).
      * Otherwise round-robin advance.
    """
    if state.is_paused(now_ts):
        group_idx = state.pause_group_idx if state.pause_group_idx < len(groups) else 0
    elif smart_sort:
        group_idx = 0
    else:
        group_idx = get_and_advance_group_index(len(groups))
        if group_idx >= len(groups):
            group_idx = 0

    if smart_sort:
        current_syms = sorted({s for g in groups for s in g})
    else:
        current_syms = groups[group_idx] if groups else []
    return group_idx, current_syms


def partition_cache(
    cache: dict, all_syms: list[str], phase: str, now_ts: float
) -> tuple[dict[str, StockQuote], list[str]]:
    """Split symbol list into (cache_hits, cache_misses)."""
    hits: dict[str, StockQuote] = {}
    misses: list[str] = []
    for sym in all_syms:
        cached = cache_get_quote(cache, sym, phase, now_ts)
        if cached:
            hits[sym] = cached
        else:
            misses.append(sym)
    return hits, misses


def fetch_missing(
    syms_to_fetch: list[str], phase: str, want_news: bool, want_treasury: bool
) -> tuple[list[StockQuote], dict | None, TreasuryYield | None]:
    """Run all needed network fetches concurrently.

    Skips the ThreadPoolExecutor entirely if there's nothing to fetch —
    measurable savings on full-cache-hit ticks.
    """
    quotes: list[StockQuote] = []
    news: dict | None = None
    treasury: TreasuryYield | None = None

    if not (syms_to_fetch or want_news or want_treasury):
        return quotes, news, treasury

    max_workers = max(2, min(15, len(syms_to_fetch) + 2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        quote_futures = {ex.submit(fetch_stock, s, phase): s for s in syms_to_fetch}
        news_future = ex.submit(fetch_finnhub_news) if want_news else None
        treasury_future = ex.submit(fetch_treasury_yield) if want_treasury else None

        for fut in concurrent.futures.as_completed(quote_futures):
            quotes.append(fut.result())
        if news_future:
            news = news_future.result()
        if treasury_future:
            treasury = treasury_future.result()
    return quotes, news, treasury


def freshness_dot(quotes: list[StockQuote], now_ts: float) -> str:
    """Compact 1-char freshness indicator for the menu bar.

    Computed from the OLDEST data_age of all visible quotes. If any quote is
    stale, the dot warns about it. Returns "" if there's nothing to show
    (e.g. deep sleep, or all-error quotes).
    """
    ages = [q.data_age_seconds for q in quotes if q.ok and q.data_age_seconds >= 0]
    if not ages:
        return ""
    worst = max(ages)
    if worst <= 30:
        return "·"      # fresh: small dot
    if worst <= 120:
        return "∘"      # warm: open circle (≤ 2 min)
    return "⚠"          # stale: warning glyph


def render_metrics_to_log(
    n_cache_hits: int, n_cache_misses: int, n_errors: int, phase: str
) -> None:
    """Tick-level metrics → log. Aggregating summary lives in a future module."""
    log.info("Tick: phase=%s cache_hits=%d cache_misses=%d errors=%d",
             phase, n_cache_hits, n_cache_misses, n_errors)


def decide_alerts(
    state: AlertState,
    ordered_quotes: list[StockQuote],
    all_quotes_by_sym: dict[str, StockQuote],
    news: dict | None,
    group_idx: int,
    market: MarketWindow,
    now_ts: float,
) -> tuple[bool, PortfolioTotals]:
    """Run all alert detectors in priority order; return (any_fired, totals)."""
    fired = False
    if market.is_stock_active and ordered_quotes:
        fired |= detect_stock_alerts(state, ordered_quotes, group_idx, now_ts)
    fired |= detect_news_alert(state, news, group_idx, now_ts)

    totals = calculate_portfolio(all_quotes_by_sym) if market.is_stock_active else PortfolioTotals()
    if totals.active and not totals.mixed_currency:
        margin = float(CONFIG.get("ACCOUNT", {}).get("margin_used", 0.0))
        fired |= detect_equity_alerts(state, totals.market_value - margin, group_idx, now_ts)
    return fired, totals


def react_to_alerts(state: AlertState, any_fired: bool, phase: str) -> None:
    """Persist state, then optionally play sound and post notification."""
    state.save()
    if not any_fired:
        return
    if CONFIG.get("ENABLE_SOUND_ALERT", False) and phase == "REGULAR":
        play_sound()
    elif CONFIG.get("ENABLE_SOUND_ALERT", False):
        log.info("Alert fired during %s session — sound suppressed (visual only).", phase)
    notify_for_alert(state, phase)


def render_dropdown_section(
    out: MenuOutput,
    market: MarketWindow,
    totals: PortfolioTotals,
    ordered: list[StockQuote],
    treasury: TreasuryYield | None,
    icons: dict[str, str],
) -> None:
    """Render everything that goes below the menu bar — portfolio block,
    each ticker's lines, treasury yield row."""
    if market.is_stock_active and totals.active:
        render_portfolio_block(out, totals)
        out.sep()
    elif not market.is_stock_active:
        out.line("Market Data and P&L Paused | color=#2F4F4F size=13")
        out.line("News Engine is actively monitoring Finnhub... | color=#191970 size=13")
        out.sep()

    for q in ordered:
        for line in render_dropdown_line(q, icons):
            out.line(line)
    if market.is_stock_active and ordered:
        out.sep()

    out.line(render_treasury_dropdown(treasury))
    out.sep()


def render_footer(
    out: MenuOutput,
    state: AlertState,
    now: datetime,
    now_ts: float,
    smart_sort: bool,
    market: MarketWindow,
) -> None:
    """Status line + last-news ping + config link + refresh button."""
    new_version = check_for_updates()
    if new_version:
        repo_url = (CONFIG.get("UPDATE_URL", "")
                    .replace("raw.githubusercontent.com", "github.com")
                    .replace("/main/version.txt", ""))
        out.line(f"🚀 V{new_version} Update Available! | color=#FF8C00 href={repo_url}")
        out.sep()

    if state.is_paused(now_ts):
        time_left = max(0, int(state.pause_until - now_ts))
        out.line(f"{state.alert_msg} ({time_left}s left) | color=#FF8C00 font='Menlo Bold'")
    elif smart_sort and market.is_stock_active:
        out.line(f"🔥 SMART SORT MODE ACTIVE - {now.strftime('%X')} EST | color=#FF8C00")
    else:
        phase_text = f"Phase: {market.phase}" if market.is_stock_active else "Phase: PRE/POST (News Only)"
        out.line(f"{phase_text} - Last Update: {now.strftime('%X')} EST")
    out.sep()

    last_news = state.last_news_title
    if last_news:
        out.line(f"🗞️ Finnhub Ping: {last_news[:65]}... | color=#888888 size=12")
        out.sep()

    out.line(f"v{CURRENT_VERSION} | color=#888888 size=11")
    out.line(f"⚙️ Edit Watchlist & Config | shell=open param1={CONFIG_FILE} terminal=false")
    out.line(f"📄 View Log | shell=open param1={LOG_FILE} terminal=false")
    # Optional sponsor link — set SPONSOR_URL to "" in this file to remove.
    out.line("☕ Buy Me a Coffee | href=https://buymeacoffee.com/nathanieljiang color=#FFDD00")
    out.line("🔄 Refresh All | refresh=true")


def main() -> None:
    out = MenuOutput()
    # Heartbeat: every invocation logs here. If xbar stops calling the script
    # (e.g. macOS App Nap, xbar crash), the log will show a gap — making
    # "is xbar still polling me?" diagnosable.
    log.info("Tick start")

    # Guard rail: surface bad config in the menu bar rather than crashing
    # in deep call stacks (e.g. KeyError inside a fetcher's float() call).
    config_errors = validate_config(CONFIG)
    if config_errors:
        for err in config_errors:
            log.error("Config error: %s", err)
        render_config_errors(out, config_errors)
        out.flush()
        return

    now = datetime.now(EASTERN)
    now_ts = time.time()
    today_str = now.strftime("%Y-%m-%d")
    market = MarketWindow(now)

    # Deep sleep: weekend or outside active hours.
    if market.is_weekend or not market.is_news_active:
        render_deep_sleep(out, "Weekend" if market.is_weekend else "Deep Sleep", now)
        out.flush()
        return

    state = AlertState.load(today_str)

    # ---- 1. Decide what to display this tick ----
    groups = CONFIG.get("TICKER_GROUPS") or [[]]
    smart_sort = CONFIG.get("SMART_SORT", False)
    group_idx, current_syms = decide_display_group(state, smart_sort, groups, now_ts)

    portfolio_syms = list(CONFIG.get("PORTFOLIO", {}).keys()) if market.is_stock_active else []
    all_fetch_syms = sorted(set(current_syms) | set(portfolio_syms))

    # ---- 2. Cache lookup ----
    quote_cache = load_quote_cache()
    cache_hits: dict[str, StockQuote] = {}
    syms_to_fetch: list[str] = []
    if market.is_stock_active:
        cache_hits, syms_to_fetch = partition_cache(quote_cache, all_fetch_syms, market.phase, now_ts)

    cached_treasury = cache_get_treasury(quote_cache, now_ts)
    cached_news = cache_get_news(quote_cache, now_ts)
    need_news = CONFIG.get("ENABLE_NEWS_ALERTS", True) and cached_news is None
    need_treasury = cached_treasury is None

    # ---- 3. Concurrent fetch for cache misses ----
    fetched_quotes, fetched_news, fetched_treasury = fetch_missing(
        syms_to_fetch, market.phase, need_news, need_treasury
    )
    news = fetched_news if fetched_news is not None else cached_news
    treasury = fetched_treasury if fetched_treasury is not None else cached_treasury

    # ---- 4. Cache write-back ----
    for q in fetched_quotes:
        cache_put_quote(quote_cache, q, market.phase, now_ts)
    if need_treasury and fetched_treasury is not None:
        cache_put_treasury(quote_cache, fetched_treasury, now_ts)
    if need_news and fetched_news is not None:
        cache_put_news(quote_cache, fetched_news, now_ts)
    save_quote_cache(quote_cache)

    # Metrics for this tick.
    n_errors = sum(1 for q in fetched_quotes if not q.ok)
    render_metrics_to_log(len(cache_hits), len(syms_to_fetch), n_errors, market.phase)

    # ---- 5. Merge data + order for display ----
    quotes: list[StockQuote] = list(cache_hits.values()) + fetched_quotes
    quotes_by_sym = {q.symbol: q for q in quotes}
    ordered = order_display_quotes(quotes, current_syms, quotes_by_sym) if market.is_stock_active else []

    # ---- 6. Alerts ----
    any_fired, totals = decide_alerts(state, ordered, quotes_by_sym, news, group_idx, market, now_ts)
    react_to_alerts(state, any_fired, market.phase)

    # ---- 7. Render ----
    is_paused = state.is_paused(now_ts)
    current_color = state.pause_color if is_paused else CONFIG["COLOR_NORMAL"]
    icons = CONFIG.get("TICKER_ICONS", {})
    freshness = freshness_dot(ordered, now_ts) if market.is_stock_active else ""

    menubar = render_menubar_string(
        ordered, state, is_paused, market.is_stock_active, icons, treasury, freshness
    )
    out.line(f"{menubar} | {FONT_SETTINGS} color={current_color}")
    out.sep()

    render_dropdown_section(out, market, totals, ordered, treasury, icons)
    render_footer(out, state, now, now_ts, smart_sort, market)

    out.flush()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 — last-resort UI guard
        log.exception("Fatal error in main()")
        print(f"⚠️ Terminal Crash | font='Menlo Bold' size=14 color=#FF3333 dropdown=false")
        print("---")
        print(f"Fatal Error: {e}")
        print(f"Log: {LOG_FILE}")
        print(f"Config: {CONFIG_FILE}")