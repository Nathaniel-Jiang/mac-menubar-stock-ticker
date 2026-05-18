#!/usr/bin/env python3

"""
macOS Menu Bar Stock Terminal (xbar plugin) V1.1
Features: Sparklines, Priority Sorting, P&L, Margin & Equity Alerts, CNBC Breaking News, Custom Icons
"""

import urllib.request
import urllib.error
import json
import sys
import os
import random
import time
from datetime import datetime
import concurrent.futures
import xml.etree.ElementTree as ET

# ==================== [ SYSTEM CONSTANTS & TIMEZONE ] ====================
CURRENT_VERSION = "1.1"
os.environ['TZ'] = 'America/New_York'
time.tzset()

FONT_SETTINGS = "font='Menlo Bold' size=14 dropdown=false"
STATE_FILE = '/tmp/xbar_stock_idx.txt'
ALERT_STATE_FILE = '/tmp/xbar_stock_alerts_v4.json'
CONFIG_FILE = os.path.expanduser('~/.xbar_stock_config.json')

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
]

CURRENCY_SYMBOLS = {
    'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 
    'CNY': '¥', 'BTC': '₿', 'ETH': 'Ξ'
}

# The default configuration generated upon the first run (Anonymized)
DEFAULT_CONFIG = {
    "THRESHOLDS": [5, 10, 15, 20, 25],
    "COLOR_UP": "#00FF00",
    "COLOR_DOWN": "#FF3333",
    "COLOR_NORMAL": "#FFFFFF",
    "ENABLE_SOUND_ALERT": True,
    "FREEZE_DURATION": 30,
    "SMART_SORT": False, 
    "ENABLE_NEWS_ALERTS": True, 
    "UPDATE_URL": "https://raw.githubusercontent.com/Nathaniel-Jiang/mac-menubar-stock-ticker/main/version.txt",
    "TICKER_GROUPS": [
        ["AAPL", "MSFT", "TSLA"],
        ["NVDA", "GOOGL", "AMZN"]
    ],
    "TICKER_ICONS": {
        "AAPL": "🍎",
        "TSLA": "⚡",
        "NVDA": "🧠"
    },
    "ACCOUNT": {
        "margin_used": 5000.00,
        "EQUITY_ALERT_HIGH": 50000.00,
        "EQUITY_ALERT_LOW": 10000.00
    },
    "PORTFOLIO": {
        "AAPL": {"shares": 100, "cost_basis": 150.00},
        "MSFT": {"shares": 50, "cost_basis": 350.00}
    }
}
# =========================================================================

def load_config():
    """Loads user configuration, auto-generates default if missing, and merges keys."""
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
        except Exception: pass
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            user_cfg = json.load(f)
            for key in DEFAULT_CONFIG:
                if key not in user_cfg:
                    user_cfg[key] = DEFAULT_CONFIG[key]
            return user_cfg
    except Exception:
        return DEFAULT_CONFIG

CONFIG = load_config()

def format_volume(v):
    """Formats large volume numbers into human-readable strings."""
    if v == 0: return "0"
    elif v >= 1_000_000_000: return f"{v/1_000_000_000:.2f}B"
    elif v >= 1_000_000: return f"{v/1_000_000:.2f}M"
    elif v >= 1_000: return f"{v/1_000:.1f}K"
    else: return str(v)

