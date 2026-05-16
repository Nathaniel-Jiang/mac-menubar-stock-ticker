#!/usr/bin/env python3

"""
macOS Menu Bar Stock Terminal (xbar plugin) V1.0
Features: Sparklines, Smart Priority Sorting, Global Currencies, OTA Updates, P&L
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

# ==================== [ SYSTEM CONSTANTS & TIMEZONE ] ====================
CURRENT_VERSION = "1.0"
os.environ['TZ'] = 'America/New_York'
time.tzset()

FONT_SETTINGS = "font='Menlo Bold' size=14 dropdown=false"
STATE_FILE = '/tmp/xbar_stock_idx.txt'
ALERT_STATE_FILE = '/tmp/xbar_stock_alerts_v4.json'
CONFIG_FILE = os.path.expanduser('~/.xbar_stock_config.json')

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15'
]

CURRENCY_SYMBOLS = {
    'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 
    'CNY': '¥', 'BTC': '₿', 'ETH': 'Ξ'
}

DEFAULT_CONFIG = {
    "THRESHOLDS": [5, 10, 15, 20, 25],
    "COLOR_UP": "#00FF00",
    "COLOR_DOWN": "#FF3333",
    "COLOR_NORMAL": "#FFFFFF",
    "ENABLE_SOUND_ALERT": True,
    "SMART_SORT": False, # If true, ignores groups and displays top movers
    "UPDATE_URL": "https://raw.githubusercontent.com/Nathaniel-Jiang/mac-menubar-stock-ticker/main/version.txt",
    "TICKER_GROUPS": [
        ["AAPL", "MSFT"],
        ["NVDA", "GOOGL"],
        ["AMZN", "META"]
    ],
    "PORTFOLIO": {
        "NVDA": {"shares": 50, "cost_basis": 120.00}
    }
}
# =========================================================================

def load_config():
    """Loads user config, auto-generates default, and merges missing keys."""
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
    if v == 0: return "0"
    elif v >= 1_000_000_000: return f"{v/1_000_000_000:.2f}B"
    elif v >= 1_000_000: return f"{v/1_000_000:.2f}M"
    elif v >= 1_000: return f"{v/1_000:.1f}K"
    else: return str(v)

def generate_sparkline(close_prices):
    """Generates an ASCII sparkline chart from an array of prices."""
    valid_data = [x for x in close_prices if x is not None]
    if not valid_data: return ""
    # Subsample to 8 data points to fit the menu bar beautifully
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
    """Checks the remote GitHub repository for a newer version."""
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

def get_stock_data(symbol, market_phase):
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

            if market_phase == 'PRE' and meta.get('preMarketPrice'):
                display_price = meta.get('preMarketPrice')
                phase_icon = "🌅"
            elif market_phase == 'POST' and meta.get('postMarketPrice'):
                display_price = meta.get('postMarketPrice')
                comparison_base = regular_price 
                phase_icon = "🌙"

            # Generate Sparkline from 1m close prices
            close_prices = data_rt['chart']['result'][0]['indicators']['quote'][0].get('close', [])
            sparkline = generate_sparkline(close_prices)

        # Fetch 10-Day Volume
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
    if 4 <= now.hour < 9 or (now.hour == 9 and now.minute < 30): market_phase = 'PRE'
    elif 16 <= now.hour < 20: market_phase = 'POST'
    
    is_deep_night = (now.hour >= 20) or (now.hour < 4)
    
    if is_weekend or is_deep_night:
        print(f"🌑🌑🌑🌑🌑 | {FONT_SETTINGS} color={CONFIG['COLOR_NORMAL']}")
        print('---')
        print(f"Status: Market Closed (Deep Sleep) - Last: {now.strftime('%X')} EST")
        print(f"Edit Config File | href=file://{CONFIG_FILE}")
        sys.exit(0)
        
    try:
        with open(ALERT_STATE_FILE, 'r') as f:
            alert_state = json.load(f)
        if alert_state.get("date") != today_str:
            alert_state = {"date": today_str, "triggered": {}, "pause_until": 0, "pause_group_idx": 0, "pause_color": CONFIG['COLOR_NORMAL']}
    except Exception:
        alert_state = {"date": today_str, "triggered": {}, "pause_until": 0, "pause_group_idx": 0, "pause_color": CONFIG['COLOR_NORMAL']}

    is_paused = now_ts < alert_state.get("pause_until", 0)

    # Fetching Logic: Smart Sort vs Standard Group Rotation
    is_smart_sort = CONFIG.get("SMART_SORT", False)
    all_symbols_flat = [sym for group in CONFIG['TICKER_GROUPS'] for sym in group]
    
    if is_smart_sort:
        current_syms = list(set(all_symbols_flat)) # Fetch all unique tickers
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
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(15, len(current_syms))) as executor:
        future_to_sym = {executor.submit(get_stock_data, sym, market_phase): sym for sym in current_syms}
        for future in concurrent.futures.as_completed(future_to_sym):
            results.append(future.result())
            
    # Process Smart Sort
    if is_smart_sort:
        # Sort all fetched results by absolute percentage change (hottest movers first)
        results = [r for r in results if not r.get("error")]
        results.sort(key=lambda x: abs(x['c_pct_raw']), reverse=True)
        display_limit = len(CONFIG['TICKER_GROUPS'][0]) if CONFIG['TICKER_GROUPS'] else 2
        ordered_results = results[:display_limit]
    else:
        results_dict = {res['symbol']: res for res in results}
        ordered_results = [results_dict[sym] for sym in current_syms if sym in results_dict]
    
    state_changed = False
    
    for data in ordered_results:
        if data.get("error"): continue
        sym = data['symbol']
        c_pct_raw = data['c_pct_raw']
        
        for threshold in CONFIG['THRESHOLDS']:
            if c_pct_raw >= threshold:
                alert_key = f"{sym}_UP_{threshold}"
                if alert_key not in alert_state["triggered"]:
                    alert_state["triggered"][alert_key] = True
                    alert_state["pause_until"] = now_ts + 30  
                    alert_state["pause_group_idx"] = group_idx
                    alert_state["pause_color"] = CONFIG['COLOR_UP']
                    current_color = CONFIG['COLOR_UP']
                    state_changed = True
            
            elif c_pct_raw <= -threshold:
                alert_key = f"{sym}_DOWN_{threshold}"
                if alert_key not in alert_state["triggered"]:
                    alert_state["triggered"][alert_key] = True
                    alert_state["pause_until"] = now_ts + 30  
                    alert_state["pause_group_idx"] = group_idx
                    alert_state["pause_color"] = CONFIG['COLOR_DOWN']
                    current_color = CONFIG['COLOR_DOWN']
                    state_changed = True

    if state_changed:
        try:
            with open(ALERT_STATE_FILE, 'w') as f:
                json.dump(alert_state, f)
            if CONFIG.get("ENABLE_SOUND_ALERT", False):
                os.system("afplay /System/Library/Sounds/Glass.aiff &")
        except Exception: pass

    menu_bar_parts = []
    dropdown_info = []
    portfolio = CONFIG.get("PORTFOLIO", {})

    for data in ordered_results:
        sym = data['symbol']
        if data.get("error"):
            menu_bar_parts.append(f"{sym} [N/A]")
            dropdown_info.append(f"{sym}: Network Error")
            continue
        
        c_sym = data['currency']
        phase = data['phase_icon']
        spark = data['sparkline']
        
        # New Output Format: SYMBOL $PRICE %CHANGE SPARKLINE
        part_str = f"{phase}{sym} {c_sym}{data['p_str']} {data['c_fmt']} {spark}"
        menu_bar_parts.append(part_str)
        
        dd_str = f"{sym} | Vol: {data['v_fmt']} vs 10D: {data['avg_v_fmt']}"
        
        if sym in portfolio and portfolio[sym].get("shares", 0) > 0:
            shares = portfolio[sym]["shares"]
            cost = portfolio[sym]["cost_basis"]
            unrealized = (data['p_float'] - cost) * shares
            today_pl = (data['p_float'] - data['prev_close']) * shares
            sign = '+' if unrealized >= 0 else ''
            t_sign = '+' if today_pl >= 0 else ''
            dd_str += f" | 💰 P&L: {sign}{c_sym}{unrealized:,.2f} (Today: {t_sign}{c_sym}{today_pl:,.2f})"
        
        dd_str += f" | href=https://finance.yahoo.com/quote/{sym}"
        dropdown_info.append(dd_str)
    
    menu_bar_string = "   ".join(menu_bar_parts)
    print(f"{menu_bar_string} | {FONT_SETTINGS} color={current_color}")
    
    print('---')
    
    # Check for OTA Updates
    new_version = check_for_updates()
    if new_version:
        print(f"🚀 V{new_version} Update Available! | color=#FFDD00 href={CONFIG.get('UPDATE_URL').replace('raw.githubusercontent.com', 'github.com').replace('/main/version.txt', '')}")
        print('---')

    if is_paused or state_changed:
        print(f"⚠️ ALERT ACTIVE (30s Freeze) - {now.strftime('%X')} EST | color=#FFDD00")
    elif is_smart_sort:
        print(f"🔥 SMART SORT MODE ACTIVE - {now.strftime('%X')} EST | color=#FF8C00")
    else:
        print(f"Phase: {market_phase} - Group {group_idx + 1} - Last Update: {now.strftime('%X')} EST")
        
    for info in dropdown_info:
        print(info)
        
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