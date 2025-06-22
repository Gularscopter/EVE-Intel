import time
import api
import config

def format_time(seconds):
    """Formaterer sekunder til en MM:SS-streng for ETA-visning."""
    if seconds is None or seconds < 0:
        return ""
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"

def get_active_items_from_jita(progress_callback, active_flag, scan_type):
    """
    Forhåndsfiltrerer alle varer basert på aktivitet i Jita for å redusere antall
    kaller som må gjøres i selve skannet. Dette øker ytelsen betraktelig.
    """
    all_type_ids_master = list(config.ITEM_NAME_TO_ID.values())
    initial_item_chunks = [all_type_ids_master[i:i + 200] for i in range(0, len(all_type_ids_master), 200)]
    
    # Kriterier for å anse en vare som "aktiv" nok til å skannes
    PREFILTER_MIN_ISK_VOLUME = 100_000_000  # Minimum ISK-verdi på kjøpsordrer
    PREFILTER_MAX_SPREAD_PERCENT = 40.0    # Maksimal prosent-spread mellom kjøp og salg
    PREFILTER_MIN_ORDER_COUNT = 5          # Minimum antall kjøps- og salgsordrer

    progress_callback({'scan_type': scan_type, 'progress': 0, 'status': "Forhåndsfilter: Finner aktive varer i Jita..."})
    jita_station_id = config.STATIONS_INFO['Jita']['id']
    active_items = set()
    
    for i, chunk in enumerate(initial_item_chunks):
        if not active_flag.is_set():
            return None  # Avbryt hvis brukeren har trykket stopp
        
        progress_callback({
            'scan_type': scan_type,
            'progress': (i + 1) / len(initial_item_chunks) * 0.1,
            'status': f"Forhåndsfilter: Analyserer Jita (Gruppe {i+1}/{len(initial_item_chunks)})"
        })
        
        jita_market_data = api.fetch_fuzzwork_market_data(jita_station_id, chunk)
        
        for type_id_str, item_data in jita_market_data.items():
            buy_info, sell_info = item_data.get('buy', {}), item_data.get('sell', {})
            if not buy_info or not sell_info:
                continue

            highest_buy_price = float(buy_info.get('max', 0))
            buy_volume = float(buy_info.get('volume', 0))
            buy_order_count = int(buy_info.get('orderCount', 0))
            lowest_sell_price = float(sell_info.get('min', 0))
            sell_order_count = int(sell_info.get('orderCount', 0))

            if highest_buy_price > 0 and lowest_sell_price > 0:
                total_buy_value = highest_buy_price * buy_volume
                price_spread_percent = ((lowest_sell_price - highest_buy_price) / lowest_sell_price) * 100
                
                if (total_buy_value >= PREFILTER_MIN_ISK_VOLUME and 
                    price_spread_percent < PREFILTER_MAX_SPREAD_PERCENT and
                    buy_order_count >= PREFILTER_MIN_ORDER_COUNT and 
                    sell_order_count >= PREFILTER_MIN_ORDER_COUNT):
                    active_items.add(int(type_id_str))
        
        time.sleep(0.5)  # Vær snill mot Fuzzwork API

    if not active_items:
        progress_callback({'scan_type': scan_type, 'error': "Fant ingen varer i Jita som møtte aktivitetskravene."})
        return None
    
    status_update = f"Forhåndsfilter fullført. Reduserte varesøk fra {len(all_type_ids_master)} til {len(active_items)}."
    progress_callback({'scan_type': scan_type, 'progress': 0.1, 'status': status_update})
    time.sleep(2)  # Gi brukeren tid til å lese statusen
    return list(active_items)

def get_trend_indicator(history):
    """Analyserer prishistorikk for å lage en enkel trendindikator (↑, ↓, —)."""
    if not history or len(history) < 10:
        return "—"
    try:
        # Sammenligner snittet av de siste 3 dagene med de 7 dagene før det
        recent_avg = sum(h['average'] for h in history[-3:]) / 3
        older_avg = sum(h['average'] for h in history[-10:-3]) / 7
        if older_avg > 0:
            price_change_pct = ((recent_avg - older_avg) / older_avg) * 100
            if price_change_pct > 1.5: return "↑"   # Prisen går opp
            if price_change_pct < -1.5: return "↓"  # Prisen går ned
    except (ZeroDivisionError, IndexError):
        pass
    return "—"  # Stabil pris
