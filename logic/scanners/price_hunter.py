import heapq
import logging
import api
import db

def run_price_hunter_scan(scan_config, status_callback):
    """Scanner alle regioner for den beste prisen på en spesifikk vare."""
    
    type_id = scan_config.get('type_id')
    order_type = scan_config.get('order_type')
    
    if not type_id:
        raise ValueError("Mangler vare-ID for søket.")

    status_callback("Henter system- og regiondata...", 5)
    all_regions = db.get_all_regions()
    system_security = db.get_all_system_security()
    station_to_system = db.get_station_to_system_map()

    top_orders = []
    total_regions = len(all_regions)
    tie_breaker = 0

    for i, region in enumerate(all_regions):
        progress = 10 + int((i / total_regions) * 85)
        status_callback(f"Sjekker region {i+1}/{total_regions}: {region['name']}...", progress)

        page = 1
        while True:
            orders_page, total_pages = api.get_market_orders(region['id'], order_type, page, type_id=type_id)
            if not orders_page: break
            
            for order in orders_page:
                price = order['price']
                tie_breaker += 1
                
                # Bruker en min-heap for å effektivt holde styr på de 20 beste ordrene.
                # For salgsordrer (lavest pris) bruker vi negativ pris for å simulere en max-heap.
                # For kjøpsordrer (høyest pris) bruker vi positiv pris for en min-heap.
                if order_type == 'sell':
                    order_tuple = (price, tie_breaker, order)
                    if len(top_orders) < 20:
                        heapq.heappush(top_orders, order_tuple)
                    elif order_tuple[0] < top_orders[-1][0]: # Merk: justert for min-heap
                        heapq.heappushpop(top_orders, order_tuple)
                else: # buy orders
                    order_tuple = (-price, tie_breaker, order) # Bruker negativ for å finne høyeste
                    if len(top_orders) < 20:
                        heapq.heappush(top_orders, order_tuple)
                    elif order_tuple[0] > top_orders[0][0]:
                        heapq.heapreplace(top_orders, order_tuple)

            if page >= total_pages or page > 50: break
            page += 1

    if not top_orders:
        status_callback(f"Fant ingen ordre for '{scan_config.get('item_name')}' i noen regioner.", 100)
        return []
    
    status_callback("Forbereder resultater...", 98)
    final_station_ids = [order_data[2]['location_id'] for order_data in top_orders]
    station_names = db.get_station_names(final_station_ids)
    
    final_results = []
    for _, _, order_data in top_orders:
        system_id = station_to_system.get(order_data['location_id'])
        sec_status_val = system_security.get(system_id, 0.0)
        
        final_results.append({
            'price': order_data['price'],
            'quantity': order_data['volume_remain'],
            'location_name': station_names.get(order_data['location_id'], "Ukjent Stasjon"),
            'system_name': db.get_system_name(system_id),
            'sec_status': sec_status_val
        })
        
    sort_reverse = True if order_type == 'buy' else False
    return sorted(final_results, key=lambda x: x['price'], reverse=sort_reverse)