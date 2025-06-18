import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QComboBox, QCompleter, QGridLayout, QGroupBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QCheckBox)
from PyQt6.QtCore import QStringListModel, Qt
from functools import partial
import db
from logic.scanners.price_hunter import run_price_hunter_scan

class PriceHunterTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.full_scan_results = []
        self.init_ui()
        self.load_initial_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        input_group = QGroupBox("Søk etter beste pris")
        input_layout = QGridLayout(input_group)

        input_layout.addWidget(QLabel("Vare:"), 0, 0)

        # --- KORRIGERING HER: Bytter til QComboBox for robust autofullfør ---
        self.item_combo = QComboBox()
        self.item_combo.setEditable(True)
        self.item_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.item_combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.item_combo.lineEdit().setPlaceholderText("Skriv for å søke etter en vare...")
        input_layout.addWidget(self.item_combo, 0, 1, 1, 3)
        # -------------------------------------------------------------------

        self.hisec_check = QCheckBox("High-sec"); self.hisec_check.setChecked(True)
        self.lowsec_check = QCheckBox("Low-sec"); self.lowsec_check.setChecked(True)
        self.nullsec_check = QCheckBox("Null-sec"); self.nullsec_check.setChecked(True)
        input_layout.addWidget(self.hisec_check, 1, 1)
        input_layout.addWidget(self.lowsec_check, 1, 2)
        input_layout.addWidget(self.nullsec_check, 1, 3)

        for checkbox in [self.hisec_check, self.lowsec_check, self.nullsec_check]:
            checkbox.stateChanged.connect(self.update_display_from_filters)

        self.find_sell_button = QPushButton("Søk Beste Salgspris (Lavest)")
        self.find_buy_button = QPushButton("Søk Beste Kjøpspris (Høyest)")
        
        self.find_sell_button.clicked.connect(partial(self.run_scan, 'sell'))
        self.find_buy_button.clicked.connect(partial(self.run_scan, 'buy'))
        
        input_layout.addWidget(self.find_sell_button, 2, 1, 1, 2)
        input_layout.addWidget(self.find_buy_button, 2, 3, 1, 2)
        
        main_layout.addWidget(input_group)

        self.results_table = QTableWidget()
        headers = ['Pris', 'Antall', 'Lokasjon', 'System', 'Sikkerhet']
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setSortingEnabled(True)
        main_layout.addWidget(self.results_table)

    def load_initial_data(self):
        self.all_item_names = db.get_all_item_names()
        model = QStringListModel(self.all_item_names)
        completer = QCompleter(model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item_combo.setCompleter(completer)

    def run_scan(self, order_type):
        item_name = self.item_combo.currentText()
        if not item_name:
            self.main_app.log_message("Vennligst skriv inn en vare å søke etter.")
            return

        type_id = db.get_item_id_by_name(item_name)
        if not type_id:
            self.main_app.log_message(f"Fant ikke varen '{item_name}'.")
            return
            
        scan_config = {
            'item_name': item_name, 'type_id': type_id, 'order_type': order_type,
        }

        self.find_buy_button.setEnabled(False); self.find_sell_button.setEnabled(False)
        self.results_table.setRowCount(0)
        self.main_app.update_status_bar(f"Søker etter beste {order_type}-pris for {item_name}...", 0)

        self.main_app.run_in_thread(
            run_price_hunter_scan, on_success=self.on_scan_success,
            on_error=self.on_scan_error, scan_config=scan_config
        )

    def on_scan_success(self, results):
        self.find_buy_button.setEnabled(True); self.find_sell_button.setEnabled(True)
        self.main_app.update_status_bar(f"Prisjakt fullført. Fant {len(results)} mulige ordre.", 100)
        self.full_scan_results = results
        self.update_display_from_filters()

    def update_display_from_filters(self):
        if not self.full_scan_results: 
            self.results_table.setRowCount(0)
            return
        
        filtered_results = []
        for order in self.full_scan_results:
            sec = order['sec_status']
            if (sec >= 0.5 and self.hisec_check.isChecked()) or \
               (0.0 < sec < 0.5 and self.lowsec_check.isChecked()) or \
               (sec <= 0.0 and self.nullsec_check.isChecked()):
                filtered_results.append(order)
        
        self.display_results(filtered_results)

    def display_results(self, results):
        self.results_table.setRowCount(len(results))
        for row, order in enumerate(results):
            sec_val = order.get('sec_status', 0.0)
            if sec_val >= 0.5: sec_str = f"High ({sec_val:.1f})"
            elif sec_val > 0.0: sec_str = f"Low ({sec_val:.1f})"
            else: sec_str = f"Null ({sec_val:.1f})"
            
            self.set_table_item_numeric(row, 0, order.get('price'), "{:,.2f} ISK")
            self.set_table_item_numeric(row, 1, order.get('quantity'), "{:,}")
            self.results_table.setItem(row, 2, QTableWidgetItem(order.get('location_name')))
            self.results_table.setItem(row, 3, QTableWidgetItem(order.get('system_name')))
            self.results_table.setItem(row, 4, QTableWidgetItem(sec_str))
            
        self.results_table.resizeColumnsToContents()

    def on_scan_error(self, e):
        self.find_buy_button.setEnabled(True); self.find_sell_button.setEnabled(True)
        self.main_app.log_message(f"Feil under prissøk: {e}")
        self.main_app.update_status_bar("Prisjakt feilet.", 100)
        
    def set_table_item_numeric(self, row, col, data, format_str="{:,.2f}"):
        if data is None: data = 0
        item = QTableWidgetItem(format_str.format(data))
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.results_table.setItem(row, col, item)