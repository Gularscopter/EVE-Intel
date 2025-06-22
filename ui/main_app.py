import sys
import logging
import inspect
from typing import Type, TypeVar
from datetime import datetime

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTabWidget,
                             QStatusBar, QTextEdit, QProgressBar, QLayout)
from PyQt6.QtCore import QRunnable, QThreadPool, QObject, pyqtSignal, pyqtSlot, QTimer, QRect
from PyQt6.QtGui import QColor, QTextCursor

# Importerer alle fanene for type-sjekking i closeEvent
from .tabs.character import CharacterTab
from .tabs.galaxy_scanner import GalaxyScannerTab
from .tabs.manufacturing import ManufacturingTab
from .tabs.region_scanner import RegionScannerTab
from .tabs.bpo_scanner import BPOScannerTab
from .tabs.settings import SettingsTab
from .tabs.base_tab import BaseTab

import config
from auth import AuthManager

T = TypeVar('T')

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    result = pyqtSignal(object)
    progress = pyqtSignal(str, int)

class Worker(QRunnable):
    def __init__(self, fn, **kwargs):
        super().__init__()
        self.fn = fn
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.status_callback = self.signals.progress.emit

    @pyqtSlot()
    def run(self):
        try:
            # Sjekk om funksjonen forventer en status_callback
            sig = inspect.signature(self.fn)
            if 'status_callback' in sig.parameters:
                self.kwargs['status_callback'] = self.status_callback
            
            result = self.fn(**self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
            logging.exception("Error in worker thread")
        finally:
            self.signals.finished.emit()

class EveMarketApp(QMainWindow):
    layout: QVBoxLayout
    character_id: int | None
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVE Intel")
        self.threadpool = QThreadPool()
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)

        self.auth_manager = AuthManager(self)
        char_id_val = self.get_config_value('character_id')
        self.character_id = int(char_id_val) if char_id_val is not None else None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.status_bar = QStatusBar()
        self.status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(self.status_bar)
        
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        self.update_status_bar("Applikasjon starter...")
        self.load_settings()
        self.update_status_bar("Applikasjon startet.")
        
        self.threadpool = QThreadPool()
        self.active_workers = [] # For å holde styr på aktive workers
        self.log_message(f"Klar. Antall tråder tilgjengelig: {self.threadpool.maxThreadCount()}")

        self.add_tabs()
        self.layout.addWidget(self.log_console)

    def run_in_thread(self, fn, on_success, on_error, on_finished=None, **kwargs):
        worker = Worker(fn, **kwargs)
        
        worker.signals.result.connect(on_success)
        worker.signals.error.connect(on_error)
        worker.signals.progress.connect(self.update_status_bar)
        
        # Sørger for at worker fjernes fra listen når den er ferdig
        def cleanup():
            if on_finished:
                on_finished()
            if worker in self.active_workers:
                self.active_workers.remove(worker)

        worker.signals.finished.connect(cleanup)
        
        self.threadpool.start(worker)
        self.active_workers.append(worker) # Holder en referanse til workeren

    def add_tabs(self):
        self.tabs.addTab(CharacterTab(self), "Character")
        self.tabs.addTab(GalaxyScannerTab(self), "Galaxy Scanner")
        self.tabs.addTab(ManufacturingTab(self), "Manufacturing")
        self.tabs.addTab(RegionScannerTab(self), "Region Scanner")
        self.tabs.addTab(BPOScannerTab(self), "BPO Scanner")
        self.tabs.addTab(SettingsTab(self), "Settings")

    def update_status_bar(self, message: str, progress: int = -1):
        self.status_bar.showMessage(message)
        if progress is not None and progress >= 0:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(progress)
        
        if progress is not None and progress >= 100:
            QTimer.singleShot(3000, lambda: self.progress_bar.setVisible(False))
        elif progress is not None and progress < 0:
            self.progress_bar.setVisible(False)

    def log_message(self, message: str, level: str = "info"):
        now = datetime.now().strftime("%H:%M:%S")
        level_upper = level.upper()
        log_entry = f"[{now}] [{level_upper}] {message}"
        
        color = {
            "error": QColor("red"),
            "warning": QColor("orange"),
            "info": QColor("white")
        }
        
        # Log to python logger
        if level == 'error': logging.error(message)
        elif level == 'warning': logging.warning(message)
        else: logging.info(message)
        
        self.log_console.setTextColor(color.get(level, QColor("white")))
        self.log_console.append(log_entry)
        scrollbar = self.log_console.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def load_settings(self):
        try:
            app_config = config.load_config()
            if app_config:
                geometry = app_config.get('main_window_geometry')
                if geometry:
                    self.setGeometry(QRect(*geometry))
            self.log_message("Settings loaded.")
        except Exception as e:
            self.log_message(f"Could not load settings: {e}", "error")

    def save_settings(self):
        try:
            # This method only saves the main window's geometry.
            # Tabs are responsible for saving their own settings via set_config_value.
            self.set_config_value('main_window_geometry', self.geometry().getRect())
            self.log_message("Main window settings prepared for saving.")
        except Exception as e:
            self.log_message(f"Could not save main window settings: {e}", "error")

    def findChild(self, child_type: Type[T]) -> T | None:
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, child_type):
                return widget
        return None

    def closeEvent(self, event):
        self.log_message("Appen lukkes, lagrer konfigurasjon...")
        
        # Call save_settings on any tab that is a BaseTab instance
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, BaseTab):
                widget.save_settings()

        # Save the main window's settings
        self.save_settings()
        
        # Persist all collected changes to the config file
        config.save_config() 
        self.log_message("Konfigurasjon lagret til fil.")

        super().closeEvent(event)

    def get_config_value(self, key, default=None):
        return config.get(key, default)

    def set_config_value(self, key, value):
        config.set(key, value)
        # We don't save immediately, we wait for closeEvent to save all at once
        # config.save_config()

    def trigger_full_authentication(self):
        self.log_message("Starting authentication...")
        self.run_in_thread(
            self.auth_manager.start_full_auth_flow,
            on_success=self.on_auth_succeeded,
            on_error=self.on_auth_failed
        )

    def on_auth_succeeded(self, character_info):
        if isinstance(character_info, dict) and character_info.get('name'):
            self.log_message(f"Successfully authenticated as {character_info.get('name')}", "info")
            self.character_id = character_info.get('id')
            self.set_config_value('character_id', self.character_id)
            char_tab = self.findChild(CharacterTab)
            if char_tab:
                char_tab.load_character_data()
        else:
            self.on_auth_failed("Authentication failed. Please check logs and CLIENT_ID in config.")

    def on_auth_failed(self, error):
        self.log_message(f"Authentication failed: {error}", "error")
