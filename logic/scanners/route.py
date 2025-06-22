import requests
import logging
from itertools import permutations
from collections import defaultdict
import api
import db

BASE_URL = "https://esi.evetech.net/latest"

def get_route(origin_system_id, destination_system_id, route_flag='shortest'):
    """
    Calculates the route between two solar systems using the ESI API.
    """
    if not origin_system_id or not destination_system_id:
        logging.warning("get_route received invalid system IDs.")
        return None

    params = {'flag': route_flag}
    url = f"{BASE_URL}/route/{origin_system_id}/{destination_system_id}/"
    
    try:
        logging.info(f"Fetching route from {origin_system_id} to {destination_system_id}")
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get route between {origin_system_id} and {destination_system_id}: {e}")
        return None

def find_best_trades_along_route(start_system_name, end_system_name, max_jumps_from_route, status_callback):
    """
    Finds the best trading opportunities in systems along a specified route.
    """
    status_callback("Resolving start and end systems...")
    start_system_id = api.resolve_name_to_id(start_system_name, 'solar_system')
    end_system_id = api.resolve_name_to_id(end_system_name, 'solar_system')

    if not start_system_id: raise ValueError(f"Could not find start system: {start_system_name}")
    if not end_system_id: raise ValueError(f"Could not find end system: {end_system_name}")

    status_callback("Calculating main route...")
    main_route = get_route(start_system_id, end_system_id)
    if not main_route:
        raise ValueError("Could not calculate the main route.")

    # Denne logikken er kompleks og er foreløpig en forenkling.
    # En full implementasjon ville trengt en statisk data-dump (SDE) for å effektivt finne alle systemer innen N hopp.
    systems_to_scan = set(main_route)
    status_callback(f"Scanning {len(systems_to_scan)} systems on the main route...")
    
    start_station_details = api.get_station_details(api.resolve_name_to_id(f"{start_system_name} I", 'station')) # Hack to get region
    if not start_station_details: raise ValueError("Cannot determine region of start system.")
    region_id = start_station_details['region_id']

    status_callback(f"Fetching all market orders for region ID {region_id}... This can take a very long time.")
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
        if order['is_buy_order']:
            buy_orders[order['type_id']].append(order)
        else:
            sell_orders[order['type_id']].append(order)

    profitable_trades = []
    common_items = set(buy_orders.keys()) & set(sell_orders.keys())
    status_callback(f"Found {len(common_items)} common items. Calculating profits...")

    for i, item_id in enumerate(common_items):
        if i % 50 == 0:
            status_callback(f"Analyzing item {i+1}/{len(common_items)}...")
        
        best_buy = max(buy_orders[item_id], key=lambda x: x['price'])
        best_sell = min(sell_orders[item_id], key=lambda x: x['price'])

        if best_sell['price'] > best_buy['price']:
            profit = best_sell['price'] - best_buy['price']
            margin = (profit / best_buy['price']) * 100 if best_buy['price'] > 0 else 0
            
            buy_station_details = api.get_station_details(best_buy['location_id'])
            sell_station_details = api.get_station_details(best_sell['location_id'])
            
            if not buy_station_details or not sell_station_details: continue

            # Sjekk at handelen skjer innenfor systemene vi vil skanne
            if buy_station_details['system_id'] not in systems_to_scan or sell_station_details['system_id'] not in systems_to_scan:
                continue

            route_between_stations = get_route(buy_station_details['system_id'], sell_station_details['system_id'])
            jumps = len(route_between_stations) - 1 if route_between_stations else float('inf')

            profitable_trades.append({
                'item_name': db.get_item_name(item_id) or f"Item ID {item_id}",
                'buy_station': buy_station_details['name'],
                'sell_station': sell_station_details['name'],
                'profit': profit,
                'margin': margin,
                'jumps': jumps
            })

    profitable_trades.sort(key=lambda x: x['profit'], reverse=True)
    status_callback("Route scan complete.")
    return profitable_trades
