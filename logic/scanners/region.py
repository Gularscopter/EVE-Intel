# logic/scanners/region.py
import logging
import api

JITA_HUB_SYSTEM_IDS = {
    30000142,  # Jita
    30000144,  # Perimeter
}

def get_market_volume_stats(region_id, item_id):
    """Henter volumstatistikk for de siste 7 dagene."""
    stats = {'avg_volume': 0, 'active_days': 0}
    try:
        history = api.get_item_price_history(region_id, item_id)
        if not history or not isinstance(history, list) or not history:
            return stats
        
        last_7_days = history[-7:]
        active_days = sum(1 for day in last_7_days if day.get('volume', 0) > 0)
        stats['active_days'] = active_days
        
        if len(last_7_days) > 0:
            total_volume = sum(day.get('volume', 0) for day in last_7_days)
            stats['avg_volume'] = total_volume / len(last_7_days)

        return stats
    except Exception as e:
        logging.error(f"Feil under behandling av markedshistorikk for type_id {item_id}: {e}")
        return stats

def fetch_orders_for_item(item_id, region_id, min_daily_volume, min_active_days, is_debugging, access_token):
    """Henter nøyaktige ordre-detaljer og finner de beste prisene i Jita/Perimeter-systemene."""
    # Denne funksjonen bruker _ITEMS_DICT_CACHE, som nå er i worker-tråden.
    # For å unngå kompliserte avhengigheter, er det bedre å slå opp navnet etterpå.
    try:
        volume_stats = get_market_volume_stats(region_id, item_id)
        avg_daily_volume = volume_stats['avg_volume']
        active_trading_days = volume_stats['active_days']

        if avg_daily_volume < min_daily_volume: return None
        if active_trading_days < min_active_days: return None

        all_orders_in_region = []; page = 1
        while True:
            orders_page, total_pages = api.get_market_orders(region_id, "all", page, type_id=item_id)
            if not orders_page: break
            all_orders_in_region.extend(orders_page)
            if page >= total_pages: break
            page += 1
        
        if not all_orders_in_region: return None
        
        unique_location_ids = {order['location_id'] for order in all_orders_in_region}
        location_system_map = api.resolve_location_to_system_map(list(unique_location_ids), access_token)

        hub_orders = [
            order for order in all_orders_in_region
            if location_system_map.get(order['location_id']) in JITA_HUB_SYSTEM_IDS
        ]
        if not hub_orders: return None

        sell_prices = [o['price'] for o in hub_orders if not o.get('is_buy_order', True)]
        buy_prices = [o['price'] for o in hub_orders if o.get('is_buy_order', False)]
        if not sell_prices or not buy_prices: return None
            
        return {
            'Item ID': item_id,
            'Lowest Sell': min(sell_prices),
            'Highest Buy': max(buy_prices),
            'Avg Daily Vol': int(avg_daily_volume),
            'Aktive Dager': active_trading_days
        }
    except Exception as e:
        if is_debugging:
            logging.warning(f"Feil under detaljert henting av item_id {item_id}: {e}", exc_info=True)
        return None

def scan_region_for_profit(config, item_ids, access_token, progress_callback):
    """
    Scans a list of items using ESI, checks them against profitability criteria,
    and yields profitable items one by one.
    """
    total_items = len(item_ids)
    if total_items == 0:
        progress_callback("No items to scan.", 100)
        return

    progress_callback(f"Scanning {total_items} items...", 0)

    for i, item_id in enumerate(item_ids):
        progress_percentage = int(100 * (i + 1) / total_items)
        # The worker will add the item name to the status message
        progress_callback(f"Verifying item {i+1}/{total_items}", progress_percentage)

        item_data = fetch_orders_for_item(
            item_id=item_id,
            region_id=config['region_id'],
            min_daily_volume=config['min_avg_vol'],
            min_active_days=config['min_active_days'],
            is_debugging=config.get('is_debugging', False),
            access_token=access_token
        )
        
        if item_data:
            yield item_data
    
    progress_callback("Scan complete.", 100)