import json
import os
import logging

CONFIG_FILE = 'app_config.json'
_config = {}

def load_config():
    """Laster konfigurasjon fra fil inn i minnet. Kjøres en gang ved oppstart."""
    global _config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                _config = json.load(f)
                logging.info(f"Configuration loaded from {CONFIG_FILE}")
        except json.JSONDecodeError:
            logging.error(f"Could not decode JSON from {CONFIG_FILE}. Using default empty config.")
            _config = {}
    else:
        logging.warning(f"{CONFIG_FILE} not found. A new one will be created on save.")
        _config = {}
    return _config

def save_config(config_data=None):
    """Lagrer gjeldende konfigurasjon til fil."""
    data_to_save = _config if config_data is None else config_data
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=4)
            logging.info(f"Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        logging.error(f"Failed to save config to {CONFIG_FILE}: {e}")

def get_config_value(key, default=None):
    """Henter en verdi fra minne-konfigurasjonen."""
    return _config.get(key, default)

def set_config_value(key, value):
    """Setter en verdi i minne-konfigurasjonen og lagrer til fil."""
    _config[key] = value
    save_config()

# Last inn konfigurasjonen automatisk når denne modulen importeres første gang
load_config()
