import time
import api
import config
from .helpers import get_trend_indicator, format_time

def run_region_trading_scan(scan_config, all_type_ids, progress_callback):
    """Kjører 'flipping'-skann innad på én stasjon."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    scan_type = scan_config['scan_type']
    active_flag = scan_config['active_flag']
    base_progress = 0.1
    
    station_info = config.STATIONS_INFO[scan_config['station']]
    item_chunks = [all_type_ids[i:i + 200] for i in range(0, len(all_type_ids), 200)]
    
    progress_callback({'scan_type': scan_type, 'progress': base_progress, 'status': f"Steg 1: Henter priser for {scan_config['station']}..."})
    prices_map = {}
    for i, chunk in enumerate(item_chunks):
        if not active_flag.is_set(): return
        progress = base_progress + (i / len(item_chunks) * 0.4)
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Henter pris-gruppe {i+1}/{len(item_chunks)}..."})
        data = api.fetch_fuzzwork_market_data(station_info['id'], chunk)
        for typeid_str, item_data in (data or {}).items():
            prices_map[int(typeid_str)] = item_data
        time.sleep(0.5)

    progress_callback({'scan_type': scan_type, 'progress': 0.5, 'status': "Steg 2: Finner kandidater..."})
    candidates = []
    for type_id in all_type_ids:
        item_data = prices_map.get(type_id)
        if not item_data or not item_data.get('buy') or not item_data.get('sell'): continue
        if float(item_data['buy']['max']) > 0 and float(item_data['sell']['min']) > float(item_data['buy']['max']):
            candidates.append(type_id)

    total_candidates, start_time = len(candidates), time.time()
    for i, type_id in enumerate(candidates):
        if not active_flag.is_set(): break
        item_name = id_to_name.get(type_id, f"ID: {type_id}")
        progress = 0.5 + ((i + 1) / total_candidates * 0.5) if total_candidates > 0 else 1
        eta = (total_candidates - (i + 1)) * ((time.time() - start_time) / (i + 1)) if i > 0 else None
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Sjekker finalist {i+1}/{total_candidates}: {item_name}", 'eta': f"ETA: {format_time(eta)}"})
        
        history = api.fetch_esi_history(station_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        
        trend = get_trend_indicator(history)
        orders_data = api.fetch_market_orders(station_info['region_id'], type_id)
        if not orders_data: continue
        
        highest_buy = max((o for o in orders_data if o['location_id'] == station_info['id'] and o['is_buy_order']), key=lambda x: x['price'], default=None)
        lowest_sell = min((o for o in orders_data if o['location_id'] == station_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)
        if not highest_buy or not lowest_sell: continue

        # Beregn antall konkurrenter
        comp_buy = sum(1 for o in orders_data if o['location_id'] == station_info['id'] and o['is_buy_order'] and o['price'] >= highest_buy['price'])
        comp_sell = sum(1 for o in orders_data if o['location_id'] == station_info['id'] and not o['is_buy_order'] and o['price'] <= lowest_sell['price'])
        
        buy_price = highest_buy['price'] + 0.01
        sell_price = lowest_sell['price'] - 0.01
        if buy_price >= sell_price: continue
        
        fees = (buy_price * (scan_config['brokers_fee_rate'] / 100)) + (sell_price * (scan_config['brokers_fee_rate'] / 100)) + (sell_price * (scan_config['sales_tax_rate'] / 100))
        net_profit = (sell_price - buy_price) - fees
        
        if net_profit < scan_config['min_profit'] or buy_price > scan_config['max_investment']: continue
        
        result = {
            'item': item_name, 'profit_per_unit': net_profit, 'profit_margin': (net_profit / buy_price) * 100 if buy_price > 0 else 0,
            'daily_volume': avg_daily_vol, 'buy_price': buy_price, 'sell_price': sell_price, 'trend': trend, 'competition': f"{comp_buy} / {comp_sell}"
        }
        progress_callback({'scan_type': 'region_trading', 'result': result})

    progress_callback({'scan_type': scan_type, 'status': 'Stasjonshandel-skann fullført!'})
