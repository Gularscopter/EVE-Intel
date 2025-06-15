# ==============================================================================
# EVE MARKET VERKTØY - BEREGNINGS-MODUL
# ==============================================================================
import api
import config
import math # NY IMPORT

def get_single_item_analysis(analysis_config):
    """Utfører en komplett analyse for én vare mellom to stasjoner."""
    try:
        # --- 1. Hent ID-er og basisinformasjon ---
        item_name = analysis_config['item_name']
        type_id = config.ITEM_LOOKUP_LOWERCASE.get(item_name.lower())
        if not type_id:
            return {'error': f"Fant ikke varen '{item_name}'."}

        buy_station_info = config.STATIONS_INFO[analysis_config['buy_station']]
        sell_station_info = config.STATIONS_INFO[analysis_config['sell_station']]

        # --- 2. Hent markedsordrer ---
        buy_orders_data = api.fetch_market_orders(buy_station_info['region_id'], type_id)
        # Hvis salgs- og kjøpsstasjon er i samme region, trenger vi ikke hente to ganger
        if buy_station_info['region_id'] == sell_station_info['region_id']:
            sell_orders_data = buy_orders_data
        else:
            sell_orders_data = api.fetch_market_orders(sell_station_info['region_id'], type_id)

        if not buy_orders_data or not sell_orders_data:
            return {'error': "Kunne ikke hente markedsordrer for en av regionene."}

        # --- 3. Finn Kjøpspris (alltid den billigste salgsordren) ---
        station_sell_orders = [o for o in buy_orders_data if not o['is_buy_order'] and o['location_id'] == buy_station_info['id']]
        if not station_sell_orders:
            return {'error': f"Ingen salgsordrer for '{item_name}' i {buy_station_info['name']}."}
        
        best_buy_order = min(station_sell_orders, key=lambda x: x['price'])
        buy_price = best_buy_order['price']
        buy_volume = best_buy_order['volume_remain']

        # --- 4. Finn Salgspris (avhenger av metode) ---
        sell_method = analysis_config['sell_method']
        sell_price = 0
        sell_volume = 0
        
        if sell_method == "Kjøpsordre":
            station_buy_orders = [o for o in sell_orders_data if o['is_buy_order'] and o['location_id'] == sell_station_info['id']]
            if not station_buy_orders:
                return {'error': f"Ingen kjøpsordrer for '{item_name}' i {sell_station_info['name']}."}
            best_sell_order = max(station_buy_orders, key=lambda x: x['price'])
            sell_price = best_sell_order['price']
            sell_volume = best_sell_order['volume_remain']
        else: # "Salgsordre"
            station_sell_orders_at_dest = [o for o in sell_orders_data if not o['is_buy_order'] and o['location_id'] == sell_station_info['id']]
            if not station_sell_orders_at_dest:
                 return {'error': f"Ingen salgsordrer å konkurrere med for '{item_name}' i {sell_station_info['name']}."}
            lowest_sell_order = min(station_sell_orders_at_dest, key=lambda x: x['price'])
            # Vi underbyr med 0.01 ISK
            sell_price = lowest_sell_order['price'] - 0.01
            sell_volume = float('inf') # Vi antar at markedet kan absorbere vårt salg

        # --- 5. Beregn avgifter og profitt ---
        sales_tax_rate = analysis_config['sales_tax_rate'] / 100.0
        brokers_fee_rate = analysis_config['brokers_fee_rate'] / 100.0

        transaction_cost = 0
        if sell_method == "Kjøpsordre":
            transaction_cost = sell_price * sales_tax_rate
        else: # "Salgsordre"
            transaction_cost = (sell_price * brokers_fee_rate) + (sell_price * sales_tax_rate)

        net_profit_per_unit = (sell_price - buy_price) - transaction_cost

        # --- 6. Beregn antall per tur og total profitt ---
        type_attributes = api.fetch_type_attributes(type_id)
        item_m3 = type_attributes.get('volume', 1)
        if item_m3 <= 0: item_m3 = 1 # Unngå divisjon med null

        units_in_cargo = analysis_config['ship_cargo_m3'] / item_m3
        units_per_trip = int(min(units_in_cargo, buy_volume, sell_volume))
        total_profit = units_per_trip * net_profit_per_unit

        # --- 7. Formater resultater for UI ---
        return {
            "buy_price": f"{buy_price:,.2f} ISK",
            "buy_volume": f"{buy_volume:,}",
            "sell_price": f"{sell_price:,.2f} ISK",
            "sell_volume": f"{sell_volume:,}" if sell_volume != float('inf') else "Ubegrenset",
            "transaction_cost": f"{transaction_cost:,.2f} ISK",
            "profit_per_unit": f"{net_profit_per_unit:,.2f} ISK",
            "units_per_trip": f"{units_per_trip:,}",
            "total_profit": f"{total_profit:,.2f} ISK"
        }

    except Exception as e:
        return {'error': f"En uventet feil oppstod: {e}"}


