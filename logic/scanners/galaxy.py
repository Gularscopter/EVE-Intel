import time
from collections import defaultdict
import api
import config
import db
from .helpers import get_trend_indicator

def _create_optimal_bundle(items, cargo_capacity, max_investment):
    """
    Bruker en "grådig" algoritme for å lage den mest lønnsomme pakken med varer
    som passer innenfor gitte begrensninger for lasterom og investering.
    Prioriterer varer med høyest profitt per kubikkmeter (m3).
    """
    for item in items:
        # Beregn "profit density" - hvor mye profitt man får per m3
        item['profit_density'] = item['net_profit_per_unit'] / item['item_m3'] if item.get('item_m3', 0) > 0 else 0

    sorted_items = sorted(items, key=lambda x: x['profit_density'], reverse=True)
    
    bundle_items = []
    total_profit = 0
    remaining_cargo = cargo_capacity
    remaining_investment = max_investment
    
    for item in sorted_items:
        if remaining_cargo <= 0 or remaining_investment <= 0:
            break
        
        if item.get('buy_price', 0) <= 0 or item.get('item_m3', 0) <= 0:
            continue
            
        # Finn ut hvor mange enheter man har råd til og plass til
        units_affordable = remaining_investment // item['buy_price']
        units_that_fit = remaining_cargo // item['item_m3']
        
        # Det faktiske antallet er det minste av disse begrensningene
        units_to_take = int(min(units_that_fit, item['units_to_trade'], units_affordable))

        if units_to_take > 0:
            profit_from_this_item = units_to_take * item['net_profit_per_unit']
            cost_of_this_item = units_to_take * item['buy_price']

            bundle_items.append({
                'name': item['item'], 'units': units_to_take, 'profit': profit_from_this_item,
                'buy_price': item['buy_price'], 'sell_price': item['sell_price'],
                'buy_volume_available': item['buy_volume_available'],
                'sell_volume_available': item['sell_volume_available'],
                'daily_volume': item['daily_volume'], 'trend': item['trend'],
                'buy_station': item['buy_station'] 
            })
            
            total_profit += profit_from_this_item
            remaining_cargo -= units_to_take * item['item_m3']
            remaining_investment -= cost_of_this_item

    return {
        "is_bundle": True, "buy_station": items[0]['buy_station'] if items else 'N/A', 
        "total_profit": total_profit, "item_count": len(bundle_items), "items": bundle_items,
        "cargo_used_percentage": (1 - (remaining_cargo / cargo_capacity)) * 100 if cargo_capacity > 0 else 0
    }

