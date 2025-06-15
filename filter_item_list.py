# Fil: filter_item_list.py
import requests
import json
import time

FULL_ITEM_LIST_FILE = 'items.json'
FILTERED_LIST_FILE = 'items_filtered.json'
PRICES_URL = "https://esi.evetech.net/latest/markets/prices/?datasource=tranquility"
THE_FORGE_REGION_ID = 10000002 # Jita sin region, som er en god indikator

# ==============================================================================
# ### JUSTER DISSE TERSKLENE ETTER BEHOV ###
# ==============================================================================
# Beholder varer HVIS en av disse er sanne:
# 1. Den daglige handelsverdien er over denne grensen (fanger opp høy-volum varer)
MINIMUM_DAILY_TRADE_VALUE = 50_000_000  # 50 millioner ISK

# 2. Prisen per enhet er over denne grensen (fanger opp høy-verdi varer)
MINIMUM_PRICE_PER_UNIT = 5_000_000   # 5 millioner ISK
# ==============================================================================


def fetch_esi_data(url):
    headers = {'User-Agent': 'EVE-List-Filter/3.0'}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return None

def create_filtered_list():
    print("Starter prosessen med å lage en høykvalitets vareliste...")
    
    # Steg 1: Last inn den store, lokale listen vår
    try:
        with open(FULL_ITEM_LIST_FILE, 'r', encoding='utf-8') as f:
            full_item_list = json.load(f)
        print(f"Lastet {len(full_item_list)} varer fra {FULL_ITEM_LIST_FILE}.")
    except Exception as e:
        print(f"FEIL: Kunne ikke laste den lokale filen {FULL_ITEM_LIST_FILE}: {e}")
        return

    # Steg 2: Hent live priser fra ESI
    print("Henter live markedspriser fra ESI...")
    live_prices = fetch_esi_data(PRICES_URL)
    if not live_prices:
        print("FEIL: Kunne ikke hente live prisdata.")
        return
    price_map = {item['type_id']: item.get('average_price', 0) for item in live_prices}
    print(f"Fant priser for {len(price_map)} unike varer.")

    # Steg 3: Gå gjennom listen og filtrer basert på pris OG volum
    print("\nStarter filtrering basert på total handelsverdi...")
    filtered_items = {}
    total_items = len(full_item_list)

    for i, (item_name, type_id) in enumerate(full_item_list.items()):
        if i % 100 == 0:
            print(f"Prosessert {i}/{total_items}...", end='\r')
        
        avg_price = price_map.get(type_id, 0)
        if avg_price <= 0:
            continue

        # Hent historisk volum
        history_url = f"https://esi.evetech.net/latest/markets/{THE_FORGE_REGION_ID}/history/?datasource=tranquility&type_id={type_id}"
        history = fetch_esi_data(history_url)
        
        avg_daily_vol = 0
        if history:
            last_7_days = [h['volume'] for h in history[-7:]]
            if last_7_days:
                avg_daily_vol = sum(last_7_days) / len(last_7_days)
        
        if avg_daily_vol <= 0:
            continue
            
        # ### DEN NYE, SMARTE LOGIKKEN ###
        daily_trade_value = avg_price * avg_daily_vol
        
        # Inkluder varen HVIS den møter ETT av kravene
        if daily_trade_value >= MINIMUM_DAILY_TRADE_VALUE or avg_price >= MINIMUM_PRICE_PER_UNIT:
            filtered_items[item_name] = type_id
        
        time.sleep(0.01)

    print(f"\n\nFiltrering ferdig. Den nye listen inneholder {len(filtered_items)} høykvalitets-varer.")

    # Steg 4: Lagre den nye, mye kortere listen
    try:
        with open(FILTERED_LIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(filtered_items, f, indent=4, ensure_ascii=False)
        print(f"Vellykket! Den nye listen er lagret i {FILTERED_LIST_FILE}.")
        print("Kjør hovedprogrammet igjen for en mye raskere skanning.")
    except Exception as e:
        print(f"FEIL: Kunne ikke lagre den nye filen {FILTERED_LIST_FILE}: {e}")

if __name__ == '__main__':
    create_filtered_list()