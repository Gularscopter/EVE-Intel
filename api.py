# api.py
import requests
import logging
import db
import config
import time
from collections import defaultdict
import threading

# --- SENTRALISERT RATE-LIMITER FOR ESI (Tryggere versjon) ---
class RateLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.errors_remaining = 100
        self.reset_time = time.time() + 60

    def update_from_headers(self, headers):
        with self.lock:
            if 'X-Esi-Error-Limit-Remain' in headers:
                self.errors_remaining = int(headers['X-Esi-Error-Limit-Remain'])
            if 'X-Esi-Error-Limit-Reset' in headers:
                self.reset_time = time.time() + int(headers['X-Esi-Error-Limit-Reset'])

    def wait_if_needed(self):
        with self.lock:
            if self.errors_remaining < 20: # Bruker en trygg margin
                wait_time = self.reset_time - time.time()
                if wait_time > 0:
                    logging.warning(f"Rate limit lav ({self.errors_remaining}). Pauser i {wait_time:.2f} sekunder...")
                    time.sleep(wait_time + 1)

rate_limiter = RateLimiter()

def esi_request(url, method='get', **kwargs):
    """En tryggere ESI-funksjon som kun håndterer rate-limiting og returnerer rå-responsen."""
    rate_limiter.wait_if_needed()
    try:
        if method == 'get':
            response = requests.get(url, **kwargs)
        elif method == 'post':
            response = requests.post(url, **kwargs)
        else:
            raise ValueError(f"Ugyldig metode: {method}")
        
        rate_limiter.update_from_headers(response.headers)

        if response.status_code == 420:
            logging.warning(f"Mottok 420 Rate Limit Exceeded for URL {url}. Pauser i 5 sekunder...")
            time.sleep(5)
            return esi_request(url, method=method, **kwargs)

        return response
    except requests.exceptions.RequestException as e:
        logging.error(f"Nettverksfeil under kall til {url}: {e}")
        return None
# --- SLUTT PÅ RATE-LIMITER ---

ESI_BASE_URL = "https://esi.evetech.net/latest"
LOGIN_BASE_URL = "https://login.eveonline.com"
FUZZWORK_API_URL = "https://market.fuzzwork.co.uk/aggregates/"

_name_cache = {}
_station_details_cache = {}
_structure_details_cache = {}
CACHE_TIMEOUT_SECONDS = 3600

