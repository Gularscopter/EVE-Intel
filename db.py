import pandas as pd
import logging
import os

DB_FILE = 'invTypes.csv'
_items_df = None
_name_to_id = {}
_id_to_name = {}
_id_to_volume = {}

def initialize_database():
    """
    Laster inn item-data fra invTypes.csv i minnet for rask tilgang.
    """
    global _items_df, _name_to_id, _id_to_name, _id_to_volume

    if not os.path.exists(DB_FILE):
        logging.critical(f"Database file not found: {DB_FILE}. Application cannot function.")
        raise FileNotFoundError(f"Required database file '{DB_FILE}' not found.")

    try:
        logging.info(f"Loading database file: {DB_FILE}...")
        # Laster kun kolonner vi vet finnes i invTypes.csv. Dette fikser krasjen.
        _items_df = pd.read_csv(
            DB_FILE,
            usecols=['typeID', 'typeName', 'volume', 'marketGroupID'],
            dtype={
                'typeID': 'Int64', 'typeName': 'str', 'volume': 'float64', 
                'marketGroupID': 'Int64'
            },
            on_bad_lines='skip' # Hopper over dårlige linjer for robusthet
        ).dropna(subset=['typeName'])
        
        # Lag oppslags-ordbøker for rask tilgang
        _id_to_name = pd.Series(_items_df.typeName.values, index=_items_df.typeID).to_dict()
        _name_to_id = {v: k for k, v in _id_to_name.items()}
        _id_to_volume = pd.Series(_items_df.volume.values, index=_items_df.typeID).to_dict()

        logging.info("Database initialized successfully.")
    except ValueError as e:
        # Gir en mer hjelpsom feilmelding hvis kolonnene fortsatt er feil.
        if "Usecols do not match columns" in str(e):
             logging.critical(f"A column in {['typeID', 'typeName', 'volume', 'marketGroupID']} was not found in {DB_FILE}. Please check the CSV file headers. Error: {e}", exc_info=True)
        else:
            logging.critical(f"A value error occurred while initializing database from {DB_FILE}: {e}", exc_info=True)
        raise
    except Exception as e:
        logging.critical(f"An unexpected error occurred while initializing the database: {e}", exc_info=True)
        raise

def get_item_name(type_id):
    """Henter varenavn fra minnet basert på typeID."""
    return _id_to_name.get(type_id)

def get_item_id(name):
    """Henter typeID fra minnet basert på varenavn."""
    return _name_to_id.get(name)

def get_item_volume(type_id):
    """Henter volum fra minnet basert på typeID."""
    return _id_to_volume.get(type_id)
    
def get_item_names(type_ids):
    """Henter flere varenavn effektivt."""
    return {tid: _id_to_name.get(tid) for tid in type_ids if tid in _id_to_name}

# Kjør initialisering når modulen importeres
initialize_database()
