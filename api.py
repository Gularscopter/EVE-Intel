# ==============================================================================
# EVE MARKET VERKTØY - API-MODUL
# ==============================================================================
import requests
import config
import time
import db 

def fetch_blueprint_details(type_id):
    """
    Henter blueprint-detaljer fra den lokale SDE-databasen via db-modulen.
    """
    return db.get_blueprint_from_sde(type_id)

def fetch_industry_system_indices():
    if config.SYSTEM_INDICES_CACHE:
        return config.SYSTEM_INDICES_CACHE
    
    url = "https://esi.evetech.net/latest/industry/systems/?datasource=tranquility"
    response = fetch_esi_data(url)
    data = response.json() if response else None
    
    if data:
        for system_data in data:
            config.SYSTEM_INDICES_CACHE[system_data['solar_system_id']] = system_data
        return config.SYSTEM_INDICES_CACHE
    return None

def fetch_esi_data(url, token=None, page=None):
    headers = {'User-Agent': config.USER_AGENT}
    params = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    if page:
        params['page'] = page
        
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"ESI request failed for {url}: {e}")
        return None

def fetch_all_pages(url, token=None): ### ENDRET: token er valgfri
    all_results = []
    current_page = 1
    total_pages = 1

    while current_page <= total_pages:
        response = fetch_esi_data(url, token=token, page=current_page)
        if not response:
            break

        data = response.json()
        if not data:
            break
        all_results.extend(data)

        if current_page == 1:
            total_pages = int(response.headers.get('x-pages', 1))
        
        current_page += 1
        
    return all_results

### NY ###
def fetch_structure_market_orders(structure_id, token):
    """
    Henter alle markedsordrer fra en spesifikk, brukereid stasjon.
    Krever autentisering og at karakteren har docking-tilgang.
    """
    if not token:
        print("Token mangler for å hente data fra structure.")
        return None
        
    url = f"https://esi.evetech.net/latest/markets/structures/{structure_id}/"
    return fetch_all_pages(url, token)

### NY ###
def get_structure_details(structure_id, token):
    """Henter nøkkeldetaljer for en spesifikk struktur."""
    url = f"https://esi.evetech.net/latest/universe/structures/{structure_id}/?datasource=tranquility"
    response = fetch_esi_data(url, token=token)
    if not response:
        return None
        
    data = response.json()
    system_id = data.get('solar_system_id')
    if not system_id:
        return None

    system_name = db.get_system_name_from_sde(system_id)
    region_id = db.get_region_for_system(system_id)

    return {
        "name": data.get('name', 'Ukjent Navn'),
        "system_id": system_id,
        "system_name": system_name,
        "region_id": region_id
    }

def fetch_character_orders_paginated(character_id, token):
    url = f"https://esi.evetech.net/v1/characters/{character_id}/orders/"
    return fetch_all_pages(url, token)

def fetch_character_transactions_paginated(character_id, token):
    url = f"https://esi.evetech.net/v1/characters/{character_id}/wallet/transactions/"
    return fetch_all_pages(url, token)

def fetch_character_assets_paginated(character_id, token):
    url = f"https://esi.evetech.net/v5/characters/{character_id}/assets/"
    return fetch_all_pages(url, token)

# ==============================================================================
# === NY FUNKSJON FOR SKIPSLAST ===
# ==============================================================================
def fetch_character_ship(character_id, token):
    """Henter informasjon om spillerens aktive skip."""
    url = f"https://esi.evetech.net/v2/characters/{character_id}/ship/"
    response = fetch_esi_data(url, token=token)
    return response.json() if response else None
# ==============================================================================

def open_market_window_in_game(type_id, token):
    url = "https://esi.evetech.net/v1/ui/openwindow/marketdetails/"
    params = {'type_id': type_id}
    headers = {
        'User-Agent': config.USER_AGENT,
        'Authorization': f"Bearer {token}"
    }
    try:
        response = requests.post(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"ESI UI request failed: {e}")
        return False

def fetch_tokens_from_code(client_id, secret_key, code):
    url = "https://login.eveonline.com/v2/oauth/token"
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Host': 'login.eveonline.com'}
    data = {'grant_type': 'authorization_code', 'code': code}
    
    try:
        response = requests.post(url, headers=headers, data=data, auth=(client_id, secret_key))
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def refresh_esi_tokens(client_id, secret_key, refresh_token):
    url = "https://login.eveonline.com/v2/oauth/token"
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Host': 'login.eveonline.com'}
    data = {'grant_type': 'refresh_token', 'refresh_token': refresh_token}

    try:
        response = requests.post(url, headers=headers, data=data, auth=(client_id, secret_key))
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def fetch_market_orders(region_id, type_id):
    url = f"https://esi.evetech.net/latest/markets/{region_id}/orders/?datasource=tranquility&type_id={type_id}"
    response = fetch_esi_data(url)
    return response.json() if response else None

