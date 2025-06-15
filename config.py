# ==============================================================================
# EVE MARKET VERKTØY - KONFIGURASJONSMODUL
# ==============================================================================
import json
from tkinter import messagebox
import customtkinter as ctk

# --- FILNAVN OG KONSTANTER ---
ITEMS_FILE = 'items_filtered.json'
CONFIG_FILE = 'app_config.json'
USER_AGENT = 'EVE-Complete-Tool/Final (PythonApp)'
EXCELLENT_DEAL_MARGIN = 20.0
GOOD_DEAL_MARGIN = 10.0
GOLDEN_DEAL_MIN_VOLUME = 500
GOLDEN_DEAL_MAX_COMPETITION = 10

# --- DATA-Strukturer / Caches ---
STATIONS_INFO = {
    "Jita": {"id": 60003760, "region_id": 10000002, "system_id": 30000142},
    "Dodixie": {"id": 60011866, "region_id": 10000032, "system_id": 30002659},
    "Amarr": {"id": 60008494, "region_id": 10000043, "system_id": 30002187},
    "Hek": {"id": 60004588, "region_id": 10000042, "system_id": 30002053},
    "Rens": {"id": 60004548, "region_id": 10000030, "system_id": 30002510}
}
ITEM_NAME_TO_ID = {}
ITEM_LOOKUP_LOWERCASE = {}
TYPE_ATTRIBUTES_CACHE = {}
ALL_REGIONS_CACHE = {}
STATION_CACHE = {}
SYSTEM_INDICES_CACHE = {}

# --- FUNKSJONER ---
def load_items_from_file():
    """Laster inn varelisten fra JSON-filen."""
    global ITEM_NAME_TO_ID, ITEM_LOOKUP_LOWERCASE
    try:
        with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
            ITEM_NAME_TO_ID = json.load(f)
            ITEM_LOOKUP_LOWERCASE = {k.lower(): v for k, v in ITEM_NAME_TO_ID.items()}
        print(f"Lastet {len(ITEM_NAME_TO_ID)} varer fra {ITEMS_FILE}")
        return True
    except (FileNotFoundError, json.JSONDecodeError):
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror("Kritisk Feil", f"Fant ikke filen '{ITEMS_FILE}'.\n\nProgrammet kan ikke starte uten denne.\nKjør et skript for å generere den først.", parent=root)
        root.destroy()
        return False

# ==============================================================================
# === NY FUNKSJON FOR Å LAGRE VARELISTEN ===
# ==============================================================================
def save_item_list():
    """Lagrer den nåværende varelisten (ITEM_NAME_TO_ID) til fil."""
    try:
        with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
            # Sorterer ordboken alfabetisk før lagring for en penere fil
            sorted_items = dict(sorted(ITEM_NAME_TO_ID.items()))
            json.dump(sorted_items, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Kunne ikke lagre varelisten til {ITEMS_FILE}: {e}")
# ==============================================================================

def load_settings():
    try:
        with open(CONFIG_FILE, 'r') as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}

    defaults = {
        "analyse_buy_station": "Jita", "analyse_sell_station": "Amarr", "analyse_sell_method": "Kjøpsordre",
        "analyse_ship_cargo": "4000.0", "analyse_item_name": "Tritanium",
        "scanner_buy_station": "Jita", "scanner_sell_station": "Amarr",
        "scanner_min_profit": "1000000", "scanner_min_volume": "10",
        "scanner_ship_cargo": "4000", "scanner_max_investment": "100000000",
        "arbitrage_buy_station": "Jita", "arbitrage_sell_station": "Amarr",
        "arbitrage_min_profit": "1000000", "arbitrage_min_volume": "10",
        "arbitrage_ship_cargo": "4000", "arbitrage_max_investment": "100000000",
        "region_station": "Jita", "region_min_profit": "50000",
        "region_min_volume": "100", "region_max_investment": "100000000",
        "galaxy_home_base": "Jita", "galaxy_target_region": "The Forge",
        "galaxy_min_profit": "2000000", "galaxy_min_volume": "10",
        "galaxy_ship_cargo": "4000", "galaxy_max_investment": "100000000",
        "sales_tax": "8.0", "brokers_fee": "3.0",
        "esi_client_id": "", "esi_secret_key": "",
        "access_token": None, "refresh_token": None, "token_expiry": None,
        "user_structures": []
    }
    
    for key, value in defaults.items():
        settings.setdefault(key, value)
        
    return settings

def save_settings(settings_dict):
    """Lagrer innstillinger til config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_dict, f, indent=4)
    except IOError as e:
        print(f"Kunne ikke lagre innstillinger til {CONFIG_FILE}: {e}")