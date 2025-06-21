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

def _get_market_prices(item_ids, status_callback):
    """
    Fetches market prices for a list of item IDs specifically from Jita 4-4
    using the more efficient Fuzzwork API endpoint.
    """
    JITA_STATION_ID = 60003760

    if not item_ids:
        return {}
        
    status_callback("Fetching market prices from Fuzzwork...", 10)
    
    # Use the api.get_market_prices which calls Fuzzwork.
    # It now accepts a status_callback to provide progress updates.
    prices_data = api.get_market_prices(item_ids, station_id=JITA_STATION_ID, status_callback=status_callback)

    # The prices_data is in the format {type_id: {'buy': X, 'sell': Y}}
    # We are interested in the lowest sell prices for materials and the product.
    item_prices = {item_id: data['sell'] for item_id, data in prices_data.items() if data['sell'] > 0}
    
    return item_prices


def find_profitable_bpos(product_name, me_level, te_level, tax_rate, status_callback):
    """
    Calculates the profitability of manufacturing a specific item from a blueprint,
    accounting for Material Efficiency (ME), with prices from Jita 4-4.
    """
    status_callback(f"Resolving blueprint for '{product_name}'...", 0)
    
    product_id = db.get_item_id(product_name)
    if not product_id:
        raise ValueError(f"Could not find item ID for '{product_name}'.")

    materials = db.get_blueprint_from_sde(product_id)
    if not materials:
        raise ValueError(f"Could not find blueprint materials for '{product_name}'.")

    status_callback("Applying material efficiency bonus...", 5)
    adjusted_materials = {}
    for material_name, quantity in materials.items():
        adjusted_quantity = quantity * (1 - (me_level / 100))
        adjusted_materials[material_name] = adjusted_quantity

    all_item_names = set(adjusted_materials.keys())
    all_item_names.add(product_name)

    status_callback("Converting item names to IDs...", 8)
    name_to_id_map = {name: db.get_item_id(name) for name in all_item_names}
    item_ids = [item_id for item_id in name_to_id_map.values() if item_id is not None]

    item_prices = _get_market_prices(item_ids, status_callback)
    
    status_callback("Calculating profitability...", 95)
    profitable_bpos = []
    material_details = []

    try:
        material_cost = 0
        for material_name, quantity in adjusted_materials.items():
            material_id = name_to_id_map.get(material_name)
            if material_id not in item_prices:
                raise ValueError(f"Price for material '{material_name}' not found.")
            
            price_per_unit = item_prices[material_id]
            total_cost = price_per_unit * quantity
            material_cost += total_cost
            
            material_details.append({
                'name': material_name,
                'quantity': quantity,
                'price_per_unit': price_per_unit,
                'total_cost': total_cost
            })
        
        # Apply base manufacturing tax (0.25%) and the system cost index
        base_tax = 0.0025  # 0.25%
        system_cost_index = tax_rate / 100
        manufacturing_cost = material_cost * (1 + base_tax + system_cost_index)

        if product_id not in item_prices:
            raise ValueError(f"Price for product '{product_name}' not found.")
        product_price = item_prices[product_id]
        
        if manufacturing_cost > 0:
            profit = product_price - manufacturing_cost
            margin = (profit / manufacturing_cost) * 100
            
            if profit > 0:
                profitable_bpos.append({
                    'name': product_name,
                    'cost': manufacturing_cost,
                    'price': product_price,
                    'profit': profit,
                    'margin': margin,
                    'materials': material_details
                })
    except Exception as e:
        logging.error(f"Error calculating profitability for {product_name}: {e}")

    status_callback("Calculation complete.", 100)
    return profitable_bpos