def fetch_esi_history(region_id, type_id):
    url = f"https://esi.evetech.net/latest/markets/{region_id}/history/?datasource=tranquility&type_id={type_id}"
    response = fetch_esi_data(url)
    return response.json() if response else None

def fetch_type_attributes(type_id):
    if type_id in config.TYPE_ATTRIBUTES_CACHE: 
        return config.TYPE_ATTRIBUTES_CACHE[type_id]
    
    name_from_sde = db.get_type_name_from_sde(type_id)
    if not name_from_sde.startswith("Ukjent"):
        url = f"https://esi.evetech.net/latest/universe/types/{type_id}/?datasource=tranquility"
        response = fetch_esi_data(url)
        data = response.json() if response else None
        if data: 
            config.TYPE_ATTRIBUTES_CACHE[type_id] = data
        return data
        
    url = f"https://esi.evetech.net/latest/universe/types/{type_id}/?datasource=tranquility"
    response = fetch_esi_data(url)
    data = response.json() if response else None
    if data: 
        config.TYPE_ATTRIBUTES_CACHE[type_id] = data
    return data

def fetch_fuzzwork_market_data(station_id, type_ids):
    url = "https://market.fuzzwork.co.uk/aggregates/"
    params = {'station': station_id, 'types': ",".join(map(str, type_ids))}
    headers = {'User-Agent': config.USER_AGENT}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return {}

def populate_all_regions_cache():
    if config.ALL_REGIONS_CACHE: return

    response = fetch_esi_data("https://esi.evetech.net/latest/universe/regions/")
    if not response: return
    region_ids = response.json()

    k_space_region_ids = [rid for rid in region_ids if str(rid).startswith('10')]
    for region_id in k_space_region_ids:
        region_response = fetch_esi_data(f"https://esi.evetech.net/latest/universe/regions/{region_id}/")
        if region_response:
            region_data = region_response.json()
            if region_data and 'name' in region_data:
                config.ALL_REGIONS_CACHE[region_data['name']] = region_id

### ENDRET ###
def get_station_name_with_cache(location_id):
    """
    Henter navnet på en lokasjon (stasjon eller struktur) med cache.
    Prøver først som stasjon, deretter som struktur.
    """
    if location_id in config.STATION_CACHE: 
        return config.STATION_CACHE[location_id]
    
    # Sjekk om det er en pre-definert hub
    for name, info in config.STATIONS_INFO.items():
        if info['id'] == location_id:
            config.STATION_CACHE[location_id] = name
            return name
            
    # Forsøk å hente som NPC-stasjon først
    station_url = f"https://esi.evetech.net/latest/universe/stations/{location_id}/"
    response = fetch_esi_data(station_url)
    if response:
        data = response.json()
        if data and 'name' in data:
            name = data['name']
            config.STATION_CACHE[location_id] = name
            return name
            
    # Hvis det feilet, forsøk å hente som brukereid stasjon
    # Dette krever token, som vi ikke har universell tilgang til her.
    # Vi stoler derfor på at navnet er cachet fra et annet sted (f.eks. asset-listen)
    # ELLER at brukeren legger det til manuelt.
    # For robusthet, kaller vi ikke ESI her, men en bedre app ville sendt token.
    # Fallback:
    name_not_found = f"Lokasjon ID: {location_id}"
    config.STATION_CACHE[location_id] = name_not_found
    return name_not_found

def get_stations_in_region(region_id):
    major_hubs_in_region = {}
    for station_name, station_info in config.STATIONS_INFO.items():
        if station_info['region_id'] == region_id:
            major_hubs_in_region[station_info['id']] = station_name
    
    if major_hubs_in_region:
        print(f"Fokusert skann: Fant {len(major_hubs_in_region)} handelshub(er) i region {region_id}.")
        return major_hubs_in_region

    print(f"Dypt skann: Ingen kjente huber funnet i region {region_id}. Starter fullt stasjonssøk...")
    systems_url = f"https://esi.evetech.net/latest/universe/regions/{region_id}/"
    region_response = fetch_esi_data(systems_url)
    if not region_response: return {}
    
    region_data = region_response.json()
    if not region_data or 'systems' not in region_data: return {}

    all_stations = {}
    systems_in_region = region_data.get('systems', [])
    
    for system_id in systems_in_region:
        system_response = fetch_esi_data(f"https://esi.evetech.net/latest/universe/systems/{system_id}/")
        if system_response:
            system_data = system_response.json()
            if system_data and 'stations' in system_data:
                for station_id in system_data['stations']:
                    station_info = get_station_name_with_cache(station_id)
                    if station_info != str(station_id): 
                        all_stations[station_id] = station_info
        
        time.sleep(0.05)
        
    return all_stations