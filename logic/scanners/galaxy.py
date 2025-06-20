import logging
from collections import defaultdict
import api
import db
from logic.route_planner import find_shortest_path

def _create_optimal_bundle(items, cargo_capacity, max_investment, station_name="Multi-Stasjon"):
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
                'name': item['item_name'], 'quantity': num_to_buy, 'buy_price': buy_price,
                'sell_price': item['sell_price'], 'profit_per_unit': item['net_profit_per_unit'],
                'total_profit_for_item': item_profit,
                'buy_station_name': item.get('buy_station_name', 'Ukjent'),
                'sell_station_name': item.get('sell_station_name', 'Ukjent'),
                'buy_system_id': item.get('buy_system_id'),
                'sell_system_id': item.get('sell_system_id'),
                'volume_str': f"{item.get('buy_volume'):,} / {item.get('sell_volume'):,}",
                'jumps': item.get('jumps') 
            }
            bundle_items.append(item_data)
            
            total_profit += item_profit; total_investment += item_cost; total_volume += item_volume
            remaining_cargo -= item_volume; remaining_investment -= item_cost
            
    return {
        'items': bundle_items, 'total_profit': total_profit, 'total_investment': total_investment,
        'total_volume': total_volume, 'station_name': station_name
    }

def run_galaxy_scan(scan_config, status_callback):
    status_callback("Forbereder...", 0)
    buy_region_id = api.resolve_name_to_id(scan_config['buy_region'], 'region')
    sell_region_id = api.resolve_name_to_id(scan_config['sell_region'], 'region')
    if not buy_region_id or not sell_region_id: raise ValueError("Kunne ikke finne region-ID.")

    all_type_ids = db.get_filtered_item_ids()
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
        location_name_map.update(db.get_station_names(list(npc_station_ids)))
    if player_structure_ids and scan_config.get('access_token'):
        for struct_id in player_structure_ids:
            details = api.get_structure_details(struct_id, scan_config['access_token'])
            location_name_map[struct_id] = details.get('name', f"Struktur ID: {struct_id}")

    system_security = db.get_all_system_security()
    item_volume_map = {item_id: db.get_item_volume(item_id) for item_id in profitable_candidates}
    
    all_verifiable_trades = []
    for item_id, buy_order in found_buy_orders.items():
        if item_id in found_sell_orders:
            sell_order = found_sell_orders[item_id]
            buy_loc_id = buy_order['location_id']
            sell_loc_id = sell_order['location_id']
            
            buy_system_id = station_to_system_map.get(buy_loc_id)
            sell_system_id = station_to_system_map.get(sell_loc_id)

            # Fallback for strukturer
            if not buy_system_id and buy_loc_id in player_structure_ids:
                 # Dette krever en forbedring i hvordan vi henter system_id for strukturer
                 # For nå, hopper vi over hvis vi ikke finner det lett
                 pass
            if not sell_system_id and sell_loc_id in player_structure_ids:
                 pass
            
            if buy_system_id and sell_system_id:
                jumps = db.calculate_shortest_path(buy_system_id, sell_system_id)
                all_verifiable_trades.append({
                    'item_id': item_id, 'item_name': db.get_type_name_from_sde(item_id),
                    'item_m3': item_volume_map.get(item_id),
                    'buy_price': buy_order['price'], 'sell_price': sell_order['price'],
                    'buy_station_name': location_name_map.get(buy_loc_id, f"Ukjent ({buy_loc_id})"),
                    'sell_station_name': location_name_map.get(sell_loc_id, f"Ukjent ({sell_loc_id})"),
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
    
    items_to_bundle = profitable_items
    if scan_config['use_common_sell_station']:
        hub_potential = defaultdict(float)
        for item in profitable_items: hub_potential[item['sell_station_name']] += item['net_profit_per_unit'] * item['available_volume']
        if hub_potential:
            best_common_hub = max(hub_potential, key=hub_potential.get)
            items_to_bundle = [item for item in profitable_items if item['sell_station_name'] == best_common_hub]
    if not items_to_bundle: return []

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
        
        if len(buy_system_ids) > 1 and scan_config.get('character_id') and scan_config.get('access_token'):
            status_callback(f"Planlegger optimal kjøpsrute...", 99)
            start_system_id = api.get_character_current_system_id(scan_config['character_id'], scan_config['access_token'])
            
            if start_system_id:
                all_buy_points = list(set([start_system_id] + buy_system_ids))
                if len(all_buy_points) > 1:
                    distance_matrix = db.get_distance_matrix(all_buy_points)
                    route, total_jumps = find_shortest_path(distance_matrix, start_system_id, buy_system_ids)
                    if route:
                        bundle['buy_route_plan'] = route
                        bundle['buy_route_total_jumps'] = total_jumps

        sell_system_ids = list(set(item['sell_system_id'] for item in bundle['items']))
        last_buy_system = bundle.get('buy_route_plan', [None])[-1] or (buy_system_ids[0] if buy_system_ids else None)
        
        if len(sell_system_ids) > 1 and last_buy_system:
            status_callback(f"Planlegger optimal salgsrute...", 99)
            all_sell_points = list(set([last_buy_system] + sell_system_ids))
            if len(all_sell_points) > 1:
                distance_matrix = db.get_distance_matrix(all_sell_points)
                route, total_jumps = find_shortest_path(distance_matrix, last_buy_system, sell_system_ids)
                if route:
                    bundle['sell_route_plan'] = route
                    bundle['sell_route_total_jumps'] = total_jumps

        if 'buy_route_plan' in bundle:
            full_route = list(bundle['buy_route_plan'])
            if 'sell_route_plan' in bundle:
                full_route.extend(bundle['sell_route_plan'][1:])
            bundle['full_route_plan'] = full_route
        elif len(buy_system_ids) == 1 and 'sell_route_plan' in bundle:
             # Håndterer tilfellet med ett kjøpssystem og flere salgssystemer
             full_route = [buy_system_ids[0]] + bundle['sell_route_plan']
             bundle['full_route_plan'] = list(dict.fromkeys(full_route)) # Fjerner duplikater

        final_bundles.append(bundle)

    return sorted(final_bundles, key=lambda x: x['total_profit'], reverse=True)