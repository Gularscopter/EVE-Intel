import json
import logging
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTabWidget,
                             QDockWidget, QTextEdit, QMenuBar)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from auth import authenticate_and_get_token, refresh_access_token
from api import get_character_id, get_character_name
from config import load_config, save_config
from ui.tabs.character import CharacterTab
from ui.tabs.assets import AssetsTab
from ui.tabs.price_hunter import PriceHunterTab
from ui.tabs.region_scanner import RegionScannerTab
from ui.tabs.route_scanners import RouteScannerTab
from ui.tabs.bpo_scanner import BPOScannerTab
from ui.tabs.galaxy_scanner import GalaxyScannerTab
from ui.tabs.analyse import AnalyseTab
from ui.tabs.manufacturing import ManufacturingTab
from ui.tabs.settings import SettingsTab

class EveMarketApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVE-Intel")
        self.setGeometry(100, 100, 1600, 900)
        
        logging.info("[DEBUG] MainApp: Initializing.")
        self.config = load_config()
        self.access_token = None
        self.character_id = None
        self.character_name = "Not Authenticated"
        self.token_data = None

        self.init_ui()
        logging.info("[DEBUG] MainApp: UI Initialized.")
        
        QTimer.singleShot(100, self.initialize_auth_on_startup)
        logging.info("[DEBUG] MainApp: Scheduled auto-authentication check.")

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.create_docks()
        self.create_menus()
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        self.add_tabs()
        self.update_status_bar("Ready. Please log in.")

    def initialize_auth_on_startup(self):
        logging.info("[DEBUG] Auth: Starting automatic token refresh on startup.")
        try:
            with open('token.json', 'r') as f:
                self.token_data = json.load(f)
            refresh_token_val = self.token_data.get('refresh_token')
            if not refresh_token_val:
                raise ValueError("Refresh token not found.")

            self.update_status_bar("Refreshing authentication token...")
            new_token_data = refresh_access_token(refresh_token_val)
            
            if new_token_data:
                self.process_successful_auth(new_token_data)
            else:
                raise ValueError("Token refresh failed.")
        except (FileNotFoundError, ValueError, KeyError) as e:
            logging.warning(f"[DEBUG] Auth: Could not auto-refresh token ({e}). Ready for manual login.")

    def trigger_full_authentication(self):
        logging.info("[DEBUG] Auth: Manual login triggered by button click.")
        self.update_status_bar("Please authenticate via the browser...")
        new_token_data = authenticate_and_get_token()
        logging.info(f"[DEBUG] Auth: authenticate_and_get_token returned: {'Token data received' if new_token_data else 'None'}")
        if new_token_data:
            self.process_successful_auth(new_token_data)
        else:
            self.update_status_bar("Authentication cancelled or failed.")
            self.log_message("Authentication was not completed.")

    def process_successful_auth(self, token_data):
        logging.info("[DEBUG] Auth: Processing successful authentication...")
        if not token_data or 'access_token' not in token_data:
            logging.error("[DEBUG] Auth: CRITICAL - process_successful_auth called with invalid token_data.")
            return

        self.token_data = token_data
        with open('token.json', 'w') as f: json.dump(self.token_data, f)
        logging.info("[DEBUG] Auth: Token data saved to token.json.")
        
        self.access_token = self.token_data.get('access_token')
        self.character_id = get_character_id(self.access_token)
        logging.info(f"[DEBUG] Auth: Character ID fetched: {self.character_id}")
        self.character_name = get_character_name(self.character_id) if self.character_id else "Unknown"
        logging.info(f"[DEBUG] Auth: Character Name fetched: {self.character_name}")
        
        self.update_status_bar(f"Successfully authenticated as: {self.character_name}")
        self.post_auth_update()

    def post_auth_update(self):
        logging.info("[DEBUG] UI: Starting post-authentication update.")
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, 'load_character_data'):
                logging.info(f"[DEBUG] UI: Calling load_character_data for {self.tabs.tabText(i)}.")
                tab.load_character_data()
        self.update_status_bar(f"Ready. Logged in as: {self.character_name}")

    def add_tabs(self):
        self.tabs.addTab(CharacterTab(self), "Character"); self.tabs.addTab(AssetsTab(self), "Assets")
        self.tabs.addTab(PriceHunterTab(self), "Price Hunter"); self.tabs.addTab(RegionScannerTab(self), "Region Scanner")
        self.tabs.addTab(RouteScannerTab(self), "Route Scanner"); self.tabs.addTab(BPOScannerTab(self), "BPO Scanner")
        self.tabs.addTab(GalaxyScannerTab(self), "Galaxy Scanner"); self.tabs.addTab(AnalyseTab(self), "Analyse")
        self.tabs.addTab(ManufacturingTab(self), "Manufacturing"); self.tabs.addTab(SettingsTab(self), "Settings")

    def create_docks(self):
        self.log_dock = QDockWidget("Log", self)
        self.log_widget = QTextEdit(); self.log_widget.setReadOnly(True)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.setWidget(self.log_widget)

    def create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self); exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        view_menu = menu_bar.addMenu("View")
        view_menu.addAction(self.log_dock.toggleViewAction())

    def update_status_bar(self, message):
        self.statusBar().showMessage(message)
        logging.info(f"Status: {message}")

    def log_message(self, message):
        if hasattr(self, 'log_widget'):
            self.log_widget.append(message)
        logging.info(message)

    def get_config_value(self, key, default=None):
        return self.config.get(key, default)

    def set_config_value(self, key, value):
        self.config[key] = value
        save_config(self.config)
