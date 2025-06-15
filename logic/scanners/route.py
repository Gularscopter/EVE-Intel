import time
import api
import config
from .helpers import get_trend_indicator, format_time

def run_route_scan(scan_config, all_type_ids, progress_callback):
    """Kjører ruteskann (stasjon til stasjon, både import og arbitrage)."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    scan_type = scan_config['scan_type']
    active_flag = scan_config['active_flag']
    base_progress = 0.1
    
    item_chunks = [all_type_ids[i:i + 200] for i in range(0, len(all_type_ids), 200)]
    buy_info = config.STATIONS_INFO[scan_config['buy_station']]
    sell_info = config.STATIONS_INFO[scan_config['sell_station']]
    
    progress_callback({'scan_type': scan_type, 'progress': base_progress, 'status': "Steg 1: Henter priser fra Fuzzwork..."})
    buy_prices_map, sell_prices_map = {}, {}
    for i, chunk in enumerate(item_chunks):
        if not active_flag.is_set(): return
        progress = base_progress + (i / len(item_chunks) * 0.4)
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Henter pris-gruppe {i+1}/{len(item_chunks)}..."})
        
        buy_data = api.fetch_fuzzwork_market_data(buy_info['id'], chunk)
        sell_data = api.fetch_fuzzwork_market_data(sell_info['id'], chunk)
        for typeid_str, data in (buy_data or {}).items(): buy_prices_map[int(typeid_str)] = data
        for typeid_str, data in (sell_data or {}).items(): sell_prices_map[int(typeid_str)] = data
        time.sleep(0.5)

    progress_callback({'scan_type': scan_type, 'progress': 0.5, 'status': "Steg 2: Finner kandidater..."})
    candidates = []
    for type_id in all_type_ids:
        buy_item, sell_item = buy_prices_map.get(type_id), sell_prices_map.get(type_id)
        if not buy_item or not sell_item or not buy_item.get('sell') or not sell_item.get('buy'): continue
        
        buy_price = float(buy_item['sell']['min'])
        # Arbitrage (salg->salg) har en annen salgsprismetode
        sell_price = float(sell_item['buy']['max'] if scan_type == 'station' else sell_item['sell']['min'])
        if buy_price > 0 and sell_price > buy_price:
            candidates.append(type_id)

    total_candidates, start_time = len(candidates), time.time()
    for i, type_id in enumerate(candidates):
        if not active_flag.is_set(): break
        item_name = id_to_name.get(type_id, f"ID: {type_id}")
        progress = 0.5 + ((i + 1) / total_candidates * 0.5) if total_candidates > 0 else 1
        eta = (total_candidates - (i + 1)) * ((time.time() - start_time) / (i + 1)) if i > 0 else None
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Sjekker finalist {i+1}/{total_candidates}: {item_name}", 'eta': f"ETA: {format_time(eta)}"})
        
        history = api.fetch_esi_history(sell_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        
        trend = get_trend_indicator(history)
        buy_orders_data = api.fetch_market_orders(buy_info['region_id'], type_id)
        sell_orders_data = api.fetch_market_orders(sell_info['region_id'], type_id)
        
        buy_order = min((o for o in (buy_orders_data or []) if o['location_id'] == buy_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)
        
        if scan_type == 'station':  # Kjøp -> Salg (Import)
            sell_order = max((o for o in (sell_orders_data or []) if o['location_id'] == sell_info['id'] and o['is_buy_order']), key=lambda x: x['price'], default=None)
        else:  # Salg -> Salg (Arbitrage)
            sell_order = min((o for o in (sell_orders_data or []) if o['location_id'] == sell_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)

        if not buy_order or not sell_order: continue
        
        buy_price, buy_volume_available = buy_order['price'], buy_order['volume_remain']
        sell_price, sell_volume_available = sell_order['price'], sell_order['volume_remain']

        if scan_type == 'station':
            net_sell_price = sell_price * (1 - scan_config['sales_tax_rate'] / 100.0)
        else: # For arbitrage må vi "undercut"-e selgeren
            sell_price -= 0.01
            net_sell_price = sell_price * (1 - (scan_config['sales_tax_rate'] + scan_config['brokers_fee_rate']) / 100.0)

        if buy_price <= 0 or net_sell_price <= buy_price: continue
        
        profit_margin = ((net_sell_price - buy_price) / buy_price) * 100
        type_attributes = api.fetch_type_attributes(type_id)
        if not type_attributes or 'volume' not in type_attributes: continue
        
        item_m3 = type_attributes.get('volume', 0)
        if item_m3 <= 0: continue
        
        units_affordable = scan_config['max_investment'] / buy_price
        units_in_cargo = scan_config['ship_cargo_m3'] / item_m3
        
        trade_limit = min(units_in_cargo, buy_volume_available, sell_volume_available, units_affordable)
        total_profit = trade_limit * (net_sell_price - buy_price)
        
        if total_profit >= scan_config['min_profit']:
            result = {
                'item': item_name, 'profit_per_trip': total_profit, 'profit_margin': profit_margin, 
                'units_to_trade': trade_limit, 'daily_volume': avg_daily_vol, 'buy_price': buy_price, 
                'sell_price': sell_price, 'buy_volume_available': buy_volume_available, 
                'sell_volume_available': sell_volume_available, 'trend': trend
            }
            progress_callback({'scan_type': scan_type, 'result': result})
        
        time.sleep(0.1)

    progress_callback({'scan_type': scan_type, 'status': 'Ruteskann fullført!'})