def calculate_assets_value(assets, prices):
    """Beregner den totale verdien av en liste med eiendeler basert på en prisoversikt."""
    total_value = 0.0
    for asset in assets:
        price = prices.get(asset.get('type_id'), 0)
        quantity = asset.get('quantity', 0)
        total_value += price * quantity
    return total_value

def calculate_net_trade_profit(transactions):
    """Beregner netto profitt fra en liste med transaksjoner."""
    net_profit = 0
    if not transactions:
        return 0

    for trans in transactions:
        if not isinstance(trans, dict):
            continue

        quantity = trans.get('quantity', 0)
        unit_price = trans.get('unit_price', 0)
        is_buy = trans.get('is_buy', False)
        
        total_value = quantity * unit_price

        if is_buy:
            net_profit -= total_value
        else:
            net_profit += total_value
            
    return net_profit

def calculate_manufacturing_profit(bp_data, material_prices, product_price, system_index, me, te, sales_tax, brokers_fee):
    """Beregner profitten for å produsere en vare basert på gitte data."""
    id_to_name = {v: k for k, v in config.ITEM_NAME_TO_ID.items()}
    manufacturing = bp_data['activities']['manufacturing']
    
    total_material_cost = 0
    materials_list = []
    me_modifier = (1 - (me / 100.0))
    
    for mat in manufacturing['materials']:
        required_qty = mat['quantity']
        
        # KRITISK ENDRING: Bruker math.ceil for å runde OPP, slik spillet gjør.
        adjusted_qty = math.ceil(required_qty * me_modifier)
        
        price = material_prices.get(mat['typeID'], 0)
        if price == 0:
            # Denne sjekken er en fallback, scanneren bør allerede ha filtrert dette.
            return {'error': f"Mangler pris for materiale: {id_to_name.get(mat['typeID'], mat['typeID'])}"}
            
        cost = adjusted_qty * price
        total_material_cost += cost
        materials_list.append({
            'name': id_to_name.get(mat['typeID'], f"ID: {mat['typeID']}"),
            'req_qty': adjusted_qty, 'price': price, 'total_cost': cost
        })

    installation_cost = total_material_cost * system_index
    total_cost_per_run = total_material_cost + installation_cost
    
    product = manufacturing['products'][0]
    product_quantity = product['quantity']
    
    revenue = (product_price * product_quantity)
    fees = revenue * ((sales_tax / 100) + (brokers_fee / 100))
    net_revenue = revenue - fees

    net_profit_per_run = net_revenue - total_cost_per_run
    
    base_time = manufacturing['time']
    te_modifier = (1 - (te / 100.0))
    production_time_seconds = base_time * te_modifier
    
    profit_per_hour = (net_profit_per_run / production_time_seconds) * 3600 if production_time_seconds > 0 else 0
    
    return {
        "material_cost": total_material_cost, "installation_cost": installation_cost,
        "total_cost_per_run": total_cost_per_run, "product_sell_price": product_price,
        "net_profit_per_run": net_profit_per_run, "profit_per_hour": profit_per_hour,
        "materials": materials_list
    }