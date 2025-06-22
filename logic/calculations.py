import api
import db
import config
import math
import logging

def get_single_item_analysis(analysis_config, status_callback=None):
    """Utfører en komplett analyse for én vare mellom to stasjoner."""
    try:
        if status_callback: status_callback("Starter analyse...", 10)

        item_name = analysis_config['item_name']
        type_id = db.get_item_id_by_name(item_name)
        if not type_id: return {'error': f"Fant ikke varen '{item_name}'."}

        buy_station_info = config.STATIONS_INFO[analysis_config['buy_station']]
        sell_station_info = config.STATIONS_INFO[analysis_config['sell_station']]
        
        if status_callback: status_callback("Henter markedsordrer...", 30)

        buy_region_orders, _ = api.get_market_orders(buy_station_info['region_id'], "all", 1, type_id=type_id)
        if buy_station_info['region_id'] == sell_station_info['region_id']:
            sell_region_orders = buy_region_orders
        else:
            sell_region_orders, _ = api.get_market_orders(sell_station_info['region_id'], "all", 1, type_id=type_id)

        if not buy_region_orders or not sell_region_orders:
            return {'error': "Kunne ikke hente markedsordrer."}
        
        if status_callback: status_callback("Finner beste priser...", 90)
            
        lowest_sell_order = min((o for o in buy_region_orders if not o.get('is_buy_order') and o['location_id'] == buy_station_info['id']), key=lambda x: x['price'], default=None)
        highest_buy_order = max((o for o in sell_region_orders if o.get('is_buy_order') and o['location_id'] == sell_station_info['id']), key=lambda x: x['price'], default=None)

        if not lowest_sell_order or not highest_buy_order:
            return {'error': "Fant ikke kjøps- og/eller salgsordrer for denne varen på de valgte stasjonene."}

        buy_price = lowest_sell_order['price']
        sell_price = highest_buy_order['price']
        
        if status_callback: status_callback("Kalkulerer profitt...", 95)

        broker_fee_rate = analysis_config['brokers_fee_rate'] / 100
        sales_tax_rate = analysis_config['sales_tax_rate'] / 100
        
        # --- DEBUG-UTSAGNFRASE ---
        print("\n--- DEBUG: Profittkalkulering ---")
        print(f"  Rå Kjøpspris: {buy_price}")
        print(f"  Rå Salgspris: {sell_price}")
        print(f"  Brutto Profitt (før avgifter): {sell_price - buy_price}")
        print(f"  Broker Fee Rate: {broker_fee_rate}")
        print(f"  Sales Tax Rate: {sales_tax_rate}")
        
        buy_broker_fee = buy_price * broker_fee_rate
        sell_broker_fee = sell_price * broker_fee_rate
        tax_on_sale = sell_price * sales_tax_rate
        transaction_cost = buy_broker_fee + sell_broker_fee + tax_on_sale

        print(f"  Kjøpsavgift: {buy_broker_fee}")
        print(f"  Salgsavgift (broker): {sell_broker_fee}")
        print(f"  Salgsskatt: {tax_on_sale}")
        print(f"  Total avgift per enhet: {transaction_cost}")
        
        profit_per_unit = (sell_price - buy_price) - transaction_cost
        print(f"  Netto profitt per enhet: {profit_per_unit}")
        print("---------------------------------\n")
        # ---------------------------

        item_volume_m3 = db.get_item_volume(type_id)
        if not item_volume_m3 or item_volume_m3 == 0:
            return {'error': f"Mangler voluminformasjon for '{item_name}'."}
            
        buy_volume = lowest_sell_order['volume_remain']
        sell_volume = highest_buy_order['volume_remain']
        max_units_by_market = min(buy_volume, sell_volume)
        
        units_per_trip = math.floor(analysis_config['ship_cargo'] / item_volume_m3)
        actual_units = min(units_per_trip, max_units_by_market)

        total_investment = actual_units * buy_price
        total_profit = actual_units * profit_per_unit

        return {
            'buy_price': buy_price, 'buy_volume': buy_volume,
            'sell_price': sell_price, 'sell_volume': sell_volume,
            'transaction_cost': transaction_cost, 'profit_per_unit': profit_per_unit,
            'units_per_trip': actual_units, 'total_profit': total_profit,
            'total_investment': total_investment, 'item_volume': item_volume_m3
        }

    except Exception as e:
        logging.error(f"Feil i get_single_item_analysis: {e}", exc_info=True)
        return {'error': f"En uventet feil oppstod: {e}"}