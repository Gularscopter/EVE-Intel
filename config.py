import json
import logging

_config = {}

# --- Statisk data ---
STATIONS_INFO = {
    "Jita": {"id": 60003760, "region_id": 10000002, "system_id": 30000142},
    "Amarr": {"id": 60008494, "region_id": 10000043, "system_id": 30002187},
    "Dodixie": {"id": 60011866, "region_id": 10000032, "system_id": 30002659},
    "Rens": {"id": 60004588, "region_id": 10000030, "system_id": 30002187},
    "Hek": {"id": 60005686, "region_id": 10000042, "system_id": 30002053},
}

# --- SCOPE-LISTE ENDRET I HENHOLD TIL DIN SISTE GUIDE ---
EVE_SCOPES = " ".join([
    "publicData",
    "esi-location.read_location.v1",
    "esi-location.read_ship_type.v1",
    "esi-wallet.read_character_wallet.v1",
    "esi-search.search_structures.v1",
    "esi-universe.read_structures.v1",
    "esi-assets.read_assets.v1",
    "esi-ui.open_window.v1",
    "esi-markets.structure_markets.v1",
    "esi-industry.read_character_jobs.v1",
    "esi-markets.read_character_orders.v1",
    "esi-location.read_online.v1",
    "esi-industry.read_corporation_jobs.v1",
    "esi-industry.read_character_mining.v1",
    "esi-industry.read_corporation_mining.v1",
    "esi-ui.write_waypoint.v1" # Endret i henhold til din siste guide
])
# ----------------------------------------------------

def load_config():
    global _config
    try:
        with open('app_config.json', 'r') as f:
            _config = json.load(f)
        logging.info("Configuration loaded from app_config.json")
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning("app_config.json not found or invalid. Using default/empty config.")
        _config = {
            "client_id": "",
            "filtered_items_path": "items_filtered.json",
            "invTypes_path": "invTypes.csv"
        }

def get(key, default=None):
    if not _config:
        load_config()
    return _config.get(key, default)

def set(key, value):
    if not _config:
        load_config()
    _config[key] = value

def save_config():
    with open('app_config.json', 'w') as f:
        json.dump(_config, f, indent=4)
    logging.info("Configuration saved to app_config.json")