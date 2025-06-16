import logging
from collections import defaultdict
import api 
import db
from logic.scanners.route import get_route # <--- DENNE LINJEN ER NÅ KORRIGERT

def find_best_deals(start_station_name, end_station_name, max_volume, tax_rate, status_callback):
    """
    Finner de beste handelsrutene mellom to stasjoner.
    """
    status_callback("Resolving station names to IDs...")
    logging.info(f"Finding deals from '{start_station_name}' to '{end_station_name}'")

    start_station_id = api.resolve_name_to_id(start_station_name, category='station')
    end_station_id = api.resolve_name_to_id(end_station_name, category='station')

    if not start_station_id: raise ValueError(f"Could not find station ID for '{start_station_name}'. Check spelling.")
    if not end_station_id: raise ValueError(f"Could not find station ID for '{end_station_name}'. Check spelling.")

    status_callback("Fetching station details (System/Region)...")
    start_station_details = api.get_station_details(start_station_id)
    end_station_details = api.get_station_details(end_station_id)

    if not start_station_details: raise ValueError(f"Could not fetch details for start station ID {start_station_id}.")
    if not end_station_details: raise ValueError(f"Could not fetch details for end station ID {end_station_id}.")

    start_region_id = start_station_details['region_id']
    end_region_id = end_station_details['region_id']
    
    try:
        route_info = get_route(start_station_details['system_id'], end_station_details['system_id'])
        jumps = len(route_info) - 1 if route_info else float('inf')
    except Exception as e:
        logging.warning(f"Could not calculate jumps: {e}. Defaulting to infinity.")
        jumps = float('inf')

    status_callback("Fetching market buy orders...")
    buy_orders = []
    page = 1
    while True:
        orders = api.get_market_orders(int(start_region_id), "buy", page)
        if not orders: break
        buy_orders.extend(orders)
        page += 1
        status_callback(f"Fetched page {page} of buy orders from region {start_region_id}...")

    status_callback("Fetching market sell orders...")
    sell_orders = []
    page = 1
    while True:
        orders = api.get_market_orders(int(end_region_id), "sell", page)
        if not orders: break
        sell_orders.extend(orders)
        page += 1
        status_callback(f"Fetched page {page} of sell orders from region {end_region_id}...")
    
    status_callback("Processing and comparing orders...")
    
    best_buy_prices = defaultdict(lambda: float('-inf'))
    for order in buy_orders:
        if order.get('location_id') == start_station_id:
            best_buy_prices[order['type_id']] = max(best_buy_prices[order['type_id']], order['price'])

    best_sell_prices = defaultdict(lambda: float('inf'))
    for order in sell_orders:
        if order.get('location_id') == end_station_id:
            best_sell_prices[order['type_id']] = min(best_sell_prices[order['type_id']], order['price'])
            
    profitable_deals = []
    
    common_type_ids = set(best_buy_prices.keys()) & set(best_sell_prices.keys())
    status_callback(f"Found {len(common_type_ids)} potential items. Analyzing profits...")
    
    for type_id in common_type_ids:
        buy_price = best_buy_prices[type_id]
        sell_price = best_sell_prices[type_id]
        
        profit_before_tax = sell_price - buy_price
        tax = sell_price * (tax_rate / 100.0)
        profit_per_unit = profit_before_tax - tax
        
        if profit_per_unit <= 0: continue
            
        margin = (profit_per_unit / buy_price) * 100 if buy_price > 0 else 0
        volume = db.get_item_volume(type_id) or float('inf')
        
        if volume > max_volume: continue
        if buy_price <= 0 or sell_price <= 0: continue

        profit_per_jump = profit_per_unit / jumps if jumps > 0 else float('inf')

        profitable_deals.append({
            'item_id': type_id,
            'item_name': db.get_item_name(type_id) or "Unknown Item",
            'buy_station': start_station_name,
            'buy_price': buy_price,
            'sell_station': end_station_name,
            'sell_price': sell_price,
            'profit_per_unit': profit_per_unit,
            'volume': volume,
            'margin': margin,
            'jumps': jumps,
            'profit_per_jump': profit_per_jump
        })

    profitable_deals.sort(key=lambda x: x['profit_per_jump'], reverse=True)
    
    status_callback(f"Analysis complete. Found {len(profitable_deals)} profitable deals.")
    logging.info(f"Found {len(profitable_deals)} profitable deals.")
    
    return profitable_deals
