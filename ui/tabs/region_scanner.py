# ui/tabs/region_scanner.py
import sys
import json
import logging
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView,
                             QHeaderView, QLabel, QLineEdit, QFormLayout, QAbstractItemView, QCheckBox, QGroupBox, QMenu)
from PyQt6.QtCore import QAbstractTableModel, Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QAction

sys.path.append('logic')
from scanners import region as region_helpers 
import db
import api

class PandasModel(QAbstractTableModel):
    def __init__(self, data):
        super().__init__()
        self._data = data
    def rowCount(self, parent=None):
        return len(self._data.index) if self._data is not None else 0
    def columnCount(self, parent=None):
        if self._data is not None:
            return self._data.shape[1]
        return 0
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                value = self._data.iloc[index.row(), index.column()]
                if pd.isna(value): return ""
                if isinstance(value, float): return f"{value:,.2f}"
                if isinstance(value, int): return f"{value:,}"
                return str(value)
            if role == Qt.ItemDataRole.ForegroundRole:
                column_name = self._data.columns[index.column()]
                if column_name == 'Profit Per Unit': return QColor('lime')
                if column_name == 'ROI': return QColor('cyan')
        return None
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return str(self._data.columns[section])
        return None
    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        col_name = self._data.columns[column]
        self._data = self._data.sort_values(by=col_name, ascending=(order == Qt.SortOrder.AscendingOrder))
        self.layoutChanged.emit()
    def updateData(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

class RegionScannerWorker(QThread):
    item_found = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str, int)

    def __init__(self, config, items, access_token, parent=None):
        super().__init__(parent)
        self.config = config
        self.access_token = access_token
        # --- NYTT: Oppretter en ID -> Navn map én gang her ---
        self.id_to_name_map = {v: k for k, v in items.items()}

    # --- NYTT: Hjelpefunksjon for å finne navn, nå en del av klassen ---
    def get_item_name(self, item_id):
        return self.id_to_name_map.get(item_id, f"Unknown ID: {item_id}")

    def run(self):
        try:
            self._scan_region_logic()
        except Exception as e:
            logging.error("Feil i worker-tråden for RegionScanner", exc_info=True)
            self.error.emit(f"An error occurred in worker: {e}")
        finally:
            self.finished.emit()

    def _scan_region_logic(self):
        cfg = self.config
        
        if cfg['trace_item_name']:
            logging.info(f"SPORINGSMODUS: Kjører kun for varen '{cfg['trace_item_name']}'.")
            trace_item_id = db.get_item_id_by_name(cfg['trace_item_name'])
            if not trace_item_id:
                self.progress.emit(f"Fant ikke varen '{cfg['trace_item_name']}'", 100)
                return
            all_item_ids = [trace_item_id]
        else:
            logging.info(f"scan_region startet.")
            all_item_ids = list(self.id_to_name_map.keys())

        if not all_item_ids: return

        if cfg['trace_item_name']:
            potentially_profitable_ids = all_item_ids
        else:
            self.progress.emit("Steg 1: Henter markedspriser...", 10)
            if self.isInterruptionRequested(): return

            market_data = api.get_scanner_market_data(all_item_ids, region_id=cfg['region_id'])
            if not market_data:
                self.progress.emit("Feil: Kunne ikke hente priser fra Fuzzwork.", 100)
                return
            
            potentially_profitable_ids = []
            for item_id_str, prices in market_data.items():
                if self.isInterruptionRequested(): return
                item_id = int(item_id_str)
                highest_buy = prices.get('highest_buy', 0); lowest_sell = prices.get('lowest_sell', 0)
                buy_order_volume = prices.get('buy_order_volume', 0)
                if not (highest_buy > 0 and lowest_sell > highest_buy): continue
                absolute_spread = lowest_sell - highest_buy; relative_spread = absolute_spread / highest_buy
                if not (absolute_spread >= cfg['min_abs_spread'] and relative_spread >= cfg['min_rel_spread']): continue
                total_fees = (lowest_sell * cfg['sales_tax_rate']) + (lowest_sell * cfg['broker_fee_rate']) + (highest_buy * cfg['broker_fee_rate'])
                estimated_profit = absolute_spread - total_fees
                if estimated_profit < cfg['min_profit']: continue
                market_liquidity = highest_buy * buy_order_volume
                if market_liquidity < cfg['min_liquidity']: continue
                potentially_profitable_ids.append(item_id)
        
        total_candidates = len(potentially_profitable_ids)
        logging.info(f"Steg 1 fullført. Fant {total_candidates} kandidater.")
        if total_candidates == 0:
            self.progress.emit("Fant ingen kandidater som møtte kravene.", 100)
            return

        self.progress.emit(f"Steg 2: Verifiserer {total_candidates} kandidater...", 50)
        
        for i, item_id in enumerate(potentially_profitable_ids):
            if self.isInterruptionRequested():
                logging.info("Skanning avbrutt av bruker.")
                return
            
            progress_percentage = 50 + int(50 * (i + 1) / total_candidates)
            # --- ENDRING: Bruker den lokale navnefunksjonen ---
            self.progress.emit(f"Steg 2: Verifiserer '{self.get_item_name(item_id)}' ({i+1}/{total_candidates})", progress_percentage)
            
            item_data = region_helpers.fetch_orders_for_item(item_id, cfg['region_id'], cfg['min_avg_vol'], cfg['min_active_days'], cfg['is_debugging'], self.access_token)
            
            if item_data:
                # Beriker dataen med navnet før den sendes til UI-en
                item_data['Item Name'] = self.get_item_name(item_id)
                self.item_found.emit(item_data)
        
        logging.info("Skanning fullført.")

class RegionScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.is_scanning = False
        self.items = None
        self.all_found_items = []
        self.df_columns = ['Item Name', 'Vår Kjøpspris', 'Vår Salgspris', 'Profit Per Unit', 'ROI', 'Avg Daily Vol', 'Aktive Dager', 'Item ID']
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(500)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_table_display) 
        self.init_ui()
        self.load_items()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        filter_groupbox = QGroupBox("Filter-innstillinger")
        form_layout = QFormLayout()
        self.min_profit_input = QLineEdit("10000")
        self.min_profit_input.setToolTip("Minimum nettofortjeneste per enhet etter at alle avgifter er betalt.")
        self.min_abs_spread_input = QLineEdit("50000")
        self.min_abs_spread_input.setToolTip("Minimum prisforskjell i ren ISK mellom laveste salgsordre og høyeste kjøpsordre.")
        self.min_rel_spread_input = QLineEdit("5")
        self.min_rel_spread_input.setToolTip("Minimum prisforskjell i prosent (margin).")
        self.min_volume_input = QLineEdit("5")
        self.min_volume_input.setToolTip("Minimum gjennomsnittlig antall enheter som omsettes hver dag (siste 7 dager).")
        self.min_active_days_input = QLineEdit("4")
        self.min_active_days_input.setToolTip("Minimum antall dager (av de siste 7) varen må ha hatt salg på.")
        self.min_liquidity_input = QLineEdit("50000000")
        self.min_liquidity_input.setToolTip("Minimum totalverdi (i ISK) av alle kjøpsordrer på markedet for denne varen.")
        self.sales_tax_input = QLineEdit("3.6")
        self.sales_tax_input.setToolTip("Din 'Sales Tax'-rate i prosent.")
        self.broker_fee_input = QLineEdit("3.0")
        self.broker_fee_input.setToolTip("Din 'Broker's Fee'-rate i prosent.")
        form_layout.addRow("Min Nettofortjeneste (ISK):", self.min_profit_input)
        form_layout.addRow("Min Prisforskjell (ISK):", self.min_abs_spread_input)
        form_layout.addRow("Min Margin (%):", self.min_rel_spread_input)
        form_layout.addRow("Min Daglig Volum (Gj.sn. 7d):", self.min_volume_input)
        form_layout.addRow("Min Antall Handelsdager (siste 7):", self.min_active_days_input)
        form_layout.addRow("Min Markedslikviditet (ISK):", self.min_liquidity_input)
        form_layout.addRow("Sales Tax (%):", self.sales_tax_input)
        form_layout.addRow("Broker's Fee (%):", self.broker_fee_input)
        filter_groupbox.setLayout(form_layout)
        debug_groupbox = QGroupBox("Feilsøking")
        debug_layout = QVBoxLayout()
        self.trace_layout = QHBoxLayout()
        self.trace_item_checkbox = QCheckBox("Spor spesifikk vare:")
        self.trace_item_input = QLineEdit()
        self.trace_item_input.setPlaceholderText("Skriv inn nøyaktig varenavn...")
        self.trace_item_input.setEnabled(False)
        self.trace_item_checkbox.toggled.connect(self.trace_item_input.setEnabled)
        self.trace_layout.addWidget(self.trace_item_checkbox)
        self.trace_layout.addWidget(self.trace_item_input)
        debug_layout.addLayout(self.trace_layout)
        debug_groupbox.setLayout(debug_layout)
        self.scan_button = QPushButton("Start Skanning")
        self.scan_button.clicked.connect(self.toggle_scan)
        self.status_label = QLabel("Ready.")
        self.results_table = QTableView()
        self.results_table.setSortingEnabled(True)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.model = PandasModel(pd.DataFrame(columns=self.df_columns))
        self.results_table.setModel(self.model)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_table_context_menu)
        main_layout.addWidget(filter_groupbox)
        main_layout.addWidget(debug_groupbox)
        main_layout.addWidget(self.scan_button)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.results_table)

    def load_items(self):
        logging.info("Laster varer fra items_filtered.json...")
        try:
            with open('items_filtered.json', 'r') as f: self.items = json.load(f)
            if not self.items or not isinstance(self.items, dict) or len(self.items) == 0:
                self.status_label.setText("Error: 'items_filtered.json' is empty or invalid.")
                self.scan_button.setEnabled(False)
            else:
                self.status_label.setText(f"Loaded {len(self.items)} items. Ready.")
                self.scan_button.setEnabled(True)
        except (FileNotFoundError, json.JSONDecodeError):
            self.status_label.setText("Error: Could not load 'items_filtered.json'.")
            self.scan_button.setEnabled(False)

    def update_scan_status(self, message, percentage):
        self.status_label.setText(f"{message} [{percentage}%]")

    def toggle_scan(self):
        if self.is_scanning:
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                logging.info("Stopp-signal sendt til scanner.")
                self.worker.requestInterruption()
                self.scan_button.setEnabled(False)
                self.status_label.setText("Stopper skanning...")
        else:
            self.start_scan()

    def start_scan(self):
        if not self.items: return
        try:
            self.scan_config = {
                "min_profit": float(self.min_profit_input.text().replace(",", "")),
                "min_avg_vol": int(self.min_volume_input.text().replace(",", "")),
                "min_active_days": int(self.min_active_days_input.text().replace(",", "")),
                "sales_tax_rate": float(self.sales_tax_input.text()) / 100,
                "broker_fee_rate": float(self.broker_fee_input.text()) / 100,
                "min_abs_spread": float(self.min_abs_spread_input.text().replace(",", "")),
                "min_rel_spread": float(self.min_rel_spread_input.text()) / 100,
                "min_liquidity": float(self.min_liquidity_input.text().replace(",", "")),
                "is_debugging": self.trace_item_checkbox.isChecked(),
                "trace_item_name": self.trace_item_input.text() if self.trace_item_checkbox.isChecked() else None,
                "region_id": 10000002
            }
            if self.scan_config['trace_item_name']:
                self.scan_config['is_debugging'] = True
        except ValueError:
            self.status_label.setText("Error: Invalid number format in settings.")
            return

        access_token = self.main_app.auth_manager.get_valid_token()
        if not access_token:
            self.status_label.setText("Error: Not authenticated. Please log in.")
            return

        self.all_found_items = []
        self.model.updateData(pd.DataFrame(columns=self.df_columns))
        self.is_scanning = True
        self.scan_button.setText("Stopp Skanning")
        self.scan_button.setStyleSheet("background-color: #A03030; color: white;")
        self.worker = RegionScannerWorker(self.scan_config, self.items, access_token)
        self.worker.item_found.connect(self.on_item_found)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.progress.connect(self.update_scan_status)
        self.worker.start()

    def on_item_found(self, item_data):
        item_name = item_data.get('Item Name', 'N/A')
        # ... (resten av logikken er uendret og bruker nå scan_config)
        current_lowest_sell = item_data.get('Lowest Sell', 0)
        current_highest_buy = item_data.get('Highest Buy', 0)
        if not (current_lowest_sell > current_highest_buy): return
        our_buy_price = current_highest_buy + 0.01
        our_sell_price = current_lowest_sell - 0.01
        gross_profit = our_sell_price - our_buy_price
        total_fees = (our_sell_price * self.scan_config['broker_fee_rate']) + (our_buy_price * self.scan_config['broker_fee_rate']) + (our_sell_price * self.scan_config['sales_tax_rate'])
        profit_per_unit = gross_profit - total_fees
        if profit_per_unit < self.scan_config['min_profit']: return
        item_data['Vår Kjøpspris'] = our_buy_price
        item_data['Vår Salgspris'] = our_sell_price
        item_data['Profit Per Unit'] = profit_per_unit
        item_data['ROI'] = (profit_per_unit / our_buy_price) * 100 if our_buy_price > 0 else 0
        self.all_found_items.append(item_data)
        if not self.update_timer.isActive():
            self.update_timer.start()

    def _reset_scan_ui(self):
        self.is_scanning = False
        self.scan_button.setText("Start Skanning")
        self.scan_button.setStyleSheet("")
        self.scan_button.setEnabled(True)

    def on_scan_finished(self):
        self.update_table_display()
        self.status_label.setText(f"Skanning fullført. Fant {len(self.all_found_items)} lønnsomme varer.")
        self._reset_scan_ui()
    
    def on_scan_error(self, error_message):
        logging.error(f"En feil ble fanget av UI: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        self._reset_scan_ui()

    def update_table_display(self):
        if not self.all_found_items: return
        self.all_found_items.sort(key=lambda x: x['Profit Per Unit'], reverse=True)
        display_df = pd.DataFrame(self.all_found_items)
        for col in self.df_columns:
            if col not in display_df.columns:
                display_df[col] = pd.NA
        self.model.updateData(display_df[self.df_columns])

    def show_table_context_menu(self, position):
        index = self.results_table.indexAt(position)
        if not index.isValid(): return
        row = index.row()
        item_name = self.model._data.iloc[row]['Item Name']
        item_id = self.model._data.iloc[row]['Item ID']
        menu = QMenu()
        open_action = QAction(f"Åpne '{item_name}' i markedet", self)
        open_action.triggered.connect(lambda: self.trigger_open_market_window(item_id))
        menu.addAction(open_action)
        menu.exec(self.results_table.viewport().mapToGlobal(position))

    def trigger_open_market_window(self, type_id):
        access_token = self.main_app.auth_manager.get_valid_token()
        if not access_token:
            self.main_app.update_status_bar("Kan ikke åpne markedet: Du er ikke logget inn.")
            return
        self.main_app.update_status_bar(f"Sender kommando for vare-ID {type_id}...")
        self.main_app.run_in_thread(
            fn=api.open_market_window,
            on_success=lambda result: self.main_app.update_status_bar(
                "Signal sendt til EVE-klienten." if result else "Kunne ikke sende signal.", 2000
            ),
            on_error=lambda e: self.main_app.update_status_bar(f"Feil ved åpning av marked: {e}"),
            type_id=type_id,
            access_token=access_token
        )
    
    def load_items(self):
        logging.info("Laster varer fra items_filtered.json...")
        try:
            with open('items_filtered.json', 'r') as f: self.items = json.load(f)
            if not self.items or not isinstance(self.items, dict) or len(self.items) == 0:
                self.status_label.setText("Error: 'items_filtered.json' is empty or invalid.")
                self.scan_button.setEnabled(False)
            else:
                self.status_label.setText(f"Loaded {len(self.items)} items. Ready.")
                self.scan_button.setEnabled(True)
        except (FileNotFoundError, json.JSONDecodeError):
            self.status_label.setText("Error: Could not load 'items_filtered.json'.")
            self.scan_button.setEnabled(False)