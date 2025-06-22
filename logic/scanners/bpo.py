import time
import api
import config
import db
from logic import calculations
from .helpers import format_time

def run_bpo_scan(scan_config, progress_callback):
    """Kjører et komplett skan etter profitable blueprints å produsere."""
    try:
        me = int(scan_config.get('bpo_me'))
        te = int(scan_config.get('bpo_te'))
        min_profit_ph = float(scan_config.get('min_profit_ph'))
        min_daily_volume = float(scan_config.get('min_daily_volume'))
        production_system_name = scan_config.get('production_system')
        active_flag = scan_config.get('active_flag')
        scan_type = scan_config.get('scan_type')
        
        progress_callback({'scan_type': scan_type, 'status': 'Henter system-indekser...'})
        if not config.SYSTEM_INDICES_CACHE:
            api.fetch_industry_system_indices() 
        
        system_id = db.get_system_id_from_name(production_system_name)
        if not system_id or not config.SYSTEM_INDICES_CACHE.get(system_id):
            progress_callback({'scan_type': scan_type, 'error': f'Fant ikke industridata for {production_system_name}.'})
            return

        system_indices = config.SYSTEM_INDICES_CACHE.get(system_id)
        manufacturing_index = next((idx['cost_index'] for idx in system_indices.get('cost_indices', []) if idx['activity'] == 'manufacturing'), 0.05) 

        progress_callback({'scan_type': scan_type, 'status': 'Henter liste over alle blueprints...'})
        all_producible_items = db.get_all_manufacturable_item_ids()
        if not all_producible_items:
            progress_callback({'scan_type': scan_type, 'error': 'Kunne ikke hente blueprints fra databasen.'})
            return

        total_items = len(all_producible_items)
        progress_callback({'scan_type': scan_type, 'eta': f'Analyserer {total_items} blueprints...'})

        id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
        batch_size = 100
        start_time = time.time()

        for i in range(0, len(all_producible_items), batch_size):
            if not active_flag.is_set():
                progress_callback({'scan_type': scan_type, 'status': 'Skann avbrutt.'})
                return

            batch = all_producible_items[i:i+batch_size]
            elapsed = time.time() - start_time
            avg_time_per_item = elapsed / (i + 1) if i > 0 else 0
            eta = (total_items - (i + 1)) * avg_time_per_item if avg_time_per_item > 0 else None

            progress_callback({
                'scan_type': scan_type,
                'progress': (i + len(batch)) / total_items,
                'status': f'Sjekker batch {i//batch_size + 1}/{total_items//batch_size + 1}...',
                'eta': f"ETA: {format_time(eta)}"
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
                        if lowest_sell > 0: product_price = lowest_sell - 0.01
                    
                    if product_price == 0: raise KeyError

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

                except (KeyError, ValueError, TypeError):
                    continue
            time.sleep(0.5) 
        
        progress_callback({'scan_type': scan_type, 'status': 'Blueprint-skann fullført!'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        progress_callback({'scan_type': scan_type, 'error': f'Uventet feil under BPO-skann: {e}'})
