import logging
from itertools import permutations
from collections import defaultdict
import api
import db
import requests

def _get_all_region_ids():
    """Fetches all region IDs from the ESI."""
    try:
        response = requests.get(f"{api.BASE_URL}/universe/regions/")
        response.raise_for_status()
        # Filter out wormhole regions, which usually start with 11
        return [region_id for region_id in response.json() if not str(region_id).startswith('11')]
    except requests.RequestException as e:
        logging.error(f"Could not fetch region list: {e}")
        return []

def find_best_trades_galaxy(min_profit, min_margin, status_callback):
    """
    Scans for the best region-to-region trades across the entire galaxy.
    WARNING: This is extremely resource-intensive and will take a very long time.
    """
    status_callback("Fetching list of all regions...")
    all_region_ids = _get_all_region_ids()
    if not all_region_ids:
        raise ValueError("Could not fetch the list of regions to scan.")

    status_callback(f"Found {len(all_region_ids)} regions. This will take a VERY long time.")
    
    all_market_orders = {}
    total_regions = len(all_region_ids)
    for i, region_id in enumerate(all_region_ids):
        status_callback(f"Fetching market data for region {i+1}/{total_regions} (ID: {region_id})...")
        region_orders = []
        page = 1
        while True:
            orders = api.get_market_orders(region_id, "all", page)
            if not orders:
                break
            region_orders.extend(orders)
            page += 1
        all_market_orders[region_id] = region_orders

    status_callback("All market data downloaded. Analyzing trades...")
    
    best_buy_prices = defaultdict(lambda: (float('-inf'), None)) # (price, region_id)
    best_sell_prices = defaultdict(lambda: (float('inf'), None)) # (price, region_id)

    # Find the absolute best buy and sell prices for each item across all regions
    for region_id, orders in all_market_orders.items():
        for order in orders:
            item_id = order['type_id']
            price = order['price']
            if order['is_buy_order']:
                if price > best_buy_prices[item_id][0]:
                    best_buy_prices[item_id] = (price, region_id)
            else:
                if price < best_sell_prices[item_id][0]:
                    best_sell_prices[item_id] = (price, region_id)

    profitable_trades = []
    common_items = set(best_buy_prices.keys()) & set(best_sell_prices.keys())
    status_callback(f"Found {len(common_items)} potential trades. Calculating profits...")

    for i, item_id in enumerate(common_items):
        if i > 0 and i % 100 == 0:
            status_callback(f"Calculating profit for item {i+1}/{len(common_items)}...")

        buy_price, buy_region_id = best_buy_prices[item_id]
        sell_price, sell_region_id = best_sell_prices[item_id]

        if buy_region_id == sell_region_id:
            continue # We are looking for inter-region trades

        profit = sell_price - buy_price
        
        if profit < min_profit:
            continue

        margin = (profit / buy_price) * 100 if buy_price > 0 else 0
        if margin < min_margin:
            continue
            
        # To get region names, we need a lookup. We can't easily get it from ID.
        # This is a limitation. We will show IDs for now.
        # In a future version, a region ID to name map could be built.
        
        profitable_trades.append({
            'item_id': item_id,
            'item_name': db.get_item_name(item_id) or "Unknown Item",
            'buy_region': f"Region ID: {buy_region_id}",
            'sell_region': f"Region ID: {sell_region_id}",
            'profit': profit,
            'margin': margin,
            'volume': db.get_item_volume(item_id) or 0.0
        })

    profitable_trades.sort(key=lambda x: x['profit'], reverse=True)
    status_callback("Galaxy scan complete.")
    return profitable_trades
