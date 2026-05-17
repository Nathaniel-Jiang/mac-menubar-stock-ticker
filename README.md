# 📈 Mac Menu Bar Stock Terminal (PRO)

A highly customizable, blazing-fast stock ticker for your macOS menu bar. Powered by xbar, featuring price breakout alerts, sparkline charts, real-time margin/equity portfolio tracking, and absolute zero dependencies.

---

## ✨ Features

- **Zero Dependencies (Plug & Play):** Pure Python. No `pip install` or third-party libraries needed.
- **Mini Sparklines:** See intraday trends directly in your menu bar (e.g., `▂▃▆█`).
- **CNBC Breaking News [NEW in v1.1]:** Concurrently fetches CNBC Top News via RSS. Triggers a 30-second yellow takeover banner in your menu bar when market-moving news drops.
- **Global Equity & Margin Alerts [NEW in v1.1]:** Actively calculates your Net Equity (Market Value minus Margin). Emits distinct High/Low equity alerts so you know exactly when to take profits or cut losses.
- **Custom Ticker Icons [NEW in v1.1]:** Hide raw ticker symbols by mapping them to visually intuitive emojis (e.g., replace `"AAPL"` with 🍎).
- **Smart Priority Sorting:** Automatically pins today's hottest movers to the front.
- **Breakout Alerts & Freeze:** 15–30 second UI freeze, color shifts (Green/Red), and crisp sound alerts when a stock hits your predefined thresholds.
- **Portfolio Tracking:** See your real-time unrealized floating profit/loss directly in the dropdown menu.
- **Extended Hours:** Seamlessly switches between Pre-market (🌅) and Post-market (🌙) pricing.
- **💤 Smart Sleep Mode (Eco-Friendly):** Automatically enters “Deep Sleep” mode during weekends and deep night hours to reduce battery and CPU usage.
- **OTA Updates:** Silently checks for updates and alerts you in the menu dropdown.

---


## 🚀 Quick Install (1-Click)

