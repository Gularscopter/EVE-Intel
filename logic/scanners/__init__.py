# ==============================================================================
# EVE INTEL - SCANNER PACKAGE INITIALIZER
# ==============================================================================
# Denne filen gjør "scanners"-mappen til en Python-pakke.
# Den fungerer også som en sentral (dispatcher) som importerer den faktiske
# logikken fra sine søstermoduler og kaller riktig funksjon.

# Relative importer fra andre filer i samme mappe (scanners/)
from .helpers import get_active_items_from_jita
from .bpo import run_bpo_scan
from .price_hunter import run_price_hunter_scan
from .route import run_route_scan
from .region import run_region_trading_scan
from .galaxy import run_galaxy_scan

def run_scan_thread(scan_config, progress_callback):
    """
    Hovedfunksjon som delegerer til riktig skanner basert på konfigurasjon.
    Denne funksjonen kalles fra UI-tråden.
    """
    scan_type = scan_config.get('scan_type')
    active_flag = scan_config.get('active_flag')

    # Noen skannere trenger ikke forhåndsfiltrering av varer
    if scan_type == 'price_hunter':
        run_price_hunter_scan(scan_config, progress_callback)
        return
        
    if scan_type == 'bpo_scanner':
        run_bpo_scan(scan_config, progress_callback)
        return
    
    # De fleste skannere drar nytte av å kun sjekke aktive varer
    item_ids = get_active_items_from_jita(progress_callback, active_flag, scan_type)
    if item_ids is None:
        # Hvis item_ids er None, betyr det at skannet ble avbrutt eller feilet.
        # Melding til brukeren er allerede sendt via progress_callback.
        return

    # Deleger til riktig undermodul basert på scan_type
    if scan_type == 'galaxy':
        run_galaxy_scan(scan_config, item_ids, progress_callback)
    elif scan_type == 'region_trading':
        run_region_trading_scan(scan_config, item_ids, progress_callback)
    elif scan_type in ['station', 'arbitrage']:
        # 'station' og 'arbitrage' bruker samme logikk, men med ulik konfigurasjon.
        run_route_scan(scan_config, item_ids, progress_callback)