def verify_token_and_get_character(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{LOGIN_BASE_URL}/oauth/verify"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return {'id': data.get("CharacterID"), 'name': data.get("CharacterName")}
    except requests.exceptions.RequestException as e:
        error_text = e.response.text if e.response else "No response from server"
        logging.error(f"Failed to verify token. Status: {e.response.status_code if e.response else 'N/A'}. Response: {error_text}")
        return None

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

def get_market_prices(type_ids, station_id=None, region_id=None):
    if not type_ids: return {}
    params = {}
    if station_id: params['station'] = station_id
    elif region_id: params['region'] = region_id
    else: params['station'] = 60003760
    unique_type_ids = list(set(type_ids))
    prices = defaultdict(lambda: {'buy': 0, 'sell': 0})
    id_chunks = [unique_type_ids[i:i + 200] for i in range(0, len(unique_type_ids), 200)]
    for chunk in id_chunks:
        try:
            chunk_params = params.copy()
            chunk_params['types'] = ",".join(map(str, chunk))
            response = requests.get(FUZZWORK_API_URL, params=chunk_params)
            response.raise_for_status()
            market_data = response.json()
            for type_id_str, data in market_data.items():
                type_id = int(type_id_str)
                prices[type_id]['buy'] = float(data.get('buy', {}).get('max', 0))
                prices[type_id]['sell'] = float(data.get('sell', {}).get('min', 0))
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            logging.error(f"Failed to get or parse prices from Fuzzwork API for a chunk: {e}")
    return prices

def get_scanner_market_data(type_ids, station_id=None, region_id=None):
    if not type_ids: return {}
    params = {}
    if station_id: params['station'] = station_id
    elif region_id: params['region'] = region_id
    else: params['station'] = 60003760
    unique_type_ids = list(set(type_ids))
    market_data_map = defaultdict(lambda: {
        'highest_buy': 0, 'lowest_sell': 0, 'buy_order_volume': 0, 'sell_order_volume': 0
    })
    id_chunks = [unique_type_ids[i:i + 200] for i in range(0, len(unique_type_ids), 200)]
    for chunk in id_chunks:
        try:
            chunk_params = params.copy()
            chunk_params['types'] = ",".join(map(str, chunk))
            response = requests.get(FUZZWORK_API_URL, params=chunk_params)
            response.raise_for_status()
            fuzzwork_json = response.json()
            for type_id_str, data in fuzzwork_json.items():
                type_id = int(type_id_str)
                market_data_map[type_id]['highest_buy'] = float(data.get('buy', {}).get('max', 0))
                market_data_map[type_id]['lowest_sell'] = float(data.get('sell', {}).get('min', 0))
                market_data_map[type_id]['buy_order_volume'] = int(float(data.get('buy', {}).get('volume', 0)))
                market_data_map[type_id]['sell_order_volume'] = int(float(data.get('sell', {}).get('volume', 0)))
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            logging.error(f"Failed to get or parse scanner data from Fuzzwork API for a chunk: {e}")
    return market_data_map

def get_market_orders(region_id, order_type="all", page=1, type_id=None):
    params = {"order_type": order_type, "page": page}
    if type_id: params['type_id'] = type_id
    try:
        response = esi_request(f"{ESI_BASE_URL}/markets/{region_id}/orders/", params=params)
        if response is None or response.status_code == 404: return [], 0
        response.raise_for_status()
        total_pages = int(response.headers.get('x-pages', 1))
        return response.json(), total_pages
    except requests.exceptions.RequestException: return [], 0

def get_character_orders(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/characters/{character_id}/orders/"
    try:
        response = esi_request(url, headers=headers)
        if response:
            response.raise_for_status()
            return response.json()
        return []
    except requests.exceptions.RequestException as e:
        logging.error(f"Could not fetch character orders for character {character_id}: {e}")
        return []

def get_character_ship(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/characters/{character_id}/ship/"
    try:
        response = esi_request(url, headers=headers)
        if response:
            response.raise_for_status()
            return response.json()
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Could not fetch character ship for character {character_id}: {e}")
        return None

def get_character_location(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/characters/{character_id}/location/"
    try:
        response = esi_request(url, headers=headers)
        if response:
            response.raise_for_status()
            return response.json()
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Could not fetch character location for character {character_id}: {e}")
        return None

def get_structure_details(structure_id, access_token):
    now = time.time()
    cache_key = f"struct_{structure_id}"
    if cache_key in _structure_details_cache and (now - _structure_details_cache[cache_key]['timestamp']) < CACHE_TIMEOUT_SECONDS:
        return _structure_details_cache[cache_key]['data']
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/universe/structures/{structure_id}/"
    try:
        response = esi_request(url, headers=headers)
        if response:
            response.raise_for_status()
            data = response.json()
            data['name'] = data.get('name', f"Struktur ID: {structure_id}")
            _structure_details_cache[cache_key] = {'timestamp': now, 'data': data}
            return data
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else "N/A"
        logging.warning(f"Could not fetch details for structure {structure_id}: {status_code}")
    error_data = {'name': f"Utilgjengelig ({structure_id})", 'solar_system_id': None}
    _structure_details_cache[cache_key] = {'timestamp': now, 'data': error_data}
    return error_data

def get_structure_name(structure_id, access_token):
    return get_structure_details(structure_id, access_token)

_location_to_system_map = {}
def resolve_location_to_system_map(location_ids, access_token):
    ids_to_resolve = list(set(loc_id for loc_id in location_ids if loc_id not in _location_to_system_map))
    if not ids_to_resolve:
        return {k: v for k, v in _location_to_system_map.items() if k in location_ids}
    npc_station_ids = {loc_id for loc_id in ids_to_resolve if 60000000 <= loc_id < 64000000}
    player_structure_ids = {loc_id for loc_id in ids_to_resolve if loc_id >= 100000000000}
    if npc_station_ids:
        station_system_map = db.get_station_to_system_map()
        for station_id in npc_station_ids:
            if station_id in station_system_map:
                _location_to_system_map[station_id] = station_system_map[station_id]
    if player_structure_ids and access_token:
        for struct_id in player_structure_ids:
            details = get_structure_details(struct_id, access_token)
            if details and details.get('solar_system_id'):
                _location_to_system_map[struct_id] = details['solar_system_id']
    return {k: v for k, v in _location_to_system_map.items() if k in location_ids}

def resolve_name_to_id(name, category=None):
    now = time.time()
    cache_key = f"{category}_{name.lower()}" if category else name.lower()
    if cache_key in _name_cache: return _name_cache[cache_key]
    try:
        response = esi_request(f"{ESI_BASE_URL}/universe/ids/", method='post', json=[name])
        if response:
            response.raise_for_status()
            data = response.json()
            if category:
                key = category + 's'
                if key in data and data[key]:
                    result_id = data[key][0]['id']; _name_cache[cache_key] = result_id; return result_id
            for cat_key, entries in data.items():
                if entries:
                    result_id = entries[0]['id']; _name_cache[cache_key] = result_id; return result_id
        return None
    except requests.exceptions.RequestException: return None

def get_station_details(station_id):
    now = time.time()
    if station_id in _station_details_cache and (now - _station_details_cache[station_id]['timestamp']) < CACHE_TIMEOUT_SECONDS:
        return _station_details_cache[station_id]['data']
    try:
        station_response = esi_request(f"{ESI_BASE_URL}/universe/stations/{station_id}/")
        if not station_response: return None
        station_response.raise_for_status()
        station_data = station_response.json()
        system_response = esi_request(f"{ESI_BASE_URL}/universe/systems/{station_data['system_id']}/")
        if not system_response: return None
        system_response.raise_for_status()
        constellation_id = system_response.json()['constellation_id']
        constellation_response = esi_request(f"{ESI_BASE_URL}/universe/constellations/{constellation_id}/")
        if not constellation_response: return None
        constellation_response.raise_for_status()
        region_id = constellation_response.json()['region_id']
        details = {'id': station_id, 'name': station_data['name'], 'system_id': station_data['system_id'], 'region_id': region_id}
        _station_details_cache[station_id] = {'timestamp': now, 'data': details}
        return details
    except requests.exceptions.RequestException: return None

def get_character_name(character_id):
    response = esi_request(f"{ESI_BASE_URL}/characters/{character_id}/")
    return response.json()["name"] if response and response.status_code == 200 else "Unknown"

def get_character_details(character_id):
    response = esi_request(f"{ESI_BASE_URL}/characters/{character_id}/")
    if response and response.status_code == 200:
        data = response.json()
        corp_id = data.get('corporation_id')
        alliance_id = data.get('alliance_id')
        if corp_id: data['corporation_name'] = get_corp_name(corp_id)
        if alliance_id: data['alliance_name'] = get_alliance_name(alliance_id)
        return data
    return None

def get_corp_name(corp_id):
    response = esi_request(f"{ESI_BASE_URL}/corporations/{corp_id}/")
    return response.json().get('name', 'N/A') if response and response.status_code == 200 else 'N/A'

def get_alliance_name(alliance_id):
    response = esi_request(f"{ESI_BASE_URL}/alliances/{alliance_id}/")
    return response.json().get('name', 'N/A') if response and response.status_code == 200 else 'N/A'

def get_character_wallet(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    response = esi_request(f"{ESI_BASE_URL}/characters/{character_id}/wallet/", headers=headers)
    return response.json() if response and response.status_code == 200 else None

def get_character_wallet_journal(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/characters/{character_id}/wallet/journal/"
    journal_entries = []
    page = 1
    while True:
        try:
            response = esi_request(url, headers=headers, params={'page': page})
            if not response or response.status_code != 200: break
            data = response.json()
            if not data: break
            journal_entries.extend(data)
            page += 1
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logging.error(f"Failed to get wallet journal page {page}: {e}")
            break
    return journal_entries

def get_character_wallet_transactions(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{ESI_BASE_URL}/characters/{character_id}/wallet/transactions/"
    try:
        response = esi_request(url, headers=headers, params={'page': 1})
        if response:
            response.raise_for_status()
            return response.json()
        return []
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to get wallet transactions for character {character_id}: {e}")
        return []

def get_character_assets_with_names(character_id, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    assets = []
    page = 1
    while True:
        url = f"{ESI_BASE_URL}/characters/{character_id}/assets/"
        response = esi_request(url, headers=headers, params={'page': page})
        if not response or response.status_code != 200: break
        data = response.json()
        if not data: break
        assets.extend(data)
        page += 1
    type_ids = list(set([asset['type_id'] for asset in assets]))
    item_names = db.get_item_names(type_ids)
    location_ids = list(set([asset['location_id'] for asset in assets]))
    location_names = get_location_names(location_ids, access_token, character_id)
    for asset in assets:
        asset['name'] = item_names.get(asset['type_id'], 'Unknown Item')
        asset['volume'] = db.get_item_volume(asset['type_id']) or 0.0
        asset['location_name'] = location_names.get(asset['location_id'], 'Unknown Location')
    assets_by_location = defaultdict(list)
    for asset in assets:
        assets_by_location[asset['location_name']].append(asset)
    return assets_by_location

def get_location_names(location_ids, access_token, character_id):
    if not location_ids: return {}
    if isinstance(location_ids, set):
        location_ids = list(location_ids)
    names = {}
    id_chunks = [location_ids[i:i + 1000] for i in range(0, len(location_ids), 1000)]
    for chunk in id_chunks:
        if not chunk: continue
        try:
            response = esi_request(f"{ESI_BASE_URL}/universe/names/", method='post', json=chunk)
            if response and response.status_code == 200:
                for item in response.json():
                    names[item['id']] = item['name']
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logging.error(f"Failed to get names for chunk: {e}")
    for loc_id in location_ids:
        if loc_id not in names:
            if loc_id == character_id:
                names[loc_id] = "Asset Safety"
            else:
                names[loc_id] = f"Unknown Location ({loc_id})"
    return names

def get_item_price_history(region_id, type_id):
    try:
        response = esi_request(f"{ESI_BASE_URL}/markets/{region_id}/history/", params={'type_id': type_id})
        if response and response.status_code == 200:
            return response.json()
        return None
    except (requests.exceptions.RequestException, json.JSONDecodeError):
        return None

def get_market_history_for_items(type_ids, region_id=10000002):
    if not type_ids: return {}
    unique_type_ids = list(set(type_ids))
    volumes = {}
    for i, type_id in enumerate(unique_type_ids):
        if i > 0 and i % 50 == 0:
            logging.info(f"Fetching market history {i+1}/{len(unique_type_ids)}...")
        history = get_item_price_history(region_id, type_id)
        if history and isinstance(history, list) and len(history) > 0:
            volumes[type_id] = history[-1].get('volume', 0)
        else:
            volumes[type_id] = 0
    return volumes

# --- NY FUNKSJON FOR Å ÅPNE MARKEDET I SPILLET ---
def open_market_window(type_id, access_token, status_callback=None): # Lagt til status_callback for å unngå krasj
    """Sender en kommando til ESI for å åpne markedsdetaljer for en vare i spillet."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {'type_id': type_id}
    url = f"{ESI_BASE_URL}/ui/openwindow/marketdetails/"
    
    try:
        response = esi_request(url, method='post', headers=headers, params=params)
        if response and response.status_code == 204: # 204 No Content er suksess for dette kallet
            logging.info(f"Signal for å åpne markedsvindu for type_id {type_id} sendt.")
            return True
        elif response:
            logging.error(f"Feil ved åpning av markedsvindu: {response.status_code} - {response.text}")
        return False
    except Exception as e:
        logging.error(f"En uventet feil oppstod under open_market_window: {e}")
        return False