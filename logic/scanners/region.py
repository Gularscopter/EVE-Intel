import logging
from collections import defaultdict
import api
import db
from .helpers import get_trend_indicator # Importerer nå fra den gjenopprettede filen

def find_best_trades_in_region(region_name, min_profit, min_margin, status_callback):
    """
    Finds the best station-to-station trades within a single region.
    """
    status_callback(f"Resolving region ID for '{region_name}'...")
    # We need a station in the region to find the region_id. This is a limitation of the API design.
    # We'll try to find a major trade hub in that region if possible.
    # This is a bit of a hack. A better way would be a local region name -> ID map.
    
    # A robust way to get region_id from region_name is not straightforward via ESI.
    # This part of the logic needs to be improved, maybe with a static map.
    # For now, we will assume a direct lookup is possible IF we can find a station.
    # Let's try to find the region ID from a known station if it's a hub name.
    hubs = {"The Forge": "Jita IV - Moon 4 - Caldari Navy Assembly Plant"}
    station_name_for_region = hubs.get(region_name)
    
    if not station_name_for_region:
        raise ValueError(f"Cannot determine a station to find the region ID for '{region_name}'. This feature is limited to major hubs for now.")

    station_id = api.resolve_name_to_id(station_name_for_region, 'station')
    station_details = api.get_station_details(station_id)
    if not station_details:
        raise ValueError(f"Could not fetch details for station '{station_name_for_region}'")
    
    region_id = station_details['region_id']
    status_callback(f"Region ID {region_id} found. Fetching all market orders...")

    all_orders = []
    page = 1
    while True:
        status_callback(f"Fetching market orders page {page}...")
        orders = api.get_market_orders(region_id, "all", page)
        if not orders:
            break
        all_orders.extend(orders)
        page += 1

    status_callback("Analyzing buy and sell orders...")
    buy_orders = defaultdict(list)
    sell_orders = defaultdict(list)

    for order in all_orders:
        if order.get('is_buy_order'):
            buy_orders[order['type_id']].append(order)
        else:
            sell_orders[order['type_id']].append(order)

    profitable_deals = []
    common_items = set(buy_orders.keys()) & set(sell_orders.keys())
    status_callback(f"Found {len(common_items)} common items. Calculating profits...")

    for i, item_id in enumerate(common_items):
        if i > 0 and i % 50 == 0:
            status_callback(f"Analyzing item {i+1}/{len(common_items)}...")

        # Find best buy (highest price) and best sell (lowest price) in the region
        best_buy_order = max(buy_orders[item_id], key=lambda x: x['price'])
        best_sell_order = min(sell_orders[item_id], key=lambda x: x['price'])

        profit = best_sell_order['price'] - best_buy_order['price']

        if profit < min_profit:
            continue
        
        margin = (profit / best_buy_order['price']) * 100 if best_buy_order['price'] > 0 else 0
        
        if margin < min_margin:
            continue

        # Get extra details
        history = api.get_item_price_history(region_id, item_id)
        trend = get_trend_indicator(history)
        
        daily_volume = history[-1]['volume'] if history else 0
        volume_str = f"{daily_volume:,}" if daily_volume > 0 else "N/A"
        
        buy_station_details = api.get_station_details(best_buy_order['location_id'])
        sell_station_details = api.get_station_details(best_sell_order['location_id'])

        profitable_deals.append({
            'item_name': db.get_item_name(item_id) or f"Item ID {item_id}",
            'buy_station': buy_station_details['name'] if buy_station_details else 'Unknown Station',
            'sell_station': sell_station_details['name'] if sell_station_details else 'Unknown Station',
            'profit': profit,
            'margin': margin,
            'volume_str': f"{trend} {volume_str}",
            'price': best_sell_order['price']
        })

    profitable_deals.sort(key=lambda x: x['profit'], reverse=True)
    status_callback("Region scan complete.")
    return profitable_deals
