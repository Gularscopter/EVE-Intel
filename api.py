import requests
import logging
import db
import config
import time
from collections import defaultdict

ESI_BASE_URL = "https://esi.evetech.net/latest"
LOGIN_BASE_URL = "https://login.eveonline.com"
FUZZWORK_API_URL = "https://market.fuzzwork.co.uk/aggregates/"

_name_cache = {}
_station_details_cache = {}
CACHE_TIMEOUT_SECONDS = 3600 # 1 hour

def get_character_id(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{LOGIN_BASE_URL}/oauth/verify"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("CharacterID")
    except requests.exceptions.RequestException as e:
        error_text = e.response.text if e.response else "No response from server"
        logging.error(f"Failed to verify token. Status: {e.response.status_code if e.response else 'N/A'}. Response: {error_text}")
        return None

def get_market_prices(type_ids, station_id=60003760):
    """
    OPTIMIZED: Fetches only buy/sell prices from Fuzzwork. This is very fast.
    """
    if not type_ids: return {}
    unique_type_ids = list(set(type_ids))
    prices = defaultdict(lambda: {'buy': 0, 'sell': 0})
    
    chunk_size = 200
    id_chunks = [unique_type_ids[i:i + chunk_size] for i in range(0, len(unique_type_ids), chunk_size)]
    
    for chunk in id_chunks:
        try:
            params = {'station': station_id, 'types': ",".join(map(str, chunk))}
            response = requests.get(FUZZWORK_API_URL, params=params)
            response.raise_for_status()
            market_data = response.json()
            for type_id_str, data in market_data.items():
                type_id = int(type_id_str)
                prices[type_id]['buy'] = float(data.get('buy', {}).get('max', 0))
                prices[type_id]['sell'] = float(data.get('sell', {}).get('min', 0))
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            logging.error(f"Failed to get or parse prices from Fuzzwork API for a chunk: {e}")
            
    return prices

def get_market_history_for_items(type_ids, region_id=10000002):
    """
    SLOW: Fetches historical daily volume from ESI. To be used sparingly.
    """
    if not type_ids: return {}
    unique_type_ids = list(set(type_ids))
    volumes = {}
    
    for i, type_id in enumerate(unique_type_ids):
        if i > 0 and i % 50 == 0: logging.info(f"Fetching market history {i+1}/{len(unique_type_ids)}...")
        history = get_item_price_history(region_id, type_id)
        if history and isinstance(history, list) and len(history) > 0:
            volumes[type_id] = history[-1].get('volume', 0)
        else:
            volumes[type_id] = 0
            
    return volumes

def get_character_wallet_journal(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; url = f"{ESI_BASE_URL}/characters/{character_id}/wallet/journal/"; journal_entries = []; page = 1
    while True:
        try:
            response = requests.get(url, headers=headers, params={'page': page})
            if response.status_code != 200: break
            data = response.json()
            if not data: break
            journal_entries.extend(data); page += 1
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get wallet journal page {page}: {e}"); break
    return journal_entries

def get_character_wallet_transactions(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; url = f"{ESI_BASE_URL}/characters/{character_id}/wallet/transactions/"; transactions = []
    try:
        response = requests.get(url, headers=headers, params={'page': 1})
        response.raise_for_status()
        data = response.json()
        if data: transactions.extend(data)
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get wallet transactions for character {character_id}: {e}")
    return transactions

def get_character_location(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; url = f"{ESI_BASE_URL}/characters/{character_id}/location/"
    try: response = requests.get(url, headers=headers); response.raise_for_status(); return response.json()
    except requests.exceptions.RequestException: return None

def get_character_ship(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; url = f"{ESI_BASE_URL}/characters/{character_id}/ship/"
    try: response = requests.get(url, headers=headers); response.raise_for_status(); return response.json()
    except requests.exceptions.RequestException: return None

def get_character_orders(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; url = f"{ESI_BASE_URL}/characters/{character_id}/orders/"
    try: response = requests.get(url, headers=headers); response.raise_for_status(); return response.json()
    except requests.exceptions.RequestException: return []

def get_market_orders(region_id, order_type="all", page=1):
    params = {"order_type": order_type, "page": page}
    try:
        response = requests.get(f"{ESI_BASE_URL}/markets/{region_id}/orders/", params=params)
        if response.status_code == 404: return []
        response.raise_for_status(); return response.json()
    except requests.exceptions.RequestException: return []

def resolve_name_to_id(name, category=None):
    now = time.time()
    if name in _name_cache and (now - _name_cache[name]['timestamp']) < CACHE_TIMEOUT_SECONDS: return _name_cache[name]['data'].get('id')
    try:
        response = requests.post(f"{ESI_BASE_URL}/universe/ids/", json=[name]); response.raise_for_status(); data = response.json()
        if category:
            key = category + 's'
            if key in data and data[key]: result = data[key][0]; _name_cache[name] = {'timestamp': now, 'data': result}; return result.get('id')
        for cat_key, entries in data.items():
            if entries: result = entries[0]; _name_cache[name] = {'timestamp': now, 'data': result}; return result.get('id')
        return None
    except requests.exceptions.RequestException: return None

def get_station_details(station_id):
    now = time.time()
    if station_id in _station_details_cache and (now - _station_details_cache[station_id]['timestamp']) < CACHE_TIMEOUT_SECONDS: return _station_details_cache[station_id]['data']
    try:
        station_response = requests.get(f"{ESI_BASE_URL}/universe/stations/{station_id}/"); station_response.raise_for_status(); station_data = station_response.json()
        system_response = requests.get(f"{ESI_BASE_URL}/universe/systems/{station_data['system_id']}/"); system_response.raise_for_status()
        constellation_id = system_response.json()['constellation_id']
        constellation_response = requests.get(f"{ESI_BASE_URL}/universe/constellations/{constellation_id}/"); constellation_response.raise_for_status()
        region_id = constellation_response.json()['region_id']
        details = {'id': station_id, 'name': station_data['name'], 'system_id': station_data['system_id'], 'region_id': region_id}
        _station_details_cache[station_id] = {'timestamp': now, 'data': details}
        return details
    except requests.exceptions.RequestException: return None

def get_character_name(character_id):
    response = requests.get(f"{ESI_BASE_URL}/characters/{character_id}/"); return response.json()["name"] if response.status_code == 200 else "Unknown"

def get_character_details(character_id):
    response = requests.get(f"{ESI_BASE_URL}/characters/{character_id}/")
    if response.status_code == 200:
        data = response.json(); corp_id, alliance_id = data.get('corporation_id'), data.get('alliance_id')
        if corp_id: data['corporation_name'] = get_corp_name(corp_id)
        if alliance_id: data['alliance_name'] = get_alliance_name(alliance_id)
        return data
    return None

def get_corp_name(corp_id):
    response = requests.get(f"{ESI_BASE_URL}/corporations/{corp_id}/"); return response.json().get('name', 'N/A') if response.status_code == 200 else 'N/A'
def get_alliance_name(alliance_id):
    response = requests.get(f"{ESI_BASE_URL}/alliances/{alliance_id}/"); return response.json().get('name', 'N/A') if response.status_code == 200 else 'N/A'

def get_character_wallet(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{ESI_BASE_URL}/characters/{character_id}/wallet/", headers=headers); return response.json() if response.status_code == 200 else None

def get_character_assets_with_names(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}; assets = []; page = 1
    while True:
        response = requests.get(f"{ESI_BASE_URL}/characters/{character_id}/assets/?page={page}", headers=headers)
        if response.status_code != 200: break
        data = response.json();
        if not data: break
        assets.extend(data); page += 1
    type_ids = list(set([asset['type_id'] for asset in assets])); item_names = db.get_item_names(type_ids)
    location_ids = list(set([asset['location_id'] for asset in assets])); location_names = get_location_names(location_ids, access_token, character_id)
    for asset in assets:
        asset['name'] = item_names.get(asset['type_id'], 'Unknown Item'); asset['volume'] = db.get_item_volume(asset['type_id']) or 0.0
        asset['location_name'] = location_names.get(asset['location_id'], 'Unknown Location')
    assets_by_location = defaultdict(list)
    for asset in assets:
        assets_by_location[asset['location_name']].append(asset)
    return assets_by_location

def get_location_names(location_ids, access_token, character_id):
    if isinstance(location_ids, set): location_ids = list(location_ids)
    headers = {"Authorization": f"Bearer {access_token}"}; names = {}
    id_chunks = [location_ids[i:i + 1000] for i in range(0, len(location_ids), 1000)]
    for chunk in id_chunks:
        try:
            response = requests.post(f"{ESI_BASE_URL}/universe/names/", json=list(set(chunk)))
            if response.status_code == 200:
                for item in response.json(): names[item['id']] = item['name']
        except Exception as e: logging.error(f"Failed to get names for chunk: {e}")
    for loc_id in location_ids:
        if loc_id not in names:
            if loc_id == character_id: names[loc_id] = "Asset Safety"
            else: names[loc_id] = f"Unknown Location ({loc_id})"
    return names

def get_item_price_history(region_id, type_id):
    try: response = requests.get(f"{ESI_BASE_URL}/markets/{region_id}/history/?type_id={type_id}"); response.raise_for_status(); return response.json()
    except requests.RequestException: return None