import logging
from collections import defaultdict
import api
import db
from logic.route_planner import find_shortest_path
import random

def _create_optimal_bundle(items, cargo_capacity, max_investment, station_name="Multi-Stasjon"):
    """
    Each trade dict in the returned bundle['trades'] list will have the following structure:
    {
        'type_id': int,
        'item_name': str,
        'buy_price': float,
        'sell_price': float,
        'profit_per_item': float,
        'fitted_quantity': int,
        'buy_location_id': int,
        'buy_location_type': str,  # 'station' or 'structure'
        'sell_location_id': int,
        'sell_location_type': str,
        'buy_system_id': int,
        'sell_system_id': int,
        'jumps': int,
        'volume': float,  # per unit
        'total_profit_for_item': float,
        'buy_station_name': str,
        'sell_station_name': str,
        ... (other fields as needed)
    }
    """
    for item in items:
        item['profit_density'] = item['net_profit_per_unit'] / item['item_m3'] if item.get('item_m3', 0) > 0 else 0

    sorted_items = sorted(items, key=lambda x: x['profit_density'], reverse=True)
    
    bundle_items, total_profit, total_investment, total_volume = [], 0, 0, 0
    remaining_cargo, remaining_investment = cargo_capacity, max_investment
    
    for item in sorted_items:
        if remaining_cargo <= 0 or remaining_investment <= 0: break
        
        buy_price, item_m3 = item.get('buy_price', 0), item.get('item_m3', 0)
        if buy_price <= 0 or item_m3 <= 0: continue
            
        units_affordable = int(remaining_investment // buy_price)
        units_that_fit = int(remaining_cargo // item_m3)
        available_volume = item.get('available_volume', 0)
        
        num_to_buy = min(units_affordable, units_that_fit, available_volume)
        
        if num_to_buy > 0:
            item_cost = num_to_buy * buy_price
            item_volume = num_to_buy * item_m3
            item_profit = num_to_buy * item['net_profit_per_unit']
            item_data = {
                'type_id': item.get('item_id', 0),
                'item_name': item.get('item_name', ''),
                'buy_price': buy_price,
                'sell_price': item.get('sell_price', 0),
                'profit_per_item': item.get('net_profit_per_unit', 0),
                'fitted_quantity': num_to_buy,
                'buy_location_id': item.get('buy_location_id', item.get('buy_station_id', 0)),
                'buy_location_type': item.get('buy_location_type', ''),
                'sell_location_id': item.get('sell_location_id', item.get('sell_station_id', 0)),
                'sell_location_type': item.get('sell_location_type', ''),
                'buy_system_id': item.get('buy_system_id', 0),
                'sell_system_id': item.get('sell_system_id', 0),
                'jumps': item.get('jumps', 0),
                'volume': item_m3,
                'total_profit_for_item': item_profit,
                'buy_station_name': item.get('buy_station_name', 'Ukjent'),
                'sell_station_name': item.get('sell_station_name', 'Ukjent'),
                'buy_volume': item.get('buy_volume', 0),
                'sell_volume': item.get('sell_volume', 0),
                'volume_str': f"{item.get('buy_volume', 0):,} / {item.get('sell_volume', 0):,}",
            }
            bundle_items.append(item_data)
            
            total_profit += item_profit; total_investment += item_cost; total_volume += item_volume
            remaining_cargo -= item_volume; remaining_investment -= item_cost
    bundle = {
        'items': bundle_items,  # legacy
        'trades': bundle_items,
        'total_profit': total_profit,
        'total_investment': total_investment,
        'total_volume': total_volume,
        'station_name': station_name
    }
    return bundle

def run_galaxy_scan(scan_config, status_callback):
    status_callback("Forbereder...", 0)
    buy_region_id = api.resolve_name_to_id(scan_config['buy_region'], 'region')
    sell_region_id = api.resolve_name_to_id(scan_config['sell_region'], 'region')
    if not buy_region_id or not sell_region_id: raise ValueError("Kunne ikke finne region-ID.")

    all_type_ids = db.get_filtered_item_ids(status_callback=status_callback)
    if not all_type_ids: raise ValueError("Varelisten er tom.")

    status_callback("Steg 1: Henter prisoversikt fra Fuzzwork...", 5)
    buy_region_prices = api.get_market_prices(all_type_ids, region_id=buy_region_id)
    sell_region_prices = api.get_market_prices(all_type_ids, region_id=sell_region_id)

    profitable_candidates = {
        item_id: {'target_buy_price': buy_info.get('sell', 0), 'target_sell_price': sell_info.get('buy', 0)}
        for item_id, buy_info in buy_region_prices.items()
        if (sell_info := sell_region_prices.get(item_id)) and buy_info.get('sell', 0) > 0 and sell_info.get('buy', 0) > buy_info.get('sell', 0)
    }
    if not profitable_candidates:
        status_callback("Fullført. Fant ingen potensielle handler.", 100)
        return []

    status_callback(f"Steg 2: Fant {len(profitable_candidates)} kandidater. Starter ESI-søk...", 10)
    found_buy_orders, found_sell_orders = {}, {}
    items_to_find_buys, items_to_find_sells = set(profitable_candidates.keys()), set(profitable_candidates.keys())

    _, total_sell_pages = api.get_market_orders(buy_region_id, "sell", 1)
    # Begrenser sidetall for å unngå for lange søk
    for page in range(1, min(total_sell_pages, 200) + 1):
        if not items_to_find_buys: break
        progress = 10 + int((page / min(total_sell_pages, 200)) * 40)
        status_callback(f"Søker i salgsordrer i {scan_config['buy_region']} (side {page}/{total_sell_pages})...", progress)
        orders_page, _ = api.get_market_orders(buy_region_id, "sell", page)
        if not orders_page: break
        for order in orders_page:
            if (item_id := order['type_id']) in items_to_find_buys and order['price'] <= profitable_candidates[item_id]['target_buy_price']:
                found_buy_orders[item_id] = order; items_to_find_buys.remove(item_id)

    _, total_buy_pages = api.get_market_orders(sell_region_id, "buy", 1)
    for page in range(1, min(total_buy_pages, 200) + 1):
        if not items_to_find_sells: break
        progress = 50 + int((page / min(total_buy_pages, 200)) * 40)
        status_callback(f"Søker i kjøpsordrer i {scan_config['sell_region']} (side {page}/{total_buy_pages})...", progress)
        orders_page, _ = api.get_market_orders(sell_region_id, "buy", page)
        if not orders_page: break
        for order in orders_page:
            if (item_id := order['type_id']) in items_to_find_sells and order['price'] >= profitable_candidates[item_id]['target_sell_price']:
                found_sell_orders[item_id] = order; items_to_find_sells.remove(item_id)

    status_callback("Kobler sammen og forbereder data...", 90)
    all_location_ids = {o['location_id'] for o in found_buy_orders.values()} | {o['location_id'] for o in found_sell_orders.values()}
    station_to_system_map = db.get_station_to_system_map()
    
    # Henter alle stasjons- og strukturnavn i færre kall
    npc_station_ids = {loc_id for loc_id in all_location_ids if loc_id in station_to_system_map}
    player_structure_ids = all_location_ids - npc_station_ids
    location_name_map = {}
    if npc_station_ids:
        sde_names = db.get_station_names(list(npc_station_ids))
        for sid in npc_station_ids:
            if sid in sde_names:
                location_name_map[sid] = sde_names[sid]
            else:
                logging.warning(f"Station ID {sid} not found in SDE. Returning fallback name.")
                location_name_map[sid] = f"Unknown NPC Station ({sid})"
    if player_structure_ids and scan_config.get('access_token'):
        for struct_id in player_structure_ids:
            details = api.get_structure_details(struct_id, scan_config['access_token'])
            name = details.get('name')
            if name and not name.startswith('Utilgjengelig'):
                location_name_map[struct_id] = name
            else:
                logging.warning(f"Structure ID {struct_id} could not be resolved via ESI. Returning fallback name.")
                location_name_map[struct_id] = f"Unknown Structure ({struct_id})"

    system_security = db.get_all_system_security()
    item_volume_map = {item_id: db.get_item_volume(item_id) for item_id in profitable_candidates}
    
    all_verifiable_trades = []
    for item_id, buy_order in found_buy_orders.items():
        if item_id in found_sell_orders:
            sell_order = found_sell_orders[item_id]
            buy_loc_id = buy_order['location_id']
            sell_loc_id = sell_order['location_id']

            # Skip trades with missing or invalid location IDs
            if not buy_loc_id or not sell_loc_id or buy_loc_id == 0 or sell_loc_id == 0:
                logging.warning(f"Skipping trade for item {item_id} due to missing location IDs: buy_loc_id={buy_loc_id}, sell_loc_id={sell_loc_id}")
                continue
            
            buy_system_id = station_to_system_map.get(buy_loc_id)
            sell_system_id = station_to_system_map.get(sell_loc_id)

            # Determine location type
            buy_location_type = 'station' if buy_loc_id in npc_station_ids else 'structure'
            sell_location_type = 'station' if sell_loc_id in npc_station_ids else 'structure'

            # Fallback for strukturer
            if not buy_system_id and buy_loc_id in player_structure_ids:
                 pass
            if not sell_system_id and sell_loc_id in player_structure_ids:
                 pass

            # --- Logging for debugging station name resolution ---
            buy_station_name = location_name_map.get(buy_loc_id, f"Ukjent Stasjon/Struktur ({buy_loc_id})")
            sell_station_name = location_name_map.get(sell_loc_id, f"Ukjent Stasjon/Struktur ({sell_loc_id})")
            logging.info(f"Trade item_id={item_id}: buy_loc_id={buy_loc_id}, sell_loc_id={sell_loc_id}, buy_station_name='{buy_station_name}', sell_station_name='{sell_station_name}'")
            if buy_loc_id not in location_name_map:
                logging.warning(f"Buy location ID {buy_loc_id} not found in location_name_map for item {item_id}.")
            if sell_loc_id not in location_name_map:
                logging.warning(f"Sell location ID {sell_loc_id} not found in location_name_map for item {item_id}.")
            # ---------------------------------------------------

            if buy_system_id and sell_system_id:
                jumps = db.calculate_shortest_path(buy_system_id, sell_system_id)
                all_verifiable_trades.append({
                    'item_id': item_id, 'item_name': db.get_type_name_from_sde(item_id),
                    'item_m3': item_volume_map.get(item_id),
                    'buy_price': buy_order['price'], 'sell_price': sell_order['price'],
                    'buy_station_id': buy_loc_id,  # legacy
                    'sell_station_id': sell_loc_id,  # legacy
                    'buy_location_id': buy_loc_id,
                    'buy_location_type': buy_location_type,
                    'sell_location_id': sell_loc_id,
                    'sell_location_type': sell_location_type,
                    'buy_station_name': buy_station_name,
                    'sell_station_name': sell_station_name,
                    'buy_system_id': buy_system_id,
                    'sell_system_id': sell_system_id,
                    'sec_status': system_security.get(buy_system_id, 0.0),
                    'buy_volume': buy_order['volume_remain'], 'sell_volume': sell_order['volume_remain'],
                    'jumps': jumps
                })

    status_callback("Datainnhenting fullført.", 100)
    return all_verifiable_trades

def build_bundles_from_trades(all_trades, scan_config, status_callback):
    status_callback("Filtrerer handler...", 95)
    
    filtered_by_sec = [
        trade for trade in all_trades if ('sec_status' in trade) and (
           (trade['sec_status'] >= 0.5 and scan_config['include_hisec']) or
           (0.0 < trade['sec_status'] < 0.5 and scan_config['include_lowsec']) or
           (trade['sec_status'] <= 0.0 and scan_config['include_nullsec']))
    ]
    if not filtered_by_sec: return []

    profitable_items = []
    broker_rate = scan_config['brokers_fee_rate'] / 100.0; tax_rate = scan_config['sales_tax_rate'] / 100.0
    min_profit_per_item = scan_config.get('min_profit_per_item', 0)
    for trade in filtered_by_sec:
        trade['net_profit_per_unit'] = (trade['sell_price'] - trade['buy_price']) - ((trade['sell_price'] * tax_rate) + (trade['buy_price'] + trade['sell_price']) * broker_rate)
        trade['available_volume'] = min(trade['buy_volume'], trade['sell_volume'])
        total_item_profit = trade['net_profit_per_unit'] * trade['available_volume']
        if trade['net_profit_per_unit'] > 0 and trade.get('item_m3') and total_item_profit >= min_profit_per_item:
            profitable_items.append(trade)
    if not profitable_items: return []
    
    min_core_profit = scan_config.get('min_core_profit', 10000)  # Default 10,000 ISK
    core_trades = [t for t in profitable_items if t['net_profit_per_unit'] >= min_core_profit]
    candidate_trades = [t for t in profitable_items if t['net_profit_per_unit'] < min_core_profit]
    items_to_bundle = core_trades
    if scan_config['use_common_sell_station']:
        hub_potential = defaultdict(float)
        for item in core_trades:
            hub_potential[item['sell_station_name']] += item['net_profit_per_unit'] * item['available_volume']
        if hub_potential:
            best_common_hub = max(hub_potential.items(), key=lambda i: i[1])[0]
            items_to_bundle = [item for item in core_trades if item['sell_station_name'] == best_common_hub]
        else:
            items_to_bundle = []
    if not items_to_bundle:
        return []
    status_callback("Bygger handelspakker...", 98)
    bundles_to_build = []
    if scan_config['allow_multistation']:
        bundle = _create_optimal_bundle(items_to_bundle, scan_config['ship_cargo_m3'], scan_config['max_investment'])
        if bundle and bundle['items']:
            bundles_to_build.append(bundle)
    else:
        items_by_station = defaultdict(list)
        for item in items_to_bundle: items_by_station[item['buy_station_name']].append(item)
        for station_name, items in items_by_station.items():
            bundle = _create_optimal_bundle(items, scan_config['ship_cargo_m3'], scan_config['max_investment'], station_name)
            if bundle and bundle['items']:
                bundles_to_build.append(bundle)
    final_bundles = []
    for bundle in bundles_to_build:
        if bundle['total_profit'] < scan_config['min_profit_total']:
            continue
        buy_system_ids = list(set(item['buy_system_id'] for item in bundle['items']))
        sell_system_ids = list(set(item['sell_system_id'] for item in bundle['items']))
        start_system_id = None
        if scan_config.get('character_id') and scan_config.get('access_token'):
            start_system_id = api.get_character_current_system_id(scan_config['character_id'], scan_config['access_token'])
            if start_system_id and start_system_id not in buy_system_ids:
                buy_system_ids = [start_system_id] + buy_system_ids
        # --- Phase 1: Optimize buy route ---
        if len(buy_system_ids) > 1:
            status_callback(f"Planlegger optimal kjøpsrute...", 99)
            distance_matrix = db.get_distance_matrix(buy_system_ids)
            def nearest_neighbor(matrix, nodes, start):
                unvisited = set(nodes)
                route = [start]
                unvisited.remove(start)
                current = start
                while unvisited:
                    next_node = min(unvisited, key=lambda n: matrix[current][n])
                    route.append(next_node)
                    unvisited.remove(next_node)
                    current = next_node
                return route
            def two_opt(route, matrix):
                improved = True
                while improved:
                    improved = False
                    for i in range(1, len(route) - 2):
                        for j in range(i + 1, len(route)):
                            if j - i == 1: continue
                            new_route = route[:i] + route[i:j][::-1] + route[j:]
                            if route_length(new_route, matrix) < route_length(route, matrix):
                                route = new_route
                                improved = True
                return route
            def route_length(route, matrix):
                return sum(matrix[route[i]][route[i+1]] for i in range(len(route)-1))
            buy_start = start_system_id or buy_system_ids[0]
            buy_route = nearest_neighbor(distance_matrix, buy_system_ids, buy_start)
            buy_route = two_opt(buy_route, distance_matrix)
            bundle['buy_route_plan'] = buy_route
            bundle['buy_route_total_jumps'] = route_length(buy_route, distance_matrix)
        else:
            buy_route = buy_system_ids
        # --- Phase 2: Optimize sell route ---
        last_buy_system = buy_route[-1] if buy_route else (buy_system_ids[0] if buy_system_ids else None)
        if len(sell_system_ids) > 1 and last_buy_system:
            status_callback(f"Planlegger optimal salgsrute...", 99)
            all_sell_points = [last_buy_system] + [sid for sid in sell_system_ids if sid != last_buy_system]
            distance_matrix = db.get_distance_matrix(all_sell_points)
            sell_route = nearest_neighbor(distance_matrix, all_sell_points, last_buy_system)
            sell_route = two_opt(sell_route, distance_matrix)
            bundle['sell_route_plan'] = sell_route
            bundle['sell_route_total_jumps'] = route_length(sell_route, distance_matrix)
        else:
            sell_route = sell_system_ids
        # --- Concatenate for full route ---
        if buy_route and sell_route:
            full_route = list(buy_route)
            if sell_route and sell_route[0] == buy_route[-1]:
                full_route.extend(sell_route[1:])
            else:
                full_route.extend(sell_route)
            bundle['full_route_plan'] = full_route
            bundle['full_route_total_jumps'] = None
        else:
            bundle['full_route_plan'] = buy_route or sell_route
        # --- On-the-way logic for candidate trades ---
        route_systems = set(bundle['full_route_plan'])
        for trade in candidate_trades:
            fitted_qty = trade.get('fitted_quantity', trade.get('available_volume', 0))
            total_profit = trade.get('total_profit_for_item', 0)
            if (
                trade['buy_system_id'] in route_systems and
                trade['sell_system_id'] in route_systems and
                fitted_qty > 0 and
                trade.get('net_profit_per_unit', 0) > 0 and
                total_profit > 0
            ):
                bundle['items'].append(trade)
                bundle['trades'].append(trade)
        final_bundles.append(bundle)
    return sorted(final_bundles, key=lambda x: x['total_profit'], reverse=True)