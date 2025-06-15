# ==============================================================================
# EVE MARKET VERKTØY - SKANNER-LOGIKK
# ==============================================================================
import time
from collections import defaultdict
import heapq
import sqlite3 

import api
import config
import db
from . import calculations 


def _create_optimal_bundle(items, cargo_capacity, max_investment):
    for item in items:
        if item.get('item_m3', 0) > 0:
            item['profit_density'] = item['net_profit_per_unit'] / item['item_m3']
        else:
            item['profit_density'] = 0

    sorted_items = sorted(items, key=lambda x: x['profit_density'], reverse=True)
    bundle_items = []
    total_profit = 0
    remaining_cargo = cargo_capacity
    remaining_investment = max_investment
    
    for item in sorted_items:
        if remaining_cargo <= 0 or remaining_investment <= 0:
            break
        
        # Sjekk om 'buy_price' og 'item_m3' er gyldige for beregning
        if item['buy_price'] <= 0 or item['item_m3'] <= 0:
            continue
            
        units_affordable = remaining_investment // item['buy_price']
        units_that_fit = remaining_cargo // item['item_m3']
        
        units_to_take = int(min(
            units_that_fit, 
            item['units_to_trade'],
            units_affordable
        ))

        if units_to_take > 0:
            profit_from_this_item = units_to_take * item['net_profit_per_unit']
            cost_of_this_item = units_to_take * item['buy_price']

            # Legg til stasjonen varen kommer fra, for multi-stasjon pakker
            bundle_items.append({
                'name': item['item'], 'units': units_to_take, 'profit': profit_from_this_item,
                'buy_price': item['buy_price'], 'sell_price': item['sell_price'],
                'buy_volume_available': item['buy_volume_available'], 'sell_volume_available': item['sell_volume_available'],
                'daily_volume': item['daily_volume'], 'trend': item['trend'],
                'buy_station': item['buy_station'] 
            })
            
            total_profit += profit_from_this_item
            remaining_cargo -= units_to_take * item['item_m3']
            remaining_investment -= cost_of_this_item

    return {
        "is_bundle": True, "buy_station": items[0]['buy_station'] if items else 'N/A', "total_profit": total_profit,
        "item_count": len(bundle_items), "items": bundle_items,
        "cargo_used_percentage": (1 - (remaining_cargo / cargo_capacity)) * 100 if cargo_capacity > 0 else 0
    }

def _format_time(seconds):
    if seconds is None or seconds < 0: return ""
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"

def _get_active_items_from_jita(progress_callback, active_flag, scan_type):
    all_type_ids_master = list(config.ITEM_NAME_TO_ID.values())
    initial_item_chunks = [all_type_ids_master[i:i + 200] for i in range(0, len(all_type_ids_master), 200)]
    
    PREFILTER_MIN_ISK_VOLUME = 100_000_000
    PREFILTER_MAX_SPREAD_PERCENT = 40.0
    PREFILTER_MIN_ORDER_COUNT = 5

    progress_callback({'scan_type': scan_type, 'progress': 0, 'status': "Forhåndsfilter: Finner aktive varer i Jita..."})
    jita_station_id = config.STATIONS_INFO['Jita']['id']
    active_items = set()
    
    for i, chunk in enumerate(initial_item_chunks):
        if not active_flag.is_set(): return None
        progress_callback({'scan_type': scan_type, 'progress': (i + 1) / len(initial_item_chunks) * 0.1, 'status': f"Forhåndsfilter: Analyserer Jita-markedet (Gruppe {i+1}/{len(initial_item_chunks)})"})
        jita_market_data = api.fetch_fuzzwork_market_data(jita_station_id, chunk)
        
        for type_id_str, item_data in jita_market_data.items():
            buy_info, sell_info = item_data.get('buy', {}), item_data.get('sell', {})
            if not buy_info or not sell_info: continue
            highest_buy_price, buy_volume = float(buy_info.get('max', 0)), float(buy_info.get('volume', 0))
            buy_order_count, lowest_sell_price = int(buy_info.get('orderCount', 0)), float(sell_info.get('min', 0))
            sell_order_count = int(sell_info.get('orderCount', 0))
            if highest_buy_price > 0 and lowest_sell_price > 0:
                total_buy_value, price_spread_percent = highest_buy_price * buy_volume, ((lowest_sell_price - highest_buy_price) / lowest_sell_price) * 100
                if (total_buy_value >= PREFILTER_MIN_ISK_VOLUME and price_spread_percent < PREFILTER_MAX_SPREAD_PERCENT and
                    buy_order_count >= PREFILTER_MIN_ORDER_COUNT and sell_order_count >= PREFILTER_MIN_ORDER_COUNT):
                    active_items.add(int(type_id_str))
        time.sleep(0.5)

    if not active_items:
        progress_callback({'scan_type': scan_type, 'error': "Kunne ikke finne noen varer på Jita som møtte de smarte filtrene."})
        return None
    
    status_update = f"Forhåndsfilter fullført. Reduserte varesøk fra {len(all_type_ids_master)} til {len(active_items)}."
    progress_callback({'scan_type': scan_type, 'progress': 0.1, 'status': status_update}); time.sleep(2)
    return list(active_items)