**Prerequisite:** Ensure you have [xbar](https://xbarapp.com/) installed and running on your Mac.

Open the **Terminal** app on your Mac, copy & paste this command, and press Enter:


mkdir -p ~/Library/Application\ Support/xbar/plugins && curl -L "https://raw.githubusercontent.com/Nathaniel-Jiang/mac-menubar-stock-ticker/main/001-yahoo_stock_ticker.5s.py" -o ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.5s.py && chmod +x ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.5s.py && open -a xbar



*(This command automatically downloads the script from this repo to your xbar plugins folder, makes it executable, and wakes up xbar.)*




# 🛠️ Complete Configuration Guide (How to Customize)

You don't need to touch any Python code. Upon the first run, the script auto-generates a config file.

## 📂 How to Find the Config File

### Method 1 (Easy)
Click:

```text
⚙️ Edit Watchlist & Config
```

inside the xbar dropdown menu.

### Method 2 (Manual)

Navigate to:

```bash
~/.xbar_stock_config.json
```

---

## 1. Watchlist (`TICKER_GROUPS`) & Custom Icons (`TICKER_ICONS`)

Due to limited menu bar space, symbols are rotated in groups. Each bracket `[...]` represents one group.

### Scenario A: Add a New Ticker to an Existing Group

**Rule:** Always wrap tickers in quotes and separate them with commas.

```json
// BEFORE:
["AAPL", "MSFT"]

// AFTER:
["AAPL", "MSFT", "TSLA"]
```

### Scenario B: Add a Completely New Rotation Group

**Rule:** Add a comma after the previous closing bracket.

```json
// BEFORE:
"TICKER_GROUPS": [
    ["AAPL", "MSFT"],
    ["NVDA", "GOOGL"]
]

// AFTER:
"TICKER_GROUPS": [
    ["AAPL", "MSFT"],
    ["NVDA", "GOOGL"],
    ["BTC-USD", "ETH-USD"]
]
```

### Scenario C: Map a Custom Icon

```json
"TICKER_ICONS": {
    "AAPL": "🍎",
    "TSLA": "⚡",
    "NVDA": "🧠"
}
```

Any ticker assigned an emoji in `TICKER_ICONS` will display that emoji instead of the raw ticker symbol.

---

## 2. Smart Priority Sorting (`SMART_SORT`)

### What It Does
When enabled, the script bypasses fixed group rotations and scans all tickers simultaneously, pinning the strongest movers with the highest percentage changes.

### How to Enable

```json
"SMART_SORT": true
```

---

## 3. Portfolio, Margin & Equity Tracking (`PORTFOLIO` & `ACCOUNT`)

```json
"ACCOUNT": {
    "margin_used": 5000.00,
    "EQUITY_ALERT_HIGH": 50000.00,
    "EQUITY_ALERT_LOW": 10000.00
},
"PORTFOLIO": {
    "AAPL": {"shares": 100, "cost_basis": 150.00},
    "MSFT": {"shares": 50, "cost_basis": 350.00}
}
```

### Explanation

- **`PORTFOLIO`**
  - `shares` = number of shares owned
  - `cost_basis` = average purchase price
  - Separate multiple stocks using commas

- **`margin_used`**
  - Subtracted from total market value to calculate real-time Net Equity

- **`EQUITY_ALERT_HIGH` / `LOW`**
  - Triggers critical risk/take-profit alerts when equity thresholds are reached

---

## 4. Breakout & News Alerts

### `THRESHOLDS`

Triggers instant UI freeze and color alerts when daily percentage changes cross predefined levels.

Example:

```json
"THRESHOLDS": [2, 5, 10]
```

### `ENABLE_NEWS_ALERTS`

```json
"ENABLE_NEWS_ALERTS": true
```

When enabled, the script polls CNBC RSS headlines and triggers a temporary yellow takeover banner for breaking market news.

### `ENABLE_SOUND_ALERT`

```json
"ENABLE_SOUND_ALERT": false
```

Set to `false` to disable sounds.

---

## 5. Color Palette (`COLOR_UP` & `COLOR_DOWN`)

Customize alert overlay colors using hexadecimal color codes.

Example:

```json
"COLOR_UP": "#00FF00",
"COLOR_DOWN": "#FF0000"
```

---

## 6. Alert Freeze Duration (`FREEZE_DURATION`)

Controls how long the menu bar remains frozen on an alert.

```json
"FREEZE_DURATION": 30
```

Value is measured in seconds.

---

## 7. ⏱️ Data Fetch & Rotation Speed (xbar Mechanism)

xbar controls refresh speed entirely through the filename.

Example:

```text
001-yahoo_stock_ticker.5s.py
```

means the plugin refreshes every 5 seconds.

## How to Change the Refresh Speed

1. Click the stock ticker in the Mac menu bar
2. Navigate to:

```text
xbar → Open Plugins Folder
```

3. Rename the plugin file

Examples:

```text
...10s.py   → refresh every 10 seconds
...1m.py    → refresh every 1 minute
```

4. Return to the menu bar and click:

```text
xbar → Refresh All
```

---

# ⚠️ Troubleshooting & Common Pitfalls

## Common JSON Formatting Mistakes

1. **Missing Quotation Marks**
   - Every ticker symbol and configuration key must use double quotes

2. **Missing or Extra Commas**
   - Separate list items with commas, except the final item

3. **Broken Structure**
   - Never delete closing brackets (`}` or `]`)

---

# 🔄 Reset / Delete a Corrupted Config File

Since the config file begins with a dot (`.`), it is hidden in Finder by default.

## Option A — Fastest (Terminal)

```bash
rm ~/.xbar_stock_config.json
```

## Option B — Finder UI

1. Open Finder
2. Press:

```text
Command + Shift + H
```

3. Press:

```text
Command + Shift + .
```

to show hidden files

4. Delete:

```text
.xbar_stock_config.json
```

5. Press:

```text
Command + Shift + .
```

again to hide system files

Once deleted, the plugin automatically generates a fresh default configuration file during the next refresh cycle.

---

# 💬 Feedback & Support

Love this terminal? Have an idea? Found a bug?

## 🐛 Found a Bug?

Open an issue here:

https://github.com/Nathaniel-Jiang/mac-menubar-stock-ticker/issues

Please include:

1. Your macOS version
2. Your config file (remove personal portfolio numbers first)
3. Screenshots of any errors

---

## 💡 Feature Requests

Suggestions are always welcome — whether it's a new metric, chart style, or data source.

---

## ⭐️ Support the Project

If this tool helped you catch a breakout, save battery life, or simply made your menu bar look cooler, consider giving the repository a Star ⭐️.

---

# 🤝 Contributing

Contributions are greatly appreciated.

## Workflow

1. Fork the project
2. Create a feature branch

```bash
git checkout -b feature/AmazingFeature
```

3. Commit changes

```bash
git commit -m "Add AmazingFeature"
```

4. Push the branch

```bash
git push origin feature/AmazingFeature
```

5. Open a Pull Request against the `main` branch

---

# ☕ Support This Project

This project is completely open-source and free to use.

If it helped you catch a breakout, save battery life, or improve your workflow, consider supporting the project. Every bit of support helps keep updates and new features coming.


[!["Buy Me A Coffee"](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/nathanieljiang)
