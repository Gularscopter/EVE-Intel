# ==============================================================================
# EVE MARKET VERKTØY - HOVEDFIL
# ==============================================================================
import sys
# ENDRET IMPORT-LINJE:
from ui.main_app import EveMarketApp
from config import load_items_from_file, load_settings

def main():
    """
    Hovedfunksjon for å starte EVE Market Verktøy.
    Laster inn nødvendige data og starter GUI-loopen.
    """
    # 1. Last inn kritiske varedata. Avslutt hvis det feiler.
    if not load_items_from_file():
        sys.exit(1)

    # 2. Last inn lagrede innstillinger fra config-filen.
    app_settings = load_settings()

    # 3. Opprett og kjør applikasjonen.
    app = EveMarketApp(settings_dict=app_settings)
    app.mainloop()

if __name__ == "__main__":
    main()