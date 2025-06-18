import sqlite3
import config
import json
import logging
import os

DB_FILE = 'sde.sqlite.db'

def connect_to_sde():
    """Oppretter en tilkobling til SDE-databasen."""
    try:
        conn = sqlite3.connect(f'file:{DB_FILE}?mode=ro', uri=True)
        return conn
    except sqlite3.Error as e:
        print(f"Databasefeil: {e}")
        return None

def get_all_region_names():
    """Henter en sortert liste med alle regionnavn fra SDE."""
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT regionName FROM mapRegions ORDER BY regionName ASC")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av regionnavn: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_regions():
    """Henter en liste med ordbøker for alle regioner (ID og Navn)."""
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT regionID, regionName FROM mapRegions")
        return [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av alle regioner: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_item_names():
    """Henter en liste med alle publiserte varenavn fra SDE for autofullfør."""
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeName FROM invTypes WHERE published = 1 ORDER BY typeName ASC")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av alle varenavn: {e}")
        return []
    finally:
        if conn:
            conn.close()
            
def get_item_id_by_name(name):
    """Henter en vares typeID basert på navnet."""
    conn = connect_to_sde()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeID FROM invTypes WHERE typeName = ? COLLATE NOCASE", (name,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        if conn:
            conn.close()

def get_station_to_system_map():
    """Henter en ordbok som mapper stationID til solarSystemID for alle stasjoner."""
    conn = connect_to_sde()
    if not conn: return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT stationID, solarSystemID FROM staStations")
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av stasjons-mapping: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_type_name_from_sde(type_id):
    """Henter navnet på en vare fra SDE basert på typeID."""
    conn = connect_to_sde()
    if not conn: return f"Ukjent Vare ID: {type_id}"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeName FROM invTypes WHERE typeID=?", (type_id,))
        result = cursor.fetchone()
        return result[0] if result else f"Ukjent Vare ID: {type_id}"
    finally:
        if conn:
            conn.close()

def get_item_names(type_ids):
    """Henter navn for en liste med typeIDs i en enkelt, effektiv database-spørring."""
    if not type_ids: return {}
    conn = connect_to_sde()
    if not conn: return {}
    try:
        placeholders = ','.join('?' for _ in type_ids)
        query = f"SELECT typeID, typeName FROM invTypes WHERE typeID IN ({placeholders})"
        cursor = conn.cursor()
        cursor.execute(query, tuple(type_ids))
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av flere varenavn: {e}")
        return {}
    finally:
        if conn:
            conn.close()
            
def get_station_names(station_ids):
    """Henter stasjonsnavn for en liste med stationIDs."""
    if not station_ids: return {}
    conn = connect_to_sde()
    if not conn: return {}
    try:
        placeholders = ','.join('?' for _ in station_ids)
        query = f"SELECT stationID, stationName FROM staStations WHERE stationID IN ({placeholders})"
        cursor = conn.cursor()
        cursor.execute(query, tuple(station_ids))
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av stasjonsnavn: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_system_name(system_id):
    """Henter navnet på et solsystem fra SDE."""
    conn = connect_to_sde()
    if not conn: return "Ukjent"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemName FROM mapSolarSystems WHERE solarSystemID=?", (system_id,))
        result = cursor.fetchone()
        return result[0] if result else "Ukjent"
    finally:
        if conn:
            conn.close()

def get_item_volume(type_id):
    """Henter volumet til en vare fra SDE."""
    conn = connect_to_sde()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT volume FROM invTypes WHERE typeID=?", (type_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        if conn:
            conn.close()

def get_blueprint_from_sde(product_type_id):
    """Henter en komplett blueprint-oppskrift fra SDE-databasen."""
    conn = connect_to_sde()
    if not conn: return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeID, time FROM industryActivity WHERE productTypeID=? AND activityID=1", (product_type_id,))
        bpo_info = cursor.fetchone()
        if not bpo_info: return None
        blueprint_type_id, time = bpo_info
        cursor.execute("SELECT materialTypeID, quantity FROM industryActivityMaterials WHERE typeID=?", (blueprint_type_id,))
        materials = [{'typeID': r[0], 'quantity': r[1]} for r in cursor.fetchall()]
        cursor.execute("SELECT productTypeID, quantity FROM industryActivityProducts WHERE typeID=?", (blueprint_type_id,))
        products = [{'typeID': r[0], 'quantity': r[1]} for r in cursor.fetchall()]
        return {'blueprint_id': blueprint_type_id, 'time': time, 'materials': materials, 'products': products}
    finally:
        if conn:
            conn.close()

def get_all_system_security():
    """Henter security status for alle solsystemer."""
    all_systems = {}
    conn = connect_to_sde()
    if not conn: return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemID, security FROM mapSolarSystems")
        results = cursor.fetchall()
        for system_id, security_status in results:
            all_systems[system_id] = security_status
        return all_systems
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av security status: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_all_manufacturable_item_ids():
    """Henter en liste med tupler (productTypeID, blueprintTypeID) for alle produserbare varer fra SDE."""
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT T2.productTypeID, T2.typeID FROM invTypes AS T1 JOIN industryActivityProducts AS T2 ON T1.typeID = T2.typeID WHERE T2.activityID = 1 AND T1.published = 1")
        return list(set(cursor.fetchall()))
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av produserbare varer: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_filtered_item_ids():
    """Laster listen med vare-IDer fra den forhåndsfiltrerte JSON-filen."""
    try:
        path = config.get('filtered_items_path', 'items_filtered.json')
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict): return [int(type_id) for type_id in data.values()]
            elif isinstance(data, list): return [item['typeID'] for item in data if isinstance(item, dict) and 'typeID' in item]
            else: return []
    except FileNotFoundError:
        logging.error(f"Filtered items file not found. Please generate it via the Settings tab.")
        return []
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logging.error(f"Error reading or parsing filtered items file: {e}")
        return []