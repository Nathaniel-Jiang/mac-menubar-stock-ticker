# Menu Bar Stock Terminal

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-%E2%98%95-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/nathanieljiang)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/macOS-13%2B-black?style=for-the-badge&logo=apple)](https://www.apple.com/macos/)

A live ticker, portfolio P&L tracker, and alert engine that lives in your macOS
menu bar. Built as a single-file Python plugin for [xbar](https://xbarapp.com)
or [SwiftBar](https://swiftbar.app).

```
🚀 $124.33 ▲1.2% ▂▃▄▅   🌕 $34.45 ▲2.5% ▆▅▄   🌎 $41.86 ▲0.7% ▄▆▄  │  🇺🇸 10Y 4.42% ▲0.012 ·
```

## Why

If you want a market overview that's always visible without keeping a browser
tab open — but you don't want a heavyweight trading app eating CPU all day —
this fills a small but real gap.

## Features

- **Real-time quotes** with pre/post-market support
- **Multi-source data**: Alpaca (free tier) primary, Yahoo Finance fallback
- **Portfolio P&L**: per-stock and global, with margin-aware equity tracking
- **5-source treasury cascade**: U.S. 10Y yield from CNBC → Stooq → Yahoo
- **Smart alerts**: percentage thresholds + absolute price targets + portfolio equity
- **Phase-aware audio**: silent in pre/post, audible during RTH
- **macOS notifications** persist past the menu-bar freeze window
- **Breaking news** via Finnhub
- **Zero dependencies**: stdlib only, no `pip install`

## Quick start

1. Install [xbar](https://xbarapp.com) (recommended) or [SwiftBar](https://swiftbar.app)
2. Copy `xbar_stock_ticker.py` into the xbar plugins folder, renamed with a
   refresh-interval suffix:
   ```bash
   cp xbar_stock_ticker.py \
     ~/Library/Application\ Support/xbar/plugins/stock.8s.py
   chmod +x ~/Library/Application\ Support/xbar/plugins/stock.8s.py
   ```
3. Click the xbar icon → **Refresh All** — this creates `~/.xbar_stock_config.json`
   with safe defaults
4. Edit your config:
   ```bash
   nano ~/.xbar_stock_config.json
   ```
5. Tighten permissions (the file now holds API keys):
   ```bash
   chmod 600 ~/.xbar_stock_config.json
   ```

The plugin runs with no API keys at all — it falls back to public Yahoo
Finance scraping. Adding free API keys for [Alpaca](https://alpaca.markets)
and [Finnhub](https://finnhub.io) gives you cleaner data and breaking-news
alerts.

## Configuration

The config file is JSON. Defaults are sensible — set only the fields you
want to override. Key sections:

### Watchlists
```json
"TICKER_GROUPS": [
  ["AAPL", "MSFT", "TSLA"],
  ["NVDA", "GOOGL", "AMZN"]
]
```
Groups rotate through the menu bar one at a time. Adjust the refresh interval
via the filename suffix (`stock.8s.py` = 8 seconds per group).

### Portfolio
```json
"PORTFOLIO": {
  "AAPL": {"shares": 100, "cost_basis": 150.0}
},
"ACCOUNT": {
  "margin_used": 0,
  "EQUITY_ALERT_HIGH": 100000,
  "EQUITY_ALERT_LOW": 30000
}
```
The dropdown shows per-stock P&L. Equity = market value − margin_used. When
equity crosses HIGH or LOW, the menu bar flashes and a macOS notification
fires.

### Alerts
```json
"THRESHOLDS": [5, 10, 15, 20, 25],
"STOCK_ALERT_COOLDOWN_MINUTES": 5,
"PRICE_ALERTS": {
  "AAPL": {"above": 250.0, "below": 100.0}
}
```
THRESHOLDS fires when a stock moves by N% (vs previous close). PRICE_ALERTS
fires on absolute crossings. Cooldown silences a symbol for N minutes after
any of its alerts fires.

### API Keys

| Field | Required? | Get one at |
|---|---|---|
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | Optional (recommended) | https://alpaca.markets |
| `FINNHUB_API_KEY` | Optional (for news) | https://finnhub.io |

Without keys, the plugin falls back to Yahoo Finance for quotes and skips
news entirely. With Alpaca free keys, regular-hours quotes use the IEX feed
(authenticated, no rate-limit games).

See `DEFAULT_CONFIG` in the source for the full schema and inline docs.

## Behavior

### Active hours

Plugin only fetches data between **4:01 AM and 7:59 PM Eastern, weekdays**.
Outside that window the menu bar shows 🌑 and no network requests are made.

### Caching

| What | Cached for | Where |
|---|---|---|
| Stock quotes | 5s (RTH) / 30s (pre/post) | `/tmp/xbar_stock_quote_cache.json` |
| 10Y treasury | 30s | (same file) |
| News headline | 20s | (same file) |
| OTA version check | 1h | `/tmp/xbar_stock_ota_cache.json` |

Cache invalidates automatically on phase change (REGULAR → POST), so price
baselines never use stale data.

### Alerts

Four classes, in increasing priority:

1. **STOCK** — percentage thresholds (5/10/15/20/25%)
2. **PRICE** — absolute price targets you configured
3. **NEWS** — Finnhub top headline changes
4. **EQUITY** — portfolio equity crosses thresholds

Higher priority preempts the menu bar's visual lock; lower priority alerts
still get logged for dedup but don't change the display.

Sound plays only during regular hours (9:30 AM – 4:00 PM ET). Notifications
fire in any active phase and persist in Notification Center after the
menu-bar freeze ends.

## State files

| File | Purpose | Survives reboot? |
|---|---|---|
| `~/.xbar_stock_config.json` | Your config (mode 600) | Yes |
| `~/Library/Application Support/xbar_stock/idx.txt` | Group rotation index | Yes |
| `~/Library/Application Support/xbar_stock/alerts_v4.json` | Today's triggered alerts | Yes (resets at midnight) |
| `/tmp/xbar_stock_quote_cache.json` | Recent quote cache | No |
| `/tmp/xbar_stock_ota_cache.json` | Version check cache | No |
| `/tmp/xbar_stock.log` | Rotating log (256 KB × 2) | No |

## Troubleshooting

**Menu bar stuck at an old timestamp.**
macOS App Nap may have suspended xbar. Disable it:
```bash
defaults write com.matryer.xbar NSAppSleepDisabled -bool YES
killall xbar && open -a xbar
```

**Treasury yield never updates.**
Check `grep "Treasury:" /tmp/xbar_stock.log | tail`. You'll see which source
won. If only `Yahoo-TNX` succeeds, you're getting RTH-frozen data after
hours — your network is blocking CNBC and Stooq.

**Config errors at startup.**
Menu bar shows `⚠️ Config error (N)`. Open the dropdown for a per-error
breakdown with the file path to fix.

**Pre-market prices look wrong on small caps.**
Alpaca free tier is IEX-only, which is sparse for thin tickers during
extended hours. The dispatcher routes PRE/POST to Yahoo for this reason —
verify in the dropdown: each ticker shows `via Yahoo @ HH:MM` or
`via Alpaca @ HH:MM`.

## Architecture

Single Python file, ~2000 lines, no external dependencies.

```
main()                           ← orchestrator (~90 lines)
  ├ validate_config()            ← schema check, friendly error if bad
  ├ MarketWindow                 ← time → phase mapping
  ├ decide_display_group()       ← which tickers this tick
  ├ partition_cache()            ← split into hits + misses
  ├ fetch_missing()              ← parallel HTTP, skips executor if no work
  │   ├ fetch_stock()            ← Alpaca/Yahoo dispatcher
  │   ├ fetch_finnhub_news()
  │   └ fetch_treasury_yield()   ← 5-source cascade
  ├ decide_alerts()              ← stock + news + equity, priority-ordered
  ├ react_to_alerts()            ← persist + sound + notification
  └ MenuOutput                   ← accumulator, flushed once at end
```

Run `python3 -m py_compile xbar_stock_ticker.py` to check syntax. Reference
tests are inline in the conversation history — see commit log for examples.

## Support the project

If this saved you a Bloomberg terminal subscription (or a browser tab full of
ETF tickers), the easiest way to say thanks is a coffee:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-%E2%98%95-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/nathanieljiang)

→ <https://buymeacoffee.com/nathanieljiang>

No obligation, no paywalled features — every release stays free and MIT
licensed. Sponsors just make it more likely I'll keep shipping fixes when
yet another upstream API breaks.

## License

MIT. See `LICENSE`.

## Acknowledgements

Initial concept inspired by xbar's example plugins. The 5-source treasury
cascade evolved through painful trial against an unstable CNBC API.