def run_galaxy_scan(scan_config, all_type_ids, progress_callback):
    """Kjører import/eksport-skann og bygger optimale pakker."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    scan_type, active_flag = scan_config['scan_type'], scan_config['active_flag']
    home_base_info = config.STATIONS_INFO[scan_config['home_base']]
    target_region_id = config.ALL_REGIONS_CACHE.get(scan_config['target_region'])
    
    if not target_region_id: 
        progress_callback({'scan_type': scan_type, 'error': f"Finner ikke region: {scan_config['target_region']}"})
        return
    if scan_config.get('include_structures') and not scan_config.get('token'):
        progress_callback({'scan_type': scan_type, 'error': "Innlogging kreves for å inkludere strukturer."})
        return

    progress_callback({'scan_type': scan_type, 'status': "Henter system-sikkerhet..."})
    system_securities = db.get_all_system_security_statuses()
    if not system_securities:
        progress_callback({'scan_type': scan_type, 'error': "Kunne ikke laste system-data fra SDE."})
        return

    item_chunks = [all_type_ids[i:i + 200] for i in range(0, len(all_type_ids), 200)]
    progress_callback({'scan_type': scan_type, 'progress': 0.1, 'status': "Steg 1/4: Henter priser for hjemmebase..."})
    home_buy_orders = {}
    for i, chunk in enumerate(item_chunks):
        if not active_flag.is_set(): return
        progress_callback({'scan_type': scan_type, 'progress': 0.1 + ((i + 1) / len(item_chunks) * 0.15), 'status': f"Henter hjemmebase-priser (Gruppe {i+1}/{len(item_chunks)})"})
        data = api.fetch_fuzzwork_market_data(home_base_info['id'], chunk)
        for typeid_str, item_data in (data or {}).items():
            if item_data and item_data.get('buy') and item_data.get('buy').get('max'):
                home_buy_orders[int(typeid_str)] = {'price': float(item_data['buy']['max']), 'volume': float(item_data['buy'].get('volume', 0))}
        time.sleep(0.5)

    progress_callback({'scan_type': scan_type, 'progress': 0.25, 'status': f"Steg 2/4: Henter salgsordrer fra {scan_config['target_region']}..."})
    all_regional_sell_orders = api.fetch_all_pages(f"https://esi.evetech.net/latest/markets/{target_region_id}/orders/?datasource=tranquility&order_type=sell") or []
    if scan_config.get('include_structures'):
        structures_to_scan = [s for s in scan_config['settings'].get('user_structures', []) if s.get('region_id') == target_region_id]
        for i, s_info in enumerate(structures_to_scan):
            if not active_flag.is_set(): return
            progress_callback({'scan_type': scan_type, 'progress': 0.25 + (((i + 1) / len(structures_to_scan)) * 0.15), 'status': f"Skanner struktur {i+1}/{len(structures_to_scan)}: {s_info['name']}"})
            structure_orders = api.fetch_structure_market_orders(s_info['id'], scan_config['token'])
            if structure_orders: all_regional_sell_orders.extend([o for o in structure_orders if not o.get('is_buy_order')])
    
    if not all_regional_sell_orders: 
        progress_callback({'scan_type': scan_type, 'status': "Fant ingen salgsordrer i regionen."})
        return

    progress_callback({'scan_type': scan_type, 'progress': 0.4, 'status': f"Steg 3/4: Filtrerer {len(all_regional_sell_orders)} ordrer..."})
    filtered_orders = []
    for order in all_regional_sell_orders:
        sec_status = system_securities.get(order.get('system_id'))
        if sec_status is None: continue

        if (scan_config.get('include_hisec') and sec_status >= 0.5) or \
           (scan_config.get('include_lowsec') and 0.0 < sec_status < 0.5) or \
           (scan_config.get('include_nullsec') and sec_status <= 0.0):
            filtered_orders.append(order)
    
    if not filtered_orders:
        progress_callback({'scan_type': scan_type, 'status': "Ingen ordrer i valgte sikkerhetsnivåer."})
        return

    orders_by_type = defaultdict(list)
    for order in filtered_orders: orders_by_type[order['type_id']].append(order)
    
    progress_callback({'scan_type': scan_type, 'progress': 0.5, 'status': f"Steg 4/4: Analyserer {len(orders_by_type)} varer..."})
    profitable_items_by_station = defaultdict(list)
    all_profitable_items = []

    for i, type_id in enumerate(list(orders_by_type.keys())):
        if not active_flag.is_set(): return
        progress_callback({'scan_type': scan_type, 'progress': 0.5 + (((i + 1) / len(orders_by_type)) * 0.4), 'status': f"Analyserer marked i {scan_config['target_region']} ({i+1}/{len(orders_by_type)})"})
        
        home_order_info = home_buy_orders.get(type_id)
        if not home_order_info: continue
        
        best_buy_order = min(orders_by_type[type_id], key=lambda x: x['price'])
        buy_price = best_buy_order['price']
        net_sell_price = home_order_info['price'] * (1 - scan_config['sales_tax_rate'] / 100.0)
        
        if net_sell_price <= buy_price: continue
        
        type_attributes = api.fetch_type_attributes(type_id)
        if not type_attributes or type_attributes.get('volume', 0) <= 0: continue
        
        history = api.fetch_esi_history(home_base_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        
        net_profit_per_unit = net_sell_price - buy_price
        original_trade_limit = min(scan_config['max_investment'] / buy_price if buy_price > 0 else float('inf'), best_buy_order['volume_remain'])
        
        item_data = {
            'item': id_to_name.get(type_id, f"ID: {type_id}"), 'buy_station': api.get_station_name_with_cache(best_buy_order['location_id']),
            'buy_price': buy_price, 'sell_price': home_order_info['price'], 'net_profit_per_unit': net_profit_per_unit,
            'item_m3': type_attributes['volume'], 'units_to_trade': original_trade_limit, 'buy_volume_available': best_buy_order['volume_remain'],
            'sell_volume_available': home_order_info['volume'], 'daily_volume': avg_daily_vol, 'trend': get_trend_indicator(history)
        }

        if (original_trade_limit * net_profit_per_unit) > scan_config['min_profit']:
            if scan_config.get('allow_multistation'):
                all_profitable_items.append(item_data)
            else:
                profitable_items_by_station[item_data['buy_station']].append(item_data)

    progress_callback({'scan_type': scan_type, 'progress': 0.9, 'status': "Bygger optimale handelspakker..."})
    all_bundles = []

    if scan_config.get('allow_multistation'):
        if all_profitable_items:
            bundle = _create_optimal_bundle(all_profitable_items, scan_config['ship_cargo_m3'], scan_config['max_investment'])
            bundle['is_multistation'] = True
            if bundle['total_profit'] > scan_config['min_profit']:
                all_bundles.append(bundle)
    else:
        for station_name, items in profitable_items_by_station.items():
            if not active_flag.is_set(): return
            bundle = _create_optimal_bundle(items, scan_config['ship_cargo_m3'], scan_config['max_investment'])
            if bundle['total_profit'] > scan_config['min_profit']:
                all_bundles.append(bundle)
    
    sorted_bundles = sorted(all_bundles, key=lambda x: x['total_profit'], reverse=True)
    if not sorted_bundles: 
        progress_callback({'scan_type': scan_type, 'progress': 1.0, 'status': "Fullført. Fant ingen lønnsomme pakker."})
    
    for i, bundle in enumerate(sorted_bundles):
         progress_callback({'scan_type': scan_type, 'progress': 0.9 + (((i + 1) / len(sorted_bundles)) * 0.1) if sorted_bundles else 1.0, 'result': bundle, 'status': f"Fant pakke fra {bundle.get('buy_station', 'flere stasjoner')}"})

    progress_callback({'scan_type': scan_type, 'status': 'Galakse-skann fullført!'})