def generate_sparkline(close_prices):
    """Generates an ASCII sparkline chart from an array of intraday prices."""
    valid_data = [x for x in close_prices if x is not None]
    if not valid_data: return ""
    
    # Subsample to 8 data points to fit the menu bar perfectly
    step = max(1, len(valid_data) // 8)
    sampled = valid_data[::step][-8:]
    if not sampled: return ""
    
    min_val, max_val = min(sampled), max(sampled)
    if min_val == max_val: return "━━"
    
    chars = [' ', '▂', '▃', '▄', '▅', '▆', '▇', '█']
    spread = max_val - min_val
    return "".join(chars[int(((v - min_val) / spread) * 7)] for v in sampled)

def get_currency_symbol(currency_code):
    return CURRENCY_SYMBOLS.get(currency_code, f"{currency_code} ")

def check_for_updates():
    """Checks the remote GitHub repository for a newer version via OTA."""
    update_url = CONFIG.get("UPDATE_URL", "")
    if not update_url or "YOUR_GITHUB_NAME" in update_url: 
        return None
    try:
        req = urllib.request.Request(update_url, headers={'User-Agent': random.choice(USER_AGENTS)})
        with urllib.request.urlopen(req, timeout=1.0) as response:
            remote_ver = response.read().decode('utf-8').strip()
            if remote_ver and remote_ver > CURRENT_VERSION:
                return remote_ver
    except Exception: pass
    return None

def get_cnbc_breaking_news():
    """Fetches the latest Top News headline from CNBC RSS Feed."""
    try:
        url = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"
        req = urllib.request.Request(url, headers={'User-Agent': random.choice(USER_AGENTS)})
        with urllib.request.urlopen(req, timeout=1.5) as response:
            root = ET.fromstring(response.read())
            first_item = root.find('.//item')
            if first_item is not None:
                return first_item.find('title').text.strip()
    except Exception: pass
    return None

def get_stock_data(symbol, market_phase):
    """Fetches real-time price, volume, and intraday chart data from Yahoo Finance."""
    user_agent = random.choice(USER_AGENTS)
    try:
        # Fetch Real-Time & Intraday data for Sparkline
        api_rt = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        req_rt = urllib.request.Request(api_rt, headers={'User-Agent': user_agent})
        with urllib.request.urlopen(req_rt, timeout=1.5) as response_rt:
            data_rt = json.loads(response_rt.read().decode('utf-8'))
            meta = data_rt['chart']['result'][0]['meta']
            
            currency_code = meta.get('currency', 'USD')
            currency_sym = get_currency_symbol(currency_code)
            
            regular_price = meta.get('regularMarketPrice', 0)
            prev_close = meta.get('previousClose', regular_price) 
            current_vol = meta.get('regularMarketVolume', 0)
            
            display_price = regular_price
            comparison_base = prev_close
            phase_icon = ""

            # Adjust display price based on pre/post market sessions
            if market_phase == 'PRE' and meta.get('preMarketPrice'):
                display_price = meta.get('preMarketPrice')
                phase_icon = "🌅"
            elif market_phase == 'POST' and meta.get('postMarketPrice'):
                display_price = meta.get('postMarketPrice')
                comparison_base = regular_price 
                phase_icon = "🌙"

            close_prices = data_rt['chart']['result'][0]['indicators']['quote'][0].get('close', [])
            sparkline = generate_sparkline(close_prices)

        # Fetch 10-Day Average Volume
        api_hist = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=15d&interval=1d"
        req_hist = urllib.request.Request(api_hist, headers={'User-Agent': user_agent})
        with urllib.request.urlopen(req_hist, timeout=1.5) as response_hist:
            data_hist = json.loads(response_hist.read().decode('utf-8'))
            indicators = data_hist['chart']['result'][0]['indicators']['quote'][0]
            volumes = [v for v in indicators.get('volume', []) if v is not None]
            avg_v_10d = sum(volumes[-11:-1]) / 10 if len(volumes) >= 11 else current_vol
                
        c_pct = ((display_price - comparison_base) / comparison_base) * 100 if comparison_base != 0 else 0
        
        if c_pct > 0: c_fmt_str = f"▲{c_pct:.2f}%"
        elif c_pct < 0: c_fmt_str = f"▼{abs(c_pct):.2f}%"
        else: c_fmt_str = "0.00%"
        
        return {
            "symbol": symbol, "error": False, "p_str": f"{display_price:.2f}",
            "p_float": display_price, "prev_close": comparison_base,
            "c_fmt": c_fmt_str, "v_fmt": format_volume(current_vol),
            "avg_v_fmt": format_volume(avg_v_10d),
            "c_pct_raw": c_pct, "phase_icon": phase_icon,
            "currency": currency_sym, "sparkline": sparkline
        }
    except Exception: 
        return {"symbol": symbol, "error": True}

def get_and_update_index(max_groups):
    """Manages the rotation index for ticker groups."""
    try:
        with open(STATE_FILE, 'r') as f:
            idx = int(f.read().strip())
    except Exception: idx = 0 
    
    next_idx = (idx + 1) % max_groups
    try:
        with open(STATE_FILE, 'w') as f:
            f.write(str(next_idx))
    except Exception: pass
    return idx

def main():
    now = datetime.now()
    now_ts = time.time()
    today_str = now.strftime('%Y-%m-%d')
    
    is_weekend = now.weekday() >= 5
    market_phase = 'REGULAR'
    
    # Determine current market session (EST)
    if 4 <= now.hour < 9 or (now.hour == 9 and now.minute < 30): market_phase = 'PRE'
    elif 16 <= now.hour < 20: market_phase = 'POST'
    
    # EXACT TIMING: Only active between 9:29 AM and 4:01 PM EST
    current_mins = now.hour * 60 + now.minute
    is_working_hours = (9 * 60 + 29) <= current_mins <= (16 * 60 + 1)
    
    # Smart Sleep Mode: Halt API requests during weekends or outside working hours
    if is_weekend or not is_working_hours:
        print(f"🌑🌑🌑🌑🌑 | {FONT_SETTINGS} color={CONFIG['COLOR_NORMAL']}")
        print('---')
        print(f"Status: Market Closed (Deep Sleep) - Last: {now.strftime('%X')} EST")
        print(f"Edit Config File | href=file://{CONFIG_FILE}")
        sys.exit(0)
        
    # Load or initialize the alert state file
    try:
        with open(ALERT_STATE_FILE, 'r') as f:
            alert_state = json.load(f)
        if alert_state.get("date") != today_str:
            raise ValueError
    except Exception:
        alert_state = {
            "date": today_str, "triggered": {}, "pause_until": 0, 
            "pause_group_idx": 0, "pause_color": CONFIG['COLOR_NORMAL'],
            "alert_msg": "", "alert_type": "", "last_news_title": ""
        }

    is_paused = now_ts < alert_state.get("pause_until", 0)
    is_smart_sort = CONFIG.get("SMART_SORT", False)
    all_symbols_flat = [sym for group in CONFIG['TICKER_GROUPS'] for sym in group]
    
    # Determine which tickers to fetch based on sort mode and pause state
    if is_smart_sort:
        current_syms = list(set(all_symbols_flat))
        group_idx = 0
        current_color = alert_state.get("pause_color", CONFIG['COLOR_NORMAL']) if is_paused else CONFIG['COLOR_NORMAL']
    else:
        if is_paused:
            group_idx = alert_state.get("pause_group_idx", 0)
            current_color = alert_state.get("pause_color", CONFIG['COLOR_NORMAL'])
        else:
            group_idx = get_and_update_index(len(CONFIG['TICKER_GROUPS']))
            current_color = CONFIG['COLOR_NORMAL']
            
        if group_idx >= len(CONFIG['TICKER_GROUPS']): group_idx = 0
        current_syms = CONFIG['TICKER_GROUPS'][group_idx]
    
    # === Concurrent Data Fetching (Stocks + News) ===
    results = []
    latest_news = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(15, len(current_syms) + 1)) as executor:
        future_to_sym = {executor.submit(get_stock_data, sym, market_phase): sym for sym in current_syms}
        
        # Submit the News API request concurrently if enabled
        news_future = None
        if CONFIG.get("ENABLE_NEWS_ALERTS", True):
            news_future = executor.submit(get_cnbc_breaking_news)
            
        for future in concurrent.futures.as_completed(future_to_sym):
            results.append(future.result())
            
        if news_future:
            latest_news = news_future.result()
            
    # Sort results
    if is_smart_sort:
        results = [r for r in results if not r.get("error")]
        results.sort(key=lambda x: abs(x['c_pct_raw']), reverse=True)
        display_limit = len(CONFIG['TICKER_GROUPS'][0]) if CONFIG['TICKER_GROUPS'] else 2
        ordered_results = results[:display_limit]
    else:
        results_dict = {res['symbol']: res for res in results}
        ordered_results = [results_dict[sym] for sym in current_syms if sym in results_dict]
    
    state_changed = False
    freeze_duration = CONFIG.get("FREEZE_DURATION", 30)
    
    # === 1. News Breaking Detection ===
    if latest_news:
        last_seen_news = alert_state.get("last_news_title", "")
        if not last_seen_news:
            # First boot initialize silently
            alert_state["last_news_title"] = latest_news
            state_changed = True
        elif latest_news != last_seen_news:
            alert_state["last_news_title"] = latest_news
            current_alert_type = alert_state.get("alert_type", "")
            
            # Prevent News from overwriting a Critical Equity Alert visually
            if not current_alert_type.startswith("EQUITY"):
                alert_state["pause_until"] = now_ts + 30 # Hardcode 30s freeze for breaking news
                alert_state["pause_group_idx"] = group_idx
                alert_state["pause_color"] = "#FFDD00" # Warning Yellow
                alert_state["alert_msg"] = f"📰 BREAKING: {latest_news}"
                alert_state["alert_type"] = "NEWS"
                current_color = "#FFDD00"
                state_changed = True
                is_paused = True # Force pause locally
    
    # === 2. Individual Stock Alert Detection ===
    for data in ordered_results:
        if data.get("error"): continue
        sym = data['symbol']
        c_pct_raw = data['c_pct_raw']
        
        for threshold in CONFIG['THRESHOLDS']:
            if abs(c_pct_raw) >= threshold:
                direction = "UP" if c_pct_raw > 0 else "DOWN"
                alert_key = f"{sym}_{direction}_{threshold}"
                if alert_key not in alert_state["triggered"]:
                    alert_state["triggered"][alert_key] = True
                    
                    # Do not visually override Equity or News alerts with stock alerts
                    current_alert_type = alert_state.get("alert_type", "")
                    if not current_alert_type.startswith("EQUITY") and current_alert_type != "NEWS":
                        alert_state["pause_until"] = now_ts + freeze_duration  
                        alert_state["pause_group_idx"] = group_idx
                        alert_state["pause_color"] = CONFIG['COLOR_UP'] if direction == "UP" else CONFIG['COLOR_DOWN']
                        trend_icon = "📈" if direction == "UP" else "📉"
                        alert_state["alert_msg"] = f"{trend_icon} STOCK ALERT: {sym} {direction} {threshold}%"
                        alert_state["alert_type"] = "STOCK"
                        current_color = alert_state["pause_color"]
                    state_changed = True

    menu_bar_parts = []
    dropdown_info = []
    
    portfolio = CONFIG.get("PORTFOLIO", {})
    custom_icons = CONFIG.get("TICKER_ICONS", {}) 
    account_cfg = CONFIG.get("ACCOUNT", {})
    
    total_market_value = 0.0
    total_unrealized_pl = 0.0
    total_today_pl = 0.0
    has_active_portfolio = False

    for data in ordered_results:
        sym = data['symbol']
        if data.get("error"):
            menu_bar_parts.append(f"{sym} [N/A]")
            dropdown_info.append(f"{sym}: Network Error")
            continue
        
        c_sym = data['currency']
        phase = data['phase_icon']
        spark = data['sparkline']
        display_sym = custom_icons.get(sym, sym)
        
        part_str = f"{phase}{display_sym} {c_sym}{data['p_str']} {data['c_fmt']} {spark}"
        menu_bar_parts.append(part_str)
        
        dd_str = f"{display_sym} ({sym}) • Vol: {data['v_fmt']} vs 10D: {data['avg_v_fmt']}"
        
        if sym in portfolio and portfolio[sym].get("shares", 0) > 0:
            shares = portfolio[sym]["shares"]
            cost = portfolio[sym]["cost_basis"]
            
            # Calculate Total Market Value & P&L
            market_val = data['p_float'] * shares
            unrealized = market_val - (cost * shares)
            today_pl = (data['p_float'] - data['prev_close']) * shares
            
            total_market_value += market_val
            total_unrealized_pl += unrealized
            total_today_pl += today_pl
            has_active_portfolio = True
            
            sign = '+' if unrealized >= 0 else ''
            t_sign = '+' if today_pl >= 0 else ''
            
            dd_str += f" • 💰 P&L: {sign}{c_sym}{unrealized:,.2f} (Today: {t_sign}{c_sym}{today_pl:,.2f})"
        
        dd_str += f" | href=https://finance.yahoo.com/quote/{sym}"
        dropdown_info.append(dd_str)
        
    # === 3. Global Equity Alerts ===
    if has_active_portfolio:
        margin_used = account_cfg.get("margin_used", 0.0)
        current_equity = total_market_value - margin_used
        eq_high = account_cfg.get("EQUITY_ALERT_HIGH", 0.0)
        eq_low = account_cfg.get("EQUITY_ALERT_LOW", 0.0)
        
        # Breach of Upper Equity Threshold (Take Profit)
        if eq_high > 0 and current_equity >= eq_high:
            alert_key = f"EQUITY_HIGH_{int(eq_high)}"
            if alert_key not in alert_state["triggered"]:
                alert_state["triggered"][alert_key] = True
                alert_state["pause_until"] = now_ts + freeze_duration
                alert_state["pause_group_idx"] = group_idx
                alert_state["pause_color"] = CONFIG['COLOR_UP']
                alert_state["alert_msg"] = f"🎯 EQUITY TARGET REACHED: ${current_equity:,.0f}"
                alert_state["alert_type"] = "EQUITY_HIGH"
                current_color = CONFIG['COLOR_UP']
                state_changed = True
                
        # Breach of Lower Equity Threshold (Risk Control)
        if eq_low > 0 and current_equity <= eq_low:
            alert_key = f"EQUITY_LOW_{int(eq_low)}"
            if alert_key not in alert_state["triggered"]:
                alert_state["triggered"][alert_key] = True
                alert_state["pause_until"] = now_ts + freeze_duration
                alert_state["pause_group_idx"] = group_idx
                alert_state["pause_color"] = CONFIG['COLOR_DOWN']
                alert_state["alert_msg"] = f"🛑 RISK ALERT - LOW EQUITY: ${current_equity:,.0f}"
                alert_state["alert_type"] = "EQUITY_LOW"
                current_color = CONFIG['COLOR_DOWN']
                state_changed = True

    # Persist alert state and play sound if triggered
    if state_changed:
        try:
            with open(ALERT_STATE_FILE, 'w') as f:
                json.dump(alert_state, f)
            if CONFIG.get("ENABLE_SOUND_ALERT", False):
                os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception: pass

    # === Menu Bar Rendering Logic ===
    if is_paused and alert_state.get("alert_type") == "NEWS":
        # Override entire menu bar with the Breaking News headline
        menu_bar_string = alert_state["alert_msg"]
    else:
        # Standard rendering for Stock/Equity alerts
        menu_bar_string = "   ".join(menu_bar_parts)
        if is_paused and alert_state.get("alert_type", "").startswith("EQUITY"):
            prefix = "🎯 [HIGH EQUITY] " if alert_state["alert_type"] == "EQUITY_HIGH" else "🛑 [LOW EQUITY] "
            menu_bar_string = prefix + menu_bar_string

    print(f"{menu_bar_string} | {FONT_SETTINGS} color={current_color}")
    
    print('---')
    
    # === Render Global Portfolio Dashboard ===
    if has_active_portfolio:
        margin_used = account_cfg.get("margin_used", 0.0)
        current_equity = total_market_value - margin_used
        
        tot_sign = '+' if total_unrealized_pl >= 0 else ''
        tot_t_sign = '+' if total_today_pl >= 0 else ''
        
        print(f"🏦 PORTFOLIO TOTAL | color=#00BFFF size=14 font='Menlo Bold'")
        print(f"💵 Equity: ${current_equity:,.2f} (Margin: ${margin_used:,.2f}) | color=#FFA500 size=13")
        print(f"💰 Total P&L: {tot_sign}${total_unrealized_pl:,.2f} (Today: {tot_t_sign}${total_today_pl:,.2f}) | color=#FFFFFF size=13")
        print('---')
        
    for info in dropdown_info:
        print(info)
        
    print('---')
    
    # OTA Update Check
    new_version = check_for_updates()
    if new_version:
        print(f"🚀 V{new_version} Update Available! | color=#FFDD00 href={CONFIG.get('UPDATE_URL').replace('raw.githubusercontent.com', 'github.com').replace('/main/version.txt', '')}")
        print('---')

    # Display current terminal phase/status
    if is_paused or state_changed:
        msg = alert_state.get("alert_msg", "⚠️ ALERT TRIGGERED")
        time_left = max(0, int(alert_state.get("pause_until", 0) - now_ts))
        print(f"{msg} ({time_left}s left) | color=#FFDD00 font='Menlo Bold'")
    elif is_smart_sort:
        print(f"🔥 SMART SORT MODE ACTIVE - {now.strftime('%X')} EST | color=#FF8C00")
    else:
        print(f"Phase: {market_phase} - Group {group_idx + 1} - Last Update: {now.strftime('%X')} EST")
        
    print('---')
    print("⚙️ Edit Watchlist & Config | href=file://" + CONFIG_FILE)
    print("🔄 Refresh All | refresh=true")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("⚠️ Terminal Crash | font='Menlo Bold' size=14 color=#FF3333 dropdown=false")
        print('---')
        print(f"Fatal Error: {str(e)}")
        print("Please check your ~/.xbar_stock_config.json syntax.")
