# 📈 Mac Menu Bar Stock Terminal (PRO)

A highly customizable, blazing-fast stock ticker for your macOS menu bar. Powered by xbar, featuring price breakout alerts, sparkline charts, portfolio tracking, and absolute zero dependencies.


## ✨ Features
* **Zero Dependencies (Plug & Play):** Pure Python. No `pip install` or third-party libraries needed.
* **Mini Sparklines:** See intraday trends directly in your menu bar (e.g., `▂▃▆█`).
* **Smart Priority Sorting:** Automatically pins today's hottest movers to the front.
* **Breakout Alerts & Freeze:** 30-second UI freeze, color shifts (Green/Red), and crisp sound alerts when a stock hits your predefined thresholds.
* **Portfolio Tracking:** See your real-time unrealized floating profit/loss directly in the dropdown menu.
* **Extended Hours:** Seamlessly switches between Pre-market (🌅) and Post-market (🌙) pricing.
* **💤 Smart Sleep Mode (Eco-Friendly):** To save your Mac's battery and CPU, the terminal automatically enters a "Deep Sleep" mode and pauses background network requests during weekends and deep night hours when markets are closed.
* **OTA Updates:** Silently checks for updates and alerts you in the menu dropdown.


## 🚀 Quick Install (1-Click)

**Prerequisite:** Ensure you have [xbar](https://xbarapp.com/) installed and running on your Mac.

Open the **Terminal** app on your Mac, copy & paste this command, and press Enter:


mkdir -p ~/Library/Application\ Support/xbar/plugins && curl -L "https://raw.githubusercontent.com/Nathaniel-Jiang/mac-menubar-stock-ticker/main/001-yahoo_stock_ticker.4s.py" -o ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.4s.py && chmod +x ~/Library/Application\ Support/xbar/plugins/001-yahoo_stock_ticker.4s.py && open -a xbar



*(This command automatically downloads the script from this repo to your xbar plugins folder, makes it executable, and wakes up xbar.)*


## 🛠️ Complete Configuration Guide (How to Customize)

You don't need to touch any Python code! Upon the first run, the script auto-generates a config file. 

**📂 How to find the config file:**
* **Method 1 (Easy):** Click **`⚙️ Edit Watchlist & Config`** in the xbar dropdown menu.
* **Method 2 (Manual):** Navigate to your Mac's home directory and open the hidden file: `~/.xbar_stock_config.json`.

### 1. Watchlist (`TICKER_GROUPS`) - Absolute Beginner's Guide
Due to limited menu bar space, symbols are rotated in groups. Each bracket `[...]` is one group. The menu bar will show Group 1, then Group 2, etc., on each refresh.

**Scenario A: How to add a new ticker to an existing group**
*Rule: Always wrap the ticker in `" "` and separate them with a comma `,`.*
```json
// BEFORE:
["AAPL", "MSFT"]

// AFTER (adding TSLA):
["AAPL", "MSFT", "TSLA"] 
```

**Scenario B: How to add a completely new rotation group**
*Rule: Make sure to add a comma `,` after the previous group's closing bracket `]`!*
```json
// BEFORE:
"TICKER_GROUPS": [
    ["AAPL", "MSFT"],
    ["NVDA", "GOOGL"]
]

// AFTER (Adding a 3rd group for Crypto):
"TICKER_GROUPS": [
    ["AAPL", "MSFT"],
    ["NVDA", "GOOGL"],
    ["BTC-USD", "ETH-USD"]
]
```

### 2. Smart Priority Sorting (`SMART_SORT`)
* **What it is:** When enabled, the script bypasses fixed group rotations and scans all your tickers simultaneously, instantly pinning the top movers with the highest absolute percentage change to your menu bar.
* **How to change:** Toggle from `false` to `true`.



### 3. Portfolio Tracking (`PORTFOLIO`) - Absolute Beginner's Guide
* **What it is:** Moves beyond raw percentages to show exactly how much your positions are gaining or losing in real-time.
* **How to add a new stock to track:**
  **Rule: Every stock entry requires its ticker in double quotes, followed by `shares` (amount of stock) and `cost_basis` (your average purchase price). Crucially, you MUST add a comma `,` to separate multiple stocks!*

```json
// BEFORE (Default with only one stock):
"PORTFOLIO": {
    "NVDA": {"shares": 50, "cost_basis": 120.00}
}

// AFTER (Adding a new stock, e.g., LUNR - Notice the comma after NVDA's block!):
"PORTFOLIO": {
    "NVDA": {"shares": 50, "cost_basis": 120.00},
    "LUNR": {"shares": 200, "cost_basis": 4.50}
}
```
*(Once saved, your dropdown will dynamically display live metrics like `💰 P&L: +$1,250.00` for each held position.)*


### 4. Breakout Alerts (`THRESHOLDS` & `ENABLE_SOUND_ALERT`)
* **What it is:** Triggers an instant UI freeze and structural color shifts if a stock crosses these daily percentage markers.
* **How to change:** Adjust the array values (e.g., `[2, 5, 10]`). Turn off audio by switching `"ENABLE_SOUND_ALERT": true` to `false`.


### 5. Color Palette (`COLOR_UP` & `COLOR_DOWN`)
* **What it is:** The hex code color overlay applied during alert triggers. Swap the hexadecimal values if you prefer Red for up and Green for down.


### 6. Alert Freeze Duration (`FREEZE_DURATION`)
* **What it is:** When an alert triggers, the UI freezes on the highlighted stock so you don't miss it. By default, this lasts for 30 seconds.
* **How to change:** Add or modify the `"FREEZE_DURATION": 30` key in your JSON file to set your preferred freeze time in seconds.


### 7. ⏱️ Data Fetch & Rotation Speed (xbar mechanism)
* **What it is:** The frequency at which the terminal fetches new market data and rotates to the next group of tickers.
* **How to change:** **This is NOT in the JSON file!** xbar controls the refresh rate entirely via the plugin's **filename** (e.g., `.4s.py` means a 4-second refresh).
* **The Easiest Way to Change It (No typing required):**
  1. Click your stock ticker in the Mac menu bar to open the dropdown menu.
  2. Navigate to **`xbar`** -> click **`Open Plugins Folder`**. This will instantly open the exact Finder window where your file lives.
  3. Right-click the file `001-yahoo_stock_ticker.4s.py` and select **Rename**.
  4. Change the `.4s` part to your desired interval. For example:
     * Rename to `...10s.py` to refresh/rotate every 10 seconds.
     * Rename to `...1m.py` to refresh/rotate every 1 minute.
  5. Go back to the menu bar, click **`xbar`** -> **`Refresh all`** to apply!


## ⚠️ Troubleshooting & Common Pitfalls
To keep the underlying engine running smoothly, avoid these frequent formatting mistakes in your JSON file:
1. **Missing Quotation Marks:** Every ticker symbol and configuration key must remain enclosed in **double quotes** (`"AAPL"`).
2. **Trailing/Missing Commas:** Ensure every item or block within a list is separated by a single comma `,`, except for the very last element in that section.
3. **Structural Preservation:** Never delete the closing structural brackets (`}` or `]`).


### 🔄 How to Reset / Delete a Corrupted Config File
Since the configuration file is a hidden file starting with a dot (`.`), it is invisible in Finder by default. If your file becomes corrupted and causes an interface crash, use one of the following methods to safely delete and reset it:

* **Option A (Fastest via Terminal):** Open your **Terminal** app, paste the following command, and press Enter to instantly delete it:


  rm ~/.xbar_stock_config.json


* **Option B (Via Finder User Interface):** 1. Open **Finder** and press `Command + Shift + H` to jump straight to your Home directory.
  2. Press **`Command + Shift + .` (Period key)** on your keyboard to instantly toggle hidden files visible.
  3. Find the faded file named **`.xbar_stock_config.json`** and drag it to the Trash.
  4. Press `Command + Shift + .` again to hide system files when done.

*Once deleted, the plugin will automatically generate a brand-new, pristine default configuration file on its very next refresh cycle.*


## 💬 Feedback & Support

Love this terminal? Have a brilliant idea? Or did something break? I'd love to hear from you!

* **🐛 Found a Bug?**
  Please open a ticket on the [GitHub Issues page](https://github.com/Nathaniel-Jiang/mac-menubar-stock-ticker/issues). To help me fix it blazing fast, please include:
  1. Your macOS version.
  2. A copy of your `~/.xbar_stock_config.json` *(Note: Please delete your actual portfolio numbers before sharing!)*.
  3. A screenshot of the error, if applicable.

* **💡 Have a Feature Request?**
  I am continuously looking to improve this tool! Feel free to open an issue and share your ideas. Whether it's a new metric, a different chart style, or a new data source—let's discuss it!

* **⭐️ Support the Project**
  If this tool helped you catch a breakout, saved your battery, or just looks incredibly cool on your Mac menu bar, please consider giving it a **Star ⭐️** at the top right of this repository. It helps more traders find this tool!


## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you want to modify the code, add new features, or fix bugs to improve the project for everyone:
1. **Fork** the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a **Pull Request** (PR) against our `main` branch.

I will personally review every single PR and merge the ones that bring incredible value to the community!


## ☕ Support This Project (Buy Me a Coffee)

This project is completely open-source and free to use. I build and maintain it in my free time to help fellow traders and developers stay on top of the market. 

If this tool has saved your battery, caught a major breakout, or just looks incredibly cool on your Mac menu bar, consider supporting my work! Your support keeps the updates coming and the features flowing.

[!["Buy Me A Coffee"](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/nathanieljiang)
