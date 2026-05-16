# 📈 Mac Menu Bar Stock Terminal (PRO)

A highly customizable, blazing-fast stock ticker for your macOS menu bar. Powered by xbar, featuring price breakout alerts, sparkline charts, portfolio tracking, and absolute zero dependencies.

## ✨ Features

* **Zero Dependencies (Plug & Play):** Pure Python. No `pip install` or third-party libraries needed.
* **Mini Sparklines:** See intraday trends directly in your menu bar (e.g., `▂▃▆█`).
* **Smart Priority Sorting:** Automatically pins today's hottest movers to the front.
* **Breakout Alerts & Freeze:** 30-second UI freeze, color shifts (Green/Red), and crisp sound alerts when a stock hits your predefined thresholds.
* **Portfolio Tracking:** See your real-time unrealized floating profit/loss directly in the dropdown menu.
* **Extended Hours:** Seamlessly switches between Pre-market (🌅) and Post-market (🌙) pricing.
* **OTA Updates:** Silently checks for updates and alerts you in the menu dropdown.


## 🚀 Quick Install (1-Click)

**Prerequisite:** Ensure you have [xbar](https://xbarapp.com/) installed and running on your Mac.

Open the **Terminal** app on your Mac, copy & paste this command, and press Enter:

mkdir -p ~/Library/Application\ Support/xbar/plugins && curl -L "https://raw.githubusercontent.com/Nathaniel-Jiang/mac-menubar-stock-ticker/main/001-yahoo_stock_ticker.4s.py" -o ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.4s.py && chmod +x ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.4s.py && open -a xbar

*(This command automatically downloads the script from this repo to your xbar plugins folder, makes it executable, and wakes up xbar.)*


## 🛠️ Complete Configuration Guide (How to Customize)

You don't need to touch any Python code! Upon the first run, the script auto-generates a config file. Simply click **`⚙️ Edit Watchlist & Config`** in the dropdown menu to open `~/.xbar_stock_config.json`.


### 1. Watchlist (`TICKER_GROUPS`)

* **What it is:** Due to limited menu bar space, symbols are rotated in groups. Each array `[...]` represents a single display cycle.
* **How to change:** Replace the default symbols with your own choices. It supports global stocks, indices, and crypto (e.g., `BTC-USD`).
* **Example:**
```json
"TICKER_GROUPS": [
    ["NVDA", "PLTR", "AAPL"],
    ["LUNR", "RKLB", "ASTS"]
]

```



### 2. Smart Priority Sorting (`SMART_SORT`)

* **What it is:** When enabled, the script bypasses fixed group rotations and scans all your tickers simultaneously, instantly pinning the top movers with the highest absolute percentage change to your menu bar.
* **How to change:** Toggle from `false` to `true`.
```json
"SMART_SORT": true

```



### 3. Portfolio Tracking (`PORTFOLIO`)

* **What it is:** Moves beyond raw percentages to show exactly how much your holdings are gaining or losing based on your positions.
* **How to change:** Input your specific positions. `shares` denotes your total held stock volume, and `cost_basis` represents your average purchase price.
* **Example:**
```json
"PORTFOLIO": {
    "LUNR": {"shares": 500, "cost_basis": 4.50},
    "NVDA": {"shares": 50, "cost_basis": 110.00}
}

```


*(Once configured, your dropdown will dynamically render live performance stats like `💰 P&L: +$1,250.00`.)*

### 4. Breakout Alerts (`THRESHOLDS` & `ENABLE_SOUND_ALERT`)

* **What it is:** Triggers an instant 30-second UI freeze and structural color shifts if a stock crosses these daily percentage markers.
* **How to change:**
* **Threshold Levels:** Adjust the array values (e.g., `[2, 5, 10]`) depending on your volatility preference or option strategies.
* **Audio Feedback:** Turn off the audio prompt by switching `"ENABLE_SOUND_ALERT": true` to `false`.



### 5. Color Palette (`COLOR_UP` & `COLOR_DOWN`)

* **What it is:** The hex code color overlay applied during alert triggers.
* **How to change:** Swap the hexadecimal values if your region uses alternative directional market colors (e.g., switching red and green).


## ⚠️ Troubleshooting & Common Pitfalls

To keep the underlying engine running smoothly, avoid these frequent formatting mistakes in your JSON file:

1. **Missing Quotation Marks:** Every ticker symbol and configuration key must remain enclosed in **double quotes** (`"AAPL"`), not single quotes or raw text.
2. **Trailing/Missing Commas:** Ensure every item or block within a list is separated by a single comma `,`, except for the very last element in that section.
3. **Structural Preservation:** Never delete the closing structural brackets (`}` or `]`).

*If your configuration file becomes corrupted and causes an interface crash, simply delete `~/.xbar_stock_config.json`. The plugin will automatically regenerate a pristine default copy on its next refresh cycle.*

