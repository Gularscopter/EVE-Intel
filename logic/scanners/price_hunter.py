import heapq
import api
import config
import db

def run_price_hunter_scan(scan_config, progress_callback):
    """Scanner alle regioner for den billigste salgsordren av en vare."""
    active_flag = scan_config.get('active_flag')
    scan_type = scan_config.get('scan_type')
    type_id = scan_config['type_id']
    item_name = scan_config['item_name']

    progress_callback({'scan_type': scan_type, 'progress': 0, 'status': "Henter system-sikkerhet..."})
    system_securities = db.get_all_system_security_statuses()
    if not system_securities:
        progress_callback({'scan_type': scan_type, 'error': "Kunne ikke laste system-data fra SDE."})
        return

    security_map = {}
    if scan_config.get('include_hisec', True):
        for sys_id, sec in system_securities.items():
            if sec >= 0.5: security_map[sys_id] = "High"
    if scan_config.get('include_lowsec', False):
        for sys_id, sec in system_securities.items():
            if 0.0 < sec < 0.5: security_map[sys_id] = "Low"
    if scan_config.get('include_nullsec', False):
         for sys_id, sec in system_securities.items():
            if sec <= 0.0: security_map[sys_id] = "Null"
    
    if not config.ALL_REGIONS_CACHE: api.populate_all_regions_cache()
    all_regions = [rid for rid in config.ALL_REGIONS_CACHE.values() if str(rid).startswith("10")]
    total_regions = len(all_regions)
    cheapest_orders = []
    
    for i, region_id in enumerate(all_regions):
        if not active_flag.is_set():
            progress_callback({'scan_type': scan_type, 'status': 'Skann avbrutt.'})
            return
        
        region_name = [name for name, r_id in config.ALL_REGIONS_CACHE.items() if r_id == region_id][0]
        progress = (i + 1) / total_regions
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Skanner region {i+1}/{total_regions}: {region_name}"})
        
        url = f"https://esi.evetech.net/latest/markets/{region_id}/orders/?datasource=tranquility&order_type=sell&type_id={type_id}"
        orders_in_region = api.fetch_all_pages(url)

        if not orders_in_region: continue

        for order in orders_in_region:
            system_id = order.get('system_id')
            if system_id in security_map:
                price = order['price']
                # Bruker en min-heap for å effektivt holde styr på de 20 billigste
                order_tuple = (price, order['order_id'], order)

                if len(cheapest_orders) < 20:
                    heapq.heappush(cheapest_orders, order_tuple)
                elif price < cheapest_orders[0][0]:
                    heapq.heapreplace(cheapest_orders, order_tuple)

    if not cheapest_orders:
        progress_callback({'scan_type': scan_type, 'status': f"Fant ingen salgsordrer for '{item_name}' i valgte områder."})
        return
        
    final_results = sorted([item[2] for item in cheapest_orders], key=lambda x: x['price'])

    for order in final_results:
        result = {
            'item_name': item_name, 'price': order['price'], 'quantity': order['volume_remain'],
            'location_name': api.get_station_name_with_cache(order['location_id']),
            'system_name': db.get_system_name_from_sde(order['system_id']),
            'security': security_map.get(order['system_id'], "N/A")
        }
        progress_callback({'scan_type': 'price_hunter', 'result': result})
    
    progress_callback({'scan_type': scan_type, 'status': f"Prisjakt for '{item_name}' fullført."})

