import sys
import logging
from PyQt6.QtWidgets import QApplication
from ui.main_app import EveMarketApp
import config

def main():
    """Hovedfunksjon for å starte applikasjonen."""
    # Sett opp logging for å fange feil og informasjon
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Last inn konfigurasjonen fra app_config.json
    # Funksjonen i config.py kjøres automatisk når den importeres,
    # men vi kan kalle den eksplisitt her for klarhetens skyld.
    config.load_config()

    # Opprett Qt-applikasjonen
    app = QApplication(sys.argv)
    
    # Opprett og vis hovedvinduet
    window = EveMarketApp()
    window.show()
    
    # Start applikasjonens event-loop
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
