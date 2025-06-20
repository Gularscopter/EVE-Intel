# ui/main_app.py
import logging
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTabWidget,
                             QStatusBar, QTextEdit, QProgressBar)
from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal, pyqtSlot, QTimer

from ui.tabs.character import CharacterTab
from ui.tabs.assets import AssetsTab
from ui.tabs.region_scanner import RegionScannerTab
from ui.tabs.galaxy_scanner import GalaxyScannerTab
from ui.tabs.route_scanners import RouteScannerTab
from ui.tabs.price_hunter import PriceHunterTab
from ui.tabs.analyse import AnalyseTab
from ui.tabs.bpo_scanner import BPOScannerTab
from ui.tabs.manufacturing import ManufacturingTab
from ui.tabs.settings import SettingsTab

import config
import auth
import db

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(object)
    result = pyqtSignal(object)
    progress = pyqtSignal(str, int)

class Worker(QRunnable):
    def __init__(self, fn, **kwargs):
        super().__init__()
        self.fn = fn
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        if 'status_callback' not in self.kwargs:
            self.kwargs['status_callback'] = self.signals.progress.emit

    @pyqtSlot()
    def run(self):
        try:
            result = self.fn(**self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()

class EveMarketApp(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EVE Intel v2.0 - Unstable Branch")
        self.setGeometry(100, 100, 1600, 900)
        
        self.threadpool = QThreadPool()
        
        self.auth_manager = auth.AuthManager(self)
        self.character_id = self.auth_manager.character_info.get('id')
        # La oss hente token her for å være sikker
        self.access_token = self.auth_manager.get_valid_token()

        self.init_ui()
        self.log_message(f"Loaded character ID: {self.character_id}" if self.character_id else "No character loaded.")

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(150)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.update_status_bar("Applikasjon startet.")
        
        self.add_tabs()
        self.layout.addWidget(self.log_console)

    def run_in_thread(self, fn, on_success, on_error, on_finished=None, **kwargs):
        worker = Worker(fn, **kwargs)
        
        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(self.update_status_bar)
        if on_finished:
            worker.signals.finished.connect(on_finished)
        
        self.threadpool.start(worker)

    def add_tabs(self):
        self.tabs.addTab(CharacterTab(self), "Character")
        self.tabs.addTab(AssetsTab(self), "Assets")
        
        # --- DENNE LINJEN ER ENDRET FOR Å SENDE MED 'self' ---
        self.tabs.addTab(RegionScannerTab(self), "Region Scanner")
        
        self.tabs.addTab(GalaxyScannerTab(self), "Galaxy Scanner")
        self.tabs.addTab(RouteScannerTab(self), "Route Scanner")
        self.tabs.addTab(PriceHunterTab(self), "Price Hunter")
        self.tabs.addTab(AnalyseTab(self), "Analyse")
        self.tabs.addTab(BPOScannerTab(self), "BPO Scanner")
        self.tabs.addTab(ManufacturingTab(self), "Manufacturing")
        self.tabs.addTab(SettingsTab(self), "Settings")

    @pyqtSlot(str, int)
    @pyqtSlot(str)
    def update_status_bar(self, message, progress=None):
        self.status_bar.showMessage(message)
        logging.info(message)
        
        if progress is not None and progress >= 0:
            if not self.progress_bar.isVisible():
                self.progress_bar.setVisible(True)
            self.progress_bar.setValue(progress)
        
        if progress is not None and progress >= 100:
            QTimer.singleShot(2000, lambda: self.progress_bar.setVisible(False))

    def log_message(self, message):
        self.log_console.append(message)
        logging.info(message)

    def trigger_full_authentication(self):
        success = self.auth_manager.start_full_auth_flow()
        if success:
            self.character_id = self.auth_manager.character_info.get('id')
            self.access_token = self.auth_manager.get_valid_token()
            self.log_message(f"Successfully authenticated character: {self.auth_manager.character_info.get('name')}")
            
            char_tab = self.find_tab(CharacterTab)
            if char_tab:
                char_tab.load_character_data()
        else:
            self.log_message("Authentication failed or was cancelled.")
    
    def get_config_value(self, key, default=None):
        return config.get(key.lower(), default)

    def set_config_value(self, key, value):
        config.set(key.lower(), value)
        config.save_config()

    def find_tab(self, tab_class):
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, tab_class):
                return widget
        return None