import sys
import os

# Add the project root to the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import logging
from PyQt6.QtWidgets import QApplication
from ui.main_app import EveMarketApp
import db

def main():
    """
    Hovedfunksjonen for EVE-Intel-applikasjonen.
    """
    # Konfigurerer logging for å vise meldinger i terminalen
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    try:
        # FJERNET: db.init_db() - Denne funksjonen finnes ikke i din db.py
        # logging.info("Database initialisert.") 

        app = QApplication(sys.argv)
        
        window = EveMarketApp()
        window.show()
        
        logging.info("Applikasjon startet vellykket.")
        sys.exit(app.exec())

    except Exception as e:
        logging.critical(f"En kritisk feil oppstod under oppstart: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main()