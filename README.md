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



### 6. Data Fetch & Rotation Speed (xbar mechanism)
* **What it is: The frequency at which the terminal fetches new data and rotates to the next group of tickers.

* **How to change: This is NOT in the JSON file! xbar controls the refresh rate via the plugin's filename. Currently, your file is named 001-yahoo_stock_ticker.4s.py, which means it refreshes every 4 seconds.

* **To modify: Open your xbar plugins folder (~/Library/Application Support/xbar/plugins/). Rename the file extension. For example:

* **Rename to ...10s.py to refresh/rotate every 10 seconds.

* **Rename to ...1m.py to refresh/rotate every 1 minute.

* **Note: Click Refresh all in xbar after renaming.



### 7. Alert Freeze Duration (`FREEZE_DURATION`)
* **What it is:** When an alert triggers, the UI freezes on the highlighted stock so you don't miss it. By default, this lasts for 30 seconds.
* **How to change:** Add or modify the `"FREEZE_DURATION": 30` key in your JSON file to set your preferred freeze time in seconds.



## ⚠️ Troubleshooting & Common Pitfalls

To keep the underlying engine running smoothly, avoid these frequent formatting mistakes in your JSON file:

1. **Missing Quotation Marks:** Every ticker symbol and configuration key must remain enclosed in **double quotes** (`"AAPL"`), not single quotes or raw text.
2. **Trailing/Missing Commas:** Ensure every item or block within a list is separated by a single comma `,`, except for the very last element in that section.
3. **Structural Preservation:** Never delete the closing structural brackets (`}` or `]`).

*If your configuration file becomes corrupted and causes an interface crash, simply delete `~/.xbar_stock_config.json`. The plugin will automatically regenerate a pristine default copy on its next refresh cycle.*



🔄 How to Reset / Delete a Corrupted Config File
Since the configuration file is a hidden file starting with a dot (.), it is invisible in Finder by default. If your file becomes corrupted and causes an interface crash, use one of the following methods to safely delete and reset it:

Option A (Fastest via Terminal): Open your Terminal app, paste the following command, and press Enter to instantly delete it:

rm ~/.xbar_stock_config.json



Option B (Via Finder User Interface): 

1. Open Finder and press Command + Shift + H to jump straight to your Home directory.
2. Press Command + Shift + . (Period key) on your keyboard to instantly toggle hidden files visible.
3. Find the faded file named .xbar_stock_config.json and drag it to the Trash.
4. Press Command + Shift + . again to hide system files when done.

Once deleted, the plugin will automatically generate a brand-new, pristine default configuration file on its very next refresh cycle.
