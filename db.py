# ==============================================================================
# EVE MARKET VERKTØY - DATABASE-MODUL (SDE)
# ==============================================================================
import sqlite3
import config

DB_FILE = 'sde.sqlite.db'

def connect_to_sde():
    """Oppretter en tilkobling til SDE-databasen."""
    try:
        conn = sqlite3.connect(f'file:{DB_FILE}?mode=ro', uri=True)
        return conn
    except sqlite3.Error as e:
        print(f"Databasefeil: {e}")
        return None

def get_type_name_from_sde(type_id):
    """Henter navnet på en vare fra SDE basert på typeID."""
    conn = connect_to_sde()
    if not conn:
        return f"Ukjent Vare ID: {type_id}"
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT typeName FROM invTypes WHERE typeID=?", (type_id,))
        result = cursor.fetchone()
        return result[0] if result else f"Ukjent Vare ID: {type_id}"
    finally:
        conn.close()

def get_blueprint_from_sde(product_type_id):
    """
    Henter en komplett blueprint-oppskrift fra SDE-databasen
    basert på ID-en til produktet som skal lages.
    """
    conn = connect_to_sde()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT typeID FROM industryActivityProducts WHERE productTypeID=? AND activityID=1", (product_type_id,))
        bpo_result = cursor.fetchone()
        if not bpo_result:
            return None 
        
        blueprint_type_id = bpo_result[0]

        cursor.execute("SELECT time FROM industryActivity WHERE typeID=? AND activityID=1", (blueprint_type_id,))
        time_result = cursor.fetchone()
        
        cursor.execute("""
            SELECT materialTypeID, quantity 
            FROM industryActivityMaterials 
            WHERE typeID=? AND activityID=1
        """, (blueprint_type_id,))
        materials_result = cursor.fetchall()

        cursor.execute("""
            SELECT productTypeID, quantity 
            FROM industryActivityProducts 
            WHERE typeID=? AND activityID=1
        """, (blueprint_type_id,))
        products_result = cursor.fetchall()

        if not time_result or not materials_result or not products_result:
            return None

        bp_data = {
            "blueprintTypeID": blueprint_type_id, # Inkluderer BPO ID
            "adjustedprice": 0, # Dette må hentes fra en annen kilde, men vi lar det være
            "activities": {
                "manufacturing": {
                    "time": time_result[0],
                    "materials": [{"typeID": m[0], "quantity": m[1]} for m in materials_result],
                    "products": [{"typeID": p[0], "quantity": p[1]} for p in products_result]
                }
            }
        }
        return bp_data

    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av blueprint: {e}")
        return None
    finally:
        conn.close()

def get_system_id_from_name(system_name):
    """Henter solarSystemID fra SDE basert på systemnavn."""
    conn = connect_to_sde()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemID FROM mapSolarSystems WHERE solarSystemName LIKE ?", (system_name,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av system-ID: {e}")
        return None
    finally:
        conn.close()

def get_system_name_from_sde(system_id):
    """Henter navnet på et solsystem fra SDE basert på solarSystemID."""
    conn = connect_to_sde()
    if not conn:
        return f"Ukjent System ID: {system_id}"
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemName FROM mapSolarSystems WHERE solarSystemID=?", (system_id,))
        result = cursor.fetchone()
        return result[0] if result else f"Ukjent System ID: {system_id}"
    finally:
        conn.close()

def get_region_for_system(system_id):
    """Henter regionID for et gitt solarSystemID fra SDE."""
    conn = connect_to_sde()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT regionID FROM mapSolarSystems WHERE solarSystemID=?", (system_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av region for system: {e}")
        return None
    finally:
        conn.close()

def get_all_manufacturable_products_and_bpos():
    """Henter en liste med tupler (productTypeID, blueprintTypeID) for alle produserbare varer."""
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        # Henter produkt-ID og tilhørende BPO-ID for alle produksjonsoppskrifter
        cursor.execute("SELECT productTypeID, typeID FROM industryActivityProducts WHERE activityID=1")
        results = cursor.fetchall()
        # Filtrer ut unike, da noen BPO-er kan lage flere ting (sjeldent for produksjon)
        return list(set(results))
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av alle produserbare varer: {e}")
        return []
    finally:
        conn.close()

def get_all_system_security_statuses():
    """Henter en dictionary med security status for alle solsystemer."""
    conn = connect_to_sde()
    if not conn: return {}
    all_systems = {}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT solarSystemID, ROUND(security, 1) FROM mapSolarSystems")
        results = cursor.fetchall()
        for system_id, security_status in results:
            all_systems[system_id] = security_status
        return all_systems
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av security status: {e}")
        return {}
    finally:
        conn.close()

# ==============================================================================
# === NY FUNKSJON FOR BPO-SCANNER ===
# ==============================================================================
def get_all_manufacturable_item_ids():
    """
    Henter en liste med tupler (productTypeID, blueprintTypeID) for alle 
    produserbare varer fra SDE.
    """
    conn = connect_to_sde()
    if not conn: return []
    try:
        cursor = conn.cursor()
        # Henter produkt-ID og tilhørende BPO-ID for alle produksjonsoppskrifter.
        # Vi joiner med invTypes for å sikre at blueprinten er publisert og kan selges på markedet.
        cursor.execute("""
            SELECT T2.productTypeID, T2.typeID 
            FROM invTypes AS T1
            JOIN industryActivityProducts AS T2 ON T1.typeID = T2.typeID
            WHERE T2.activityID = 1 AND T1.published = 1
        """)
        results = cursor.fetchall()
        # Filtrer ut unike resultater
        return list(set(results))
    except sqlite3.Error as e:
        print(f"SQL-feil ved henting av alle produserbare varer: {e}")
        return []
    finally:
        conn.close()