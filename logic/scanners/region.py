import logging
from collections import defaultdict
import api
import db
from .helpers import get_trend_indicator

def find_best_trades_in_region(region_name, min_profit, min_margin, status_callback):
    """
    Finds profitable trades within a region by comparing region-wide
    buy and sell prices from an aggregated source (Fuzzwork).
    """
    try:
        status_callback(f"Resolving region ID for '{region_name}'...")
        
        # ESI does not have a direct 'search region by name' endpoint.
        # This map provides IDs for major trade hubs.
        region_map = {
            "the forge": 10000002, "sinq laison": 10000032, "domain": 10000043, 
            "heimatar": 10000030, "metropolis": 10000042, "delve": 10000069
        }
        region_id = region_map.get(region_name.lower())

        if not region_id:
            raise ValueError(f"Could not resolve region ID for '{region_name}'. Please use a major trade region (e.g., The Forge, Sinq Laison, Domain).")
        
        status_callback(f"Region ID {region_id} found. Loading filtered item list...")
        
        item_ids = db.get_filtered_item_ids()
        if not item_ids:
            raise ValueError("Item list is empty. Please generate the item list in the Settings tab.")
        
        status_callback(f"Loaded {len(item_ids)} items. Fetching aggregate prices for region...")

        # Correctly call the updated API function with the 'region_id' keyword
        market_prices = api.get_market_prices(item_ids, region_id=region_id)

        if not market_prices:
            raise ValueError("Could not fetch market prices for the region. The API might be down or the region has no orders for the filtered items.")
            
        status_callback("Analyzing potential deals...")
        profitable_deals = []
        for item_id, prices in market_prices.items():
            # Fuzzwork provides max buy and min sell for the region
            buy_price = prices.get('buy', 0)
            sell_price = prices.get('sell', 0)

            if buy_price == 0 or sell_price == 0:
                continue

            profit = sell_price - buy_price
            if profit < min_profit:
                continue

            margin = (profit / buy_price) * 100 if buy_price > 0 else 0
            if margin < min_margin:
                continue

            item_name = db.get_item_name(item_id) or f"Item ID {item_id}"
            
            # Since prices are aggregated for the whole region, we can't specify exact stations.
            profitable_deals.append({
                'item_name': item_name,
                'buy_station': f"{region_name} (Region-wide)",
                'sell_station': f"{region_name} (Region-wide)",
                'profit': profit,
                'margin': margin,
                'volume_str': "N/A",  # Getting volume would require many slow ESI calls
                'price': sell_price
            })

        profitable_deals.sort(key=lambda x: x['profit'], reverse=True)
        status_callback("Region scan complete.")
        return profitable_deals

    except Exception as e:
        logging.error(f"Error in region scan: {e}", exc_info=True)
        # Directly send the error to the status bar to be visible
        status_callback(f"Region Scan ERROR: {e}")
        return []