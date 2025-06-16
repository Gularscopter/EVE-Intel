import logging
from collections import defaultdict
import api
import db

# This dictionary defines the reprocessing yields for certain ores.
# In the context of this scanner, these act as our "blueprints".
# This is based on the logic from the original GitHub file.
blueprints = {
    'Veldspar Batch (100 units)': {
        'materials': {'Veldspar': 100},
        'products': {'Tritanium': 415, 'Pyerite': 218}
    },
    'Scordite Batch (100 units)': {
        'materials': {'Scordite': 100},
        'products': {'Tritanium': 218, 'Pyerite': 109}
    },
    # More blueprints/reprocessing yields could be added here
}

def _get_market_prices(region_id, item_ids, status_callback):
    """
    Fetches the lowest sell price for a list of items in a given region.
    This is used to determine the cost of materials.
    """
    item_prices = {}
    all_orders = []
    page = 1
    
    status_callback("Fetching market orders for materials and products...")
    # Fetch all sell orders in the region
    while True:
        orders = api.get_market_orders(region_id, "sell", page)
        if not orders:
            break
        all_orders.extend(orders)
        page += 1
        status_callback(f"Fetched page {page} of sell orders...")

    # Find the minimum sell price for each required item
    min_sell_prices = defaultdict(lambda: float('inf'))
    for order in all_orders:
        if order['type_id'] in item_ids:
            min_sell_prices[order['type_id']] = min(min_sell_prices[order['type_id']], order['price'])

    for item_id in item_ids:
        price = min_sell_prices.get(item_id)
        if price and price != float('inf'):
            item_prices[item_id] = price
            
    return item_prices


def find_profitable_bpos(region_name, status_callback):
    """
    Calculates the profitability of reprocessing certain ore batches (defined in 'blueprints').
    This function is adapted from the original logic in the GitHub repository.
    """
    status_callback(f"BPO Scanner: Resolving region ID for '{region_name}'...")
    
    # Use a major hub to find the region ID. This logic can be expanded.
    hubs = {"The Forge": "Jita IV - Moon 4 - Caldari Navy Assembly Plant", "Domain": "Amarr VIII (Oris) - Emperor Family Academy"}
    station_name_for_region = hubs.get(region_name)
    
    if not station_name_for_region:
        raise ValueError(f"Cannot determine region ID for '{region_name}'. Try a major hub like 'The Forge'.")

    station_id = api.resolve_name_to_id(station_name_for_region, 'station')
    station_details = api.get_station_details(station_id)
    if not station_details:
        raise ValueError(f"Could not fetch details for station '{station_name_for_region}' to determine region.")
    
    region_id = station_details['region_id']
    status_callback(f"Scanning region ID {region_id}...")

    # Gather all unique material and product IDs needed for the scan
    all_item_names = set()
    for bpo_data in blueprints.values():
        all_item_names.update(bpo_data['materials'].keys())
        all_item_names.update(bpo_data['products'].keys())

    # Convert names to IDs
    name_to_id_map = {name: db.get_item_id(name) for name in all_item_names}
    id_to_name_map = {v: k for k, v in name_to_id_map.items() if v is not None}
    all_item_ids = list(id_to_name_map.keys())

    # Get market prices for all items
    item_prices = _get_market_prices(region_id, all_item_ids, status_callback)
    
    status_callback("Calculating profitability...")
    profitable_bpos = []

    for name, bpo_data in blueprints.items():
        try:
            # Calculate total cost of materials
            manufacturing_cost = 0
            for material_name, quantity in bpo_data['materials'].items():
                material_id = name_to_id_map.get(material_name)
                if material_id not in item_prices:
                    raise ValueError(f"Price for material '{material_name}' not found.")
                manufacturing_cost += item_prices[material_id] * quantity
            
            # Calculate total value of products
            product_value = 0
            for product_name, quantity in bpo_data['products'].items():
                product_id = name_to_id_map.get(product_name)
                if product_id not in item_prices:
                    raise ValueError(f"Price for product '{product_name}' not found.")
                product_value += item_prices[product_id] * quantity
            
            if manufacturing_cost > 0:
                profit = product_value - manufacturing_cost
                margin = (profit / manufacturing_cost) * 100
                
                # Only add if profitable
                if profit > 0:
                    profitable_bpos.append({
                        'name': name,
                        'cost': manufacturing_cost,
                        'price': product_value,
                        'profit': profit,
                        'margin': margin
                    })
        except (ValueError, KeyError) as e:
            logging.warning(f"Skipping BPO '{name}' due to calculation error: {e}")
            continue
            
    profitable_bpos.sort(key=lambda x: x['profit'], reverse=True)
    status_callback("BPO scan complete.")
    return profitable_bpos

