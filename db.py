import sqlite3
import config
import json
import logging
import os
from collections import deque, defaultdict # ENDRING: La til defaultdict i importen

# Build the absolute path to the database file, assuming it's in the same directory as this script.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sde.sqlite.db')

# Cache for SDE data to avoid repeated queries within a session
_jump_graph = None
_system_security_map = None
_path_cache = {} # Cache for beregnede ruter

def connect_to_sde():
    """Oppretter en tilkobling til SDE-databasen."""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Databasefeil: {e}")
        return None

def _get_jump_graph():
    """Hjelpefunksjon for å laste og cache system-hopp-grafen fra SDE."""
    global _jump_graph
    if _jump_graph is not None:
        return _jump_graph

    conn = connect_to_sde()
    if not conn: return {}
    
    _jump_graph = {}
    try:
        cursor = conn.cursor()
        # Bygger en adjacency list for alle system-til-system-forbindelser
        cursor.execute("SELECT fromSolarSystemID, toSolarSystemID FROM mapSolarSystemJumps")
        for from_system, to_system in cursor.fetchall():
            if from_system not in _jump_graph:
                _jump_graph[from_system] = []
            if to_system not in _jump_graph:
                _jump_graph[to_system] = []
            _jump_graph[from_system].append(to_system)
            _jump_graph[to_system].append(from_system)
        logging.info(f"Loaded jump graph for {_jump_graph.keys().__len__()} systems.")
        return _jump_graph
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved lasting av jump graph: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def calculate_shortest_path(start_system_id, end_system_id):
    """Beregner korteste antall hopp mellom to systemer ved hjelp av BFS."""
    if start_system_id == end_system_id:
        return 0
    
    # Bruk cache for å unngå å beregne samme rute flere ganger
    cache_key = tuple(sorted((start_system_id, end_system_id)))
    if cache_key in _path_cache:
        return _path_cache[cache_key]
        
    jump_graph = _get_jump_graph()
    if not start_system_id in jump_graph or not end_system_id in jump_graph:
        return None 

    queue = deque([(start_system_id, 0)])
    visited = {start_system_id}

    while queue:
        current_system, jumps = queue.popleft()

        if current_system == end_system_id:
            _path_cache[cache_key] = jumps # Lagre resultatet i cachen
            return jumps

        for neighbor in jump_graph.get(current_system, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, jumps + 1))
    
    _path_cache[cache_key] = None # Lagre at rute ikke finnes
    return None

def get_distance_matrix(system_ids):
    """Bygger en komplett avstandsmatrise for en gitt liste med systemer."""
    matrix = defaultdict(dict)
    unique_ids = list(set(system_ids))
    for i in range(len(unique_ids)):
        for j in range(i, len(unique_ids)):
            start_node = unique_ids[i]
            end_node = unique_ids[j]
            distance = calculate_shortest_path(start_node, end_node)
            if distance is not None:
                matrix[start_node][end_node] = distance
                matrix[end_node][start_node] = distance
    return matrix

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
            
def get_item_id(name):
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

def get_system_names(system_ids):
    """Henter systemnavn for en liste med systemIDs."""
    if not system_ids: return {}
    conn = connect_to_sde()
    if not conn: return {}
    try:
        placeholders = ','.join('?' for _ in system_ids)
        query = f"SELECT solarSystemID, solarSystemName FROM mapSolarSystems WHERE solarSystemID IN ({placeholders})"
        cursor = conn.cursor()
        cursor.execute(query, tuple(system_ids))
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av systemnavn: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_item_volume(type_id):
    """Henter volumet til en vare basert på typeID."""
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
    """
    Henter materialkravene for et produkt fra SDE.
    Dette forutsetter at produktet har en produksjons-blueprint.
    """
    conn = connect_to_sde()
    if not conn: return None
    try:
        cursor = conn.cursor()
        # Finner blueprint typeID basert på produktets typeID (activityID 1 = produksjon)
        query = """
        SELECT T2.typeID
        FROM industryActivityProducts AS T1
        JOIN invTypes AS T2 ON T1.typeID = T2.typeID
        WHERE T1.productTypeID = ? AND T1.activityID = 1
        """
        cursor.execute(query, (product_type_id,))
        blueprint = cursor.fetchone()
        if not blueprint:
            return None # Ingen blueprint funnet for dette produktet
        
        blueprint_type_id = blueprint[0]

        # Henter materialer for den funnede blueprinten
        material_query = """
        SELECT T2.typeName, T1.quantity
        FROM industryActivityMaterials AS T1
        JOIN invTypes AS T2 ON T1.materialTypeID = T2.typeID
        WHERE T1.typeID = ? AND T1.activityID = 1
        """
        cursor.execute(material_query, (blueprint_type_id,))
        
        materials = {row[0]: row[1] for row in cursor.fetchall()}
        return materials
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av blueprint-data: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_all_system_security():
    """Henter en ordbok som mapper systemID til security status."""
    global _system_security_map
    if _system_security_map is not None:
        return _system_security_map
    
    conn = connect_to_sde()
    if not conn: return {}
    
    _system_security_map = {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemID, security FROM mapSolarSystems")
        _system_security_map = {row[0]: row[1] for row in cursor.fetchall()}
        return _system_security_map
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av system-security: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_all_manufacturable_item_names():
    """
    Henter en sortert liste med navn på alle varer som kan produseres fra blueprints
    i en enkelt, effektiv database-spørring.
    """
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT t.typeName
            FROM invTypes t
            JOIN industryActivityProducts p ON t.typeID = p.productTypeID
            JOIN industryActivity a ON p.typeID = a.typeID
            WHERE a.activityID = 1 -- 1 for Manufacturing
              AND t.published = 1
            ORDER BY t.typeName ASC;
        """)
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av produserbare varenavn: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_manufacturable_item_ids():
    """
    Henter en liste med typeIDs for alle varer som er produkter av en blueprint.
    """
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
    """Laster en liste med vare-IDer fra items_filtered.json."""
    try:
        with open('items_filtered.json', 'r') as f:
            item_names = json.load(f)
            return [get_item_id(name) for name in item_names if get_item_id(name) is not None]
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def get_item_name(type_id):
    """Henter varenavn for en gitt typeID."""
    # Sjekk om DB_PATH er satt
    if not DB_PATH:
        logging.error("Database path not configured.")
        return "Unknown"
        
    conn = connect_to_sde()
    if not conn:
        logging.error("Failed to connect to the database in get_item_name.")
        return "Unknown"
        
    try:
        # Bruk en 'with'-statement for å sikre at tilkoblingen lukkes
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT typeName FROM invTypes WHERE typeID=?", (type_id,))
            result = cursor.fetchone()
            return result[0] if result else "Unknown"
    except sqlite3.Error as e:
        logging.error(f"Database error in get_item_name: {e}")
        return "Unknown"

def get_all_item_name_id_map():
    """Henter en ordbok som mapper alle publiserte varenavn til deres typeID."""
    conn = connect_to_sde()
    if not conn: return {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeName, typeID FROM invTypes WHERE published = 1")
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error as e:
        logging.error(f"SQL-feil ved henting av varenavn-ID-map: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def get_item_id_by_name(item_name):
    """Fetches the item ID for a given item name from the database."""
    conn = connect_to_sde()
    if conn is None:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeID FROM invTypes WHERE typeName = ?", (item_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Error fetching item ID for '{item_name}': {e}")
        return None
    finally:
        conn.close()