def _get_trend_indicator(history):
    if not history or len(history) < 10: return "—"
    try:
        recent_avg = sum(h['average'] for h in history[-3:]) / 3
        older_avg = sum(h['average'] for h in history[-10:-3]) / 7
        if older_avg > 0:
            price_change_pct = ((recent_avg - older_avg) / older_avg) * 100
            if price_change_pct > 1.5: return "↑"
            if price_change_pct < -1.5: return "↓"
    except (ZeroDivisionError, IndexError): pass
    return "—"

def run_bpo_scan(scan_config, progress_callback):
    """
    Kjører et komplett skan etter profitable blueprints å produsere.
    """
    try:
        me = int(scan_config.get('bpo_me'))
        te = int(scan_config.get('bpo_te'))
        min_profit_ph = float(scan_config.get('min_profit_ph'))
        min_daily_volume = float(scan_config.get('min_daily_volume')) # NYTT
        production_system_name = scan_config.get('production_system')
        active_flag = scan_config.get('active_flag')
        scan_type = scan_config.get('scan_type')
        
        progress_callback({'scan_type': scan_type, 'status': 'Henter system-indekser...'})
        api.fetch_industry_system_indices() 
        system_id = db.get_system_id_from_name(production_system_name)
        if not system_id or not config.SYSTEM_INDICES_CACHE.get(system_id):
            progress_callback({'scan_type': scan_type, 'error': f'Fant ikke gyldige industridata for systemet {production_system_name}.'})
            return

        system_indices = config.SYSTEM_INDICES_CACHE.get(system_id)
        manufacturing_index = next((idx['cost_index'] for idx in system_indices.get('cost_indices', []) if idx['activity'] == 'manufacturing'), 0.05) 

        progress_callback({'scan_type': scan_type, 'status': 'Henter liste over alle blueprints...'})
        all_producible_items = db.get_all_manufacturable_item_ids()
        if not all_producible_items:
            progress_callback({'scan_type': scan_type, 'error': 'Kunne ikke hente liste over blueprints fra SDE.'})
            return

        total_items = len(all_producible_items)
        progress_callback({'scan_type': scan_type, 'eta': f'Analyserer {total_items} blueprints...'})

        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        batch_size = 100
        start_time = time.time()

        for i in range(0, len(all_producible_items), batch_size):
            if not active_flag.is_set():
                progress_callback({'scan_type': scan_type, 'status': 'Skann avbrutt av bruker.'})
                return

            batch = all_producible_items[i:i+batch_size]
            elapsed = time.time() - start_time
            avg_time_per_item = elapsed / (i + 1) if i > 0 else 0
            eta = (total_items - (i + 1)) * avg_time_per_item if avg_time_per_item > 0 else None

            progress_callback({
                'scan_type': scan_type,
                'progress': (i + len(batch)) / total_items,
                'status': f'Sjekker batch {i//batch_size + 1} / {total_items//batch_size + 1}...',
                'eta': f"ETA: {_format_time(eta)}"
            })

            ids_to_price = set()
            bpos_in_batch = {}
            for product_id, bpo_id in batch:
                bp_data = db.get_blueprint_from_sde(product_id)
                if not bp_data: continue
                
                bpos_in_batch[bpo_id] = bp_data
                ids_to_price.add(product_id)
                ids_to_price.add(bpo_id)
                for mat in bp_data['activities']['manufacturing']['materials']:
                    ids_to_price.add(mat['typeID'])
            
            price_data = api.fetch_fuzzwork_market_data(config.STATIONS_INFO['Jita']['id'], list(ids_to_price))
            
            for product_id, bpo_id in batch:
                bp_data = bpos_in_batch.get(bpo_id)
                if not bp_data: continue

                try:
                    product_type_id_str = str(bp_data['activities']['manufacturing']['products'][0]['typeID'])
                    product_market_info = price_data.get(product_type_id_str, {})
                    
                    product_buy_volume = float(product_market_info.get('buy', {}).get('volume', 0))
                    if product_buy_volume < min_daily_volume:
                        continue

                    materials = bp_data['activities']['manufacturing']['materials']
                    material_prices = {m['typeID']: float(price_data[str(m['typeID'])]['sell']['min']) for m in materials}
                    
                    product_price = float(product_market_info.get('buy', {}).get('max', 0))
                    
                    if product_price == 0:
                        lowest_sell = float(product_market_info.get('sell', {}).get('min', 0))
                        if lowest_sell > 0:
                            product_price = lowest_sell - 0.01
                    
                    if product_price == 0:
                        raise KeyError

                    bpo_price = float(price_data.get(str(bpo_id), {}).get('sell', {}).get('min', 0))

                    results = calculations.calculate_manufacturing_profit(
                        bp_data, material_prices, product_price, manufacturing_index,
                        me, te, float(scan_config['sales_tax_rate']), float(scan_config['brokers_fee_rate'])
                    )

                    if 'error' in results: continue

                    if results['profit_per_hour'] >= min_profit_ph:
                        ui_result = {
                            'bpo': id_to_name.get(bpo_id, f'ID: {bpo_id}'),
                            'product': id_to_name.get(product_id, f'ID: {product_id}'),
                            'profit_ph': results['profit_per_hour'],
                            'profit_run': results['net_profit_per_run'],
                            'cost': results['total_cost_per_run'],
                            'bpo_price': bpo_price,
                        }
                        progress_callback({'result': ui_result, 'scan_type': 'bpo_scanner'})

                except KeyError:
                    continue
                except (ValueError, TypeError):
                    continue
            time.sleep(0.5) 
        
        progress_callback({'scan_type': scan_type, 'status': 'Blueprint-skann fullført!'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        progress_callback({'scan_type': scan_type, 'error': f'En uventet feil oppstod under BPO-skann: {e}'})

def run_scan_thread(scan_config, progress_callback):
    """Hovedfunksjon som delegerer til riktig skanner basert på konfigurasjon."""
    scan_type = scan_config['scan_type']
    active_flag = scan_config['active_flag']

    if scan_type == 'price_hunter':
        run_price_hunter_scan(scan_config, progress_callback)
        return
        
    if scan_type == 'bpo_scanner':
        run_bpo_scan(scan_config, progress_callback)
        return
    else:
        item_ids = _get_active_items_from_jita(progress_callback, active_flag, scan_type)
        if item_ids is None: return

    if scan_type == 'galaxy': _run_galaxy_scan(scan_config, item_ids, progress_callback)
    elif scan_type == 'region_trading': _run_region_trading_scan(scan_config, item_ids, progress_callback)
    elif scan_type in ['station', 'arbitrage']: _run_route_scan(scan_config, item_ids, progress_callback)

def run_price_hunter_scan(scan_config, progress_callback):
    """Scanner alle regioner for den billigste salgsordren av en vare, med sikkerhetsfilter."""
    active_flag = scan_config['active_flag']
    scan_type = scan_config['scan_type']
    type_id = scan_config['type_id']
    item_name = scan_config['item_name']

    progress_callback({'scan_type': scan_type, 'progress': 0, 'status': "Henter system-sikkerhet fra lokal database..."})
    system_securities = db.get_all_system_security_statuses()
    if not system_securities:
        progress_callback({'scan_type': scan_type, 'error': "Kunne ikke laste system-data fra SDE-databasen."})
        return

    security_map = {}
    if scan_config['include_hisec']:
        for sys_id, sec in system_securities.items():
            if sec >= 0.5: security_map[sys_id] = "High"
    if scan_config['include_lowsec']:
        for sys_id, sec in system_securities.items():
            if 0.0 < sec < 0.5: security_map[sys_id] = "Low"
    if scan_config['include_nullsec']:
         for sys_id, sec in system_securities.items():
            if sec <= 0.0: security_map[sys_id] = "Null"
    
    if not config.ALL_REGIONS_CACHE: api.populate_all_regions_cache()
    all_regions = [rid for rid in config.ALL_REGIONS_CACHE.values() if str(rid).startswith("10")]
    total_regions = len(all_regions)
    cheapest_orders = []
    
    for i, region_id in enumerate(all_regions):
        if not active_flag.is_set(): return
        
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
                
                order_tuple = (-price, order['order_id'], order)

                if len(cheapest_orders) < 20:
                    heapq.heappush(cheapest_orders, order_tuple)
                elif price < -cheapest_orders[0][0]:
                    heapq.heapreplace(cheapest_orders, order_tuple)

    if not cheapest_orders:
        progress_callback({'scan_type': scan_type, 'error': f"Fant ingen salgsordrer for '{item_name}' i de valgte sikkerhetsnivåene."})
        return
        
    final_results = sorted([item[2] for item in cheapest_orders], key=lambda x: x['price'])

    for order in final_results:
        result = {
            'item_name': item_name, 'price': order['price'], 'quantity': order['volume_remain'],
            'location_name': api.get_station_name_with_cache(order['location_id']),
            'system_name': db.get_system_name_from_sde(order['system_id']),
            'security': security_map.get(order['system_id'], "N/A")
        }
        progress_callback({'scan_type': scan_type, 'result': result})

def _run_route_scan(scan_config, all_type_ids, progress_callback):
    """Kjører ruteskann (stasjon til stasjon)."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    scan_type = scan_config['scan_type']
    active_flag = scan_config['active_flag']
    base_progress = 0.1
    item_chunks = [all_type_ids[i:i + 200] for i in range(0, len(all_type_ids), 200)]
    buy_info, sell_info = config.STATIONS_INFO[scan_config['buy_station']], config.STATIONS_INFO[scan_config['sell_station']]
    progress_callback({'scan_type': scan_type, 'progress': base_progress, 'status': "Steg 1: Henter priser fra Fuzzwork..."})
    buy_prices_map, sell_prices_map = {}, {}
    for i, chunk in enumerate(item_chunks):
        if not active_flag.is_set(): return
        progress = base_progress + (i / len(item_chunks) * 0.4)
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Henter pris-gruppe {i+1}/{len(item_chunks)}..."})
        buy_data = api.fetch_fuzzwork_market_data(buy_info['id'], chunk)
        sell_data = api.fetch_fuzzwork_market_data(sell_info['id'], chunk)
        for typeid_str, data in (buy_data or {}).items(): buy_prices_map[int(typeid_str)] = data
        for typeid_str, data in (sell_data or {}).items(): sell_prices_map[int(typeid_str)] = data
        time.sleep(0.5)
    progress_callback({'scan_type': scan_type, 'progress': 0.5, 'status': "Steg 2: Finner kandidater..."})
    candidates = []
    for type_id in all_type_ids:
        buy_item, sell_item = buy_prices_map.get(type_id), sell_prices_map.get(type_id)
        if not buy_item or not sell_item or not buy_item.get('sell') or not sell_item.get('buy'): continue
        buy_price = float(buy_item['sell']['min'])
        sell_price = float(sell_item['buy']['max'] if scan_type == 'station' else sell_item['sell']['min'])
        if buy_price > 0 and sell_price > buy_price: candidates.append(type_id)
    total_candidates, start_time = len(candidates), time.time()
    for i, type_id in enumerate(candidates):
        if not active_flag.is_set(): break
        item_name = id_to_name.get(type_id, str(type_id))
        progress = 0.5 + ((i + 1) / total_candidates * 0.5) if total_candidates > 0 else 1
        elapsed, avg_time = time.time() - start_time, (time.time() - start_time) / (i + 1) if i > 0 else 0
        eta = (total_candidates - (i + 1)) * avg_time if avg_time > 0 else None
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Sjekker finalist {i+1}/{total_candidates}: {item_name}", 'eta': f"ETA: {_format_time(eta)}"})
        history = api.fetch_esi_history(sell_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        trend = _get_trend_indicator(history)
        buy_orders_data, sell_orders_data = api.fetch_market_orders(buy_info['region_id'], type_id), api.fetch_market_orders(sell_info['region_id'], type_id)
        buy_order = min((o for o in (buy_orders_data or []) if o['location_id'] == buy_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)
        if scan_type == 'station': sell_order = max((o for o in (sell_orders_data or []) if o['location_id'] == sell_info['id'] and o['is_buy_order']), key=lambda x: x['price'], default=None)
        else: sell_order = min((o for o in (sell_orders_data or []) if o['location_id'] == sell_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)
        if not buy_order or not sell_order: continue
        buy_price, buy_volume_available = buy_order['price'], buy_order['volume_remain']
        if scan_type == 'station':
            sell_price, sell_volume_available = sell_order['price'], sell_order['volume_remain']
            net_sell_price = sell_price * (1 - scan_config['sales_tax_rate'] / 100.0)
        else:
            sell_price, sell_volume_available = sell_order['price'] - 0.01, sell_order['volume_remain']
            net_sell_price = sell_price * (1 - (scan_config['sales_tax_rate'] + scan_config['brokers_fee_rate']) / 100.0)
        if buy_price <= 0 or net_sell_price <= buy_price: continue
        profit_margin = ((net_sell_price - buy_price) / buy_price) * 100
        type_attributes = api.fetch_type_attributes(type_id)
        if not type_attributes or 'volume' not in type_attributes: continue
        item_m3 = type_attributes.get('volume', 0)
        if item_m3 <= 0: continue
        units_affordable, units_in_cargo = scan_config['max_investment'] / buy_price, scan_config['ship_cargo_m3'] / item_m3
        trade_limit = min(units_in_cargo, buy_volume_available, sell_volume_available, units_affordable)
        total_profit = trade_limit * (net_sell_price - buy_price)
        if total_profit >= scan_config['min_profit']:
            result = {'item': item_name, 'profit_per_trip': total_profit, 'profit_margin': profit_margin, 'units_to_trade': trade_limit,
                      'daily_volume': avg_daily_vol, 'buy_price': buy_price, 'sell_price': sell_price,
                      'buy_volume_available': buy_volume_available, 'sell_volume_available': sell_volume_available, 'trend': trend}
            progress_callback({'scan_type': scan_type, 'result': result})
        time.sleep(0.1)

def _run_region_trading_scan(scan_config, all_type_ids, progress_callback):
    """Kjører 'flipping'-skann innad på én stasjon."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    scan_type, active_flag = scan_config['scan_type'], scan_config['active_flag']
    base_progress = 0.1
    station_info = config.STATIONS_INFO[scan_config['station']]
    item_chunks = [all_type_ids[i:i + 200] for i in range(0, len(all_type_ids), 200)]
    progress_callback({'scan_type': scan_type, 'progress': base_progress, 'status': f"Steg 1: Henter priser for {scan_config['station']}..."})
    prices_map = {}
    for i, chunk in enumerate(item_chunks):
        if not active_flag.is_set(): return
        progress = base_progress + (i / len(item_chunks) * 0.4)
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Henter pris-gruppe {i+1}/{len(item_chunks)}..."})
        data = api.fetch_fuzzwork_market_data(station_info['id'], chunk)
        for typeid_str, item_data in (data or {}).items(): prices_map[int(typeid_str)] = item_data
        time.sleep(0.5)
    progress_callback({'scan_type': scan_type, 'progress': 0.5, 'status': "Steg 2: Finner kandidater..."})
    candidates = []
    for type_id in all_type_ids:
        item_data = prices_map.get(type_id)
        if not item_data or not item_data.get('buy') or not item_data.get('sell'): continue
        if float(item_data['buy']['max']) > 0 and float(item_data['sell']['min']) > float(item_data['buy']['max']):
            candidates.append(type_id)
    total_candidates, start_time = len(candidates), time.time()
    for i, type_id in enumerate(candidates):
        if not active_flag.is_set(): break
        item_name = id_to_name.get(type_id, str(type_id))
        progress = 0.5 + ((i + 1) / total_candidates * 0.5) if total_candidates > 0 else 1
        eta = (total_candidates - (i + 1)) * ((time.time() - start_time) / (i + 1)) if i > 0 else None
        progress_callback({'scan_type': scan_type, 'progress': progress, 'status': f"Sjekker finalist {i+1}/{total_candidates}: {item_name}", 'eta': f"ETA: {_format_time(eta)}"})
        history = api.fetch_esi_history(station_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        trend = _get_trend_indicator(history)
        orders_data = api.fetch_market_orders(station_info['region_id'], type_id)
        if not orders_data: continue
        highest_buy = max((o for o in orders_data if o['location_id'] == station_info['id'] and o['is_buy_order']), key=lambda x: x['price'], default=None)
        lowest_sell = min((o for o in orders_data if o['location_id'] == station_info['id'] and not o['is_buy_order']), key=lambda x: x['price'], default=None)
        if not highest_buy or not lowest_sell: continue
        comp_buy = sum(1 for o in orders_data if o['location_id'] == station_info['id'] and o['is_buy_order'] and o['price'] >= highest_buy['price'] * 0.999)
        comp_sell = sum(1 for o in orders_data if o['location_id'] == station_info['id'] and not o['is_buy_order'] and o['price'] <= lowest_sell['price'] * 1.001)
        buy_price, sell_price = highest_buy['price'] + 0.01, lowest_sell['price'] - 0.01
        if buy_price >= sell_price: continue
        fees = (buy_price * (scan_config['brokers_fee_rate'] / 100)) + (sell_price * (scan_config['brokers_fee_rate'] / 100)) + (sell_price * (scan_config['sales_tax_rate'] / 100))
        net_profit = (sell_price - buy_price) - fees
        if net_profit < scan_config['min_profit'] or buy_price > scan_config['max_investment']: continue
        result = {'item': item_name, 'profit_per_unit': net_profit, 'profit_margin': (net_profit / buy_price) * 100 if buy_price > 0 else 0,
                  'daily_volume': avg_daily_vol, 'buy_price': buy_price, 'sell_price': sell_price, 'trend': trend, 'competition': comp_buy + comp_sell}
        progress_callback({'scan_type': scan_type, 'result': result})

def _run_galaxy_scan(scan_config, all_type_ids, progress_callback):
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
        progress_callback({'scan_type': scan_type, 'error': "Fant ingen salgsordrer i regionen."})
        return

    progress_callback({'scan_type': scan_type, 'progress': 0.4, 'status': f"Steg 3/4: Filtrerer {len(all_regional_sell_orders)} ordrer på sikkerhet..."})
    filtered_orders = []
    for order in all_regional_sell_orders:
        sec_status = system_securities.get(order.get('system_id'))
        if sec_status is None: continue

        if scan_config.get('include_hisec') and sec_status >= 0.5:
            filtered_orders.append(order)
        elif scan_config.get('include_lowsec') and 0.0 < sec_status < 0.5:
            filtered_orders.append(order)
        elif scan_config.get('include_nullsec') and sec_status <= 0.0:
            filtered_orders.append(order)
    
    if not filtered_orders:
        progress_callback({'scan_type': scan_type, 'error': "Fant ingen salgsordrer i valgte sikkerhetsnivåer."})
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
        if not type_attributes or 'volume' not in type_attributes or type_attributes.get('volume', 0) <= 0: continue
        history = api.fetch_esi_history(home_base_info['region_id'], type_id)
        avg_daily_vol = sum(h['volume'] for h in history[-7:]) / 7 if history and len(history) >= 7 else 0
        if avg_daily_vol < scan_config['min_volume']: continue
        net_profit_per_unit = net_sell_price - buy_price
        original_trade_limit = min(scan_config['max_investment'] / buy_price if buy_price > 0 else float('inf'), best_buy_order['volume_remain'])
        
        item_data = {
            'item': id_to_name.get(type_id), 'buy_station': api.get_station_name_with_cache(best_buy_order['location_id']),
            'buy_price': buy_price, 'sell_price': home_order_info['price'], 'net_profit_per_unit': net_profit_per_unit,
            'item_m3': type_attributes['volume'], 'units_to_trade': original_trade_limit, 'buy_volume_available': best_buy_order['volume_remain'],
            'sell_volume_available': home_order_info['volume'], 'daily_volume': avg_daily_vol, 'trend': _get_trend_indicator(history)
        }

        if (original_trade_limit * net_profit_per_unit) > 50000:
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
        progress_callback({'scan_type': scan_type, 'progress': 1.0, 'status': "Fullført. Fant ingen lønnsomme handelspakker."})
    
    for i, bundle in enumerate(sorted_bundles):
         progress_callback({'scan_type': scan_type, 'progress': 0.9 + (((i + 1) / len(sorted_bundles)) * 0.1) if sorted_bundles else 1.0, 'result': bundle, 'status': f"Fant pakke fra {bundle.get('buy_station', 'flere stasjoner')}"})