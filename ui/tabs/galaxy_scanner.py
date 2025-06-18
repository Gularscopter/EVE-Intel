import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QHeaderView, 
                             QLabel, QDoubleSpinBox, QComboBox, QTreeWidget, 
                             QTreeWidgetItem, QCheckBox, QCompleter, QMenu, QApplication, QGridLayout)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QStringListModel
import db
from logic.scanners.galaxy import run_galaxy_scan, build_bundles_from_trades

class GalaxyScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.all_regions = []
        self.full_scan_results = []
        self.init_ui()
        self.load_region_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        top_controls = QHBoxLayout()
        
        region_layout = QGridLayout()
        region_layout.addWidget(QLabel("Fra Region:"), 0, 0)
        self.buy_region_combo = self.create_completer_combo()
        region_layout.addWidget(self.buy_region_combo, 0, 1)
        region_layout.addWidget(QLabel("Til Region:"), 1, 0)
        self.sell_region_combo = self.create_completer_combo()
        region_layout.addWidget(self.sell_region_combo, 1, 1)
        top_controls.addLayout(region_layout)

        ship_layout = QGridLayout()
        ship_layout.addWidget(QLabel("Lasterom (m³):"), 0, 0)
        self.cargo_capacity_input = self.create_spinbox(0, 100000, 5000, 100)
        ship_layout.addWidget(self.cargo_capacity_input, 0, 1)
        ship_layout.addWidget(QLabel("Maks Investering:"), 1, 0)
        self.max_investment_input = self.create_spinbox(0, 10_000_000_000, 100_000_000, 1_000_000)
        ship_layout.addWidget(self.max_investment_input, 1, 1)
        top_controls.addLayout(ship_layout)
        
        settings_layout = QGridLayout()
        settings_layout.addWidget(QLabel("Min total profitt (per pakke):"), 0, 0)
        self.min_profit_total_input = self.create_spinbox(0, 1_000_000_000, 1_000_000, 100000)
        settings_layout.addWidget(self.min_profit_total_input, 0, 1)
        settings_layout.addWidget(QLabel("Min profitt (per handel):"), 1, 0)
        self.min_profit_per_item_input = self.create_spinbox(0, 100_000_000, 100_000, 10000)
        settings_layout.addWidget(self.min_profit_per_item_input, 1, 1)
        top_controls.addLayout(settings_layout)
        
        tax_layout = QGridLayout()
        tax_layout.addWidget(QLabel("Broker%"), 0, 0)
        self.brokers_fee_input = self.create_spinbox(0, 10, 2.5, 0.1, True)
        tax_layout.addWidget(self.brokers_fee_input, 0, 1)
        tax_layout.addWidget(QLabel("Tax%"), 1, 0)
        self.sales_tax_input = self.create_spinbox(0, 10, 1.5, 0.1, True)
        tax_layout.addWidget(self.sales_tax_input, 1, 1)
        top_controls.addLayout(tax_layout)
        main_layout.addLayout(top_controls)
        
        bottom_controls = QHBoxLayout()
        checkbox_layout = QVBoxLayout()
        self.multistation_checkbox = QCheckBox("Bygg pakke fra flere stasjoner (Multi-buy)")
        self.multistation_checkbox.setChecked(True)
        self.use_common_sell_station_check = QCheckBox("Bruk én felles salgsstasjon")
        self.use_common_sell_station_check.setChecked(False)
        checkbox_layout.addWidget(self.multistation_checkbox)
        checkbox_layout.addWidget(self.use_common_sell_station_check)
        bottom_controls.addLayout(checkbox_layout)

        sec_status_layout = QVBoxLayout()
        sec_status_layout.addWidget(QLabel("Inkluder kjøp fra:"))
        sec_hbox = QHBoxLayout()
        self.hisec_check = QCheckBox("High-sec"); self.hisec_check.setChecked(True)
        self.lowsec_check = QCheckBox("Low-sec")
        self.nullsec_check = QCheckBox("Null-sec")
        sec_hbox.addWidget(self.hisec_check); sec_hbox.addWidget(self.lowsec_check); sec_hbox.addWidget(self.nullsec_check)
        sec_status_layout.addLayout(sec_hbox)
        bottom_controls.addLayout(sec_status_layout)
        
        for checkbox in [self.multistation_checkbox, self.use_common_sell_station_check, self.hisec_check, self.lowsec_check, self.nullsec_check]:
            checkbox.stateChanged.connect(self.update_display_from_filters)
        
        bottom_controls.addStretch()
        self.scan_button = QPushButton("Finn Rute")
        self.scan_button.clicked.connect(self.run_scan)
        bottom_controls.addWidget(self.scan_button)
        main_layout.addLayout(bottom_controls)

        self.results_tree = QTreeWidget()
        headers = ["Pakke / Vare", "Antall", "Total Vare-Profitt", "Kjøpsstasjon", "Salgsstasjon", "Volum (Kjøp/Salg)"]
        self.results_tree.setHeaderLabels(headers)
        self.results_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(self.show_bundle_context_menu)
        main_layout.addWidget(self.results_tree)

    def create_completer_combo(self):
        combo = QComboBox(); combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert); combo.setCompleter(QCompleter(self))
        return combo

    def load_region_data(self):
        self.all_regions = db.get_all_region_names(); model = QStringListModel(self.all_regions)
        self.buy_region_combo.completer().setModel(model); self.buy_region_combo.addItems(self.all_regions)
        self.sell_region_combo.completer().setModel(model); self.sell_region_combo.addItems(self.all_regions)
        if "The Forge" in self.all_regions: self.buy_region_combo.setCurrentText("The Forge")
        if "Domain" in self.all_regions: self.sell_region_combo.setCurrentText("Domain")

    def create_spinbox(self, min_val, max_val, default_val, step, is_double=False):
        spinbox = QDoubleSpinBox()
        if is_double: spinbox.setDecimals(2)
        else: spinbox.setDecimals(0)
        spinbox.setRange(min_val, max_val); spinbox.setValue(default_val)
        spinbox.setSingleStep(step); spinbox.setGroupSeparatorShown(True)
        return spinbox

    def run_scan(self):
        scan_config = {
            'buy_region': self.buy_region_combo.currentText(), 
            'sell_region': self.sell_region_combo.currentText(),
            'access_token': self.main_app.access_token # Legger til access token for struktur-oppslag
        }
        if scan_config['buy_region'] == scan_config['sell_region']:
            self.main_app.log_message("Start- og mål-region kan ikke være den samme."); return

        self.main_app.update_status_bar(f"Søker rute fra {scan_config['buy_region']} til {scan_config['sell_region']}...", 0)
        self.scan_button.setEnabled(False); self.results_tree.clear(); self.full_scan_results = []
        self.main_app.run_in_thread(run_galaxy_scan, scan_config=scan_config, on_success=self.on_scan_success, on_error=self.on_scan_error)

    def on_scan_success(self, all_trades):
        self.full_scan_results = all_trades; self.scan_button.setEnabled(True)
        self.update_display_from_filters()

    def update_display_from_filters(self):
        if not self.full_scan_results: return
        scan_config = {
            'ship_cargo_m3': self.cargo_capacity_input.value(), 'max_investment': self.max_investment_input.value(),
            'min_profit_total': self.min_profit_total_input.value(),
            'min_profit_per_item': self.min_profit_per_item_input.value(),
            'brokers_fee_rate': self.brokers_fee_input.value(), 'sales_tax_rate': self.sales_tax_input.value(),
            'allow_multistation': self.multistation_checkbox.isChecked(),
            'use_common_sell_station': self.use_common_sell_station_check.isChecked(),
            'include_hisec': self.hisec_check.isChecked(), 'include_lowsec': self.lowsec_check.isChecked(),
            'include_nullsec': self.nullsec_check.isChecked(),
        }
        
        self.scan_button.setEnabled(False)
        self.main_app.update_status_bar("Bygger pakker med gjeldende filter...", 95)
        # --- KORRIGERING HER: Bruker run_in_thread for å unngå feil ---
        self.main_app.run_in_thread(build_bundles_from_trades, 
                                   all_trades=self.full_scan_results, 
                                   scan_config=scan_config,
                                   on_success=self.display_bundles, 
                                   on_error=self.on_scan_error)

    def display_bundles(self, bundles):
        self.scan_button.setEnabled(True)
        self.main_app.update_status_bar(f"Viser {len(bundles)} handelspakke(r).", 100)
        self.results_tree.clear()
        if not bundles:
            root_item = QTreeWidgetItem(self.results_tree); root_item.setText(0, "Ingen pakker funnet med gjeldende filter.")
            return

        for i, bundle in enumerate(bundles):
            station_name = bundle.get('station_name', 'Ukjent')
            root_item = QTreeWidgetItem(self.results_tree)
            root_item.setData(0, Qt.ItemDataRole.UserRole, bundle)
            root_item.setText(0, f"Pakke #{i+1}: Fra {station_name}")
            root_item.setText(2, f"{bundle.get('total_profit', 0):,.2f} ISK")
            root_item.setText(3, f"Kost: {bundle.get('total_investment', 0):,.2f} ISK")
            root_item.setText(4, f"Volum: {bundle.get('total_volume', 0):,.2f} m³")
            for col in [2,3,4]: root_item.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            for item in bundle.get('items', []):
                child_item = QTreeWidgetItem(root_item)
                child_item.setText(0, f"  {item['name']}")
                child_item.setText(1, f"{item['quantity']:,}")
                child_item.setText(2, f"{item.get('total_profit_for_item', 0):,.2f} ISK")
                child_item.setText(3, item.get('buy_station_name'))
                child_item.setText(4, item.get('sell_station_name'))
                child_item.setText(5, item.get('volume_str'))
                for col in [1,2,5]: child_item.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.results_tree.expandAll()
        for i in range(self.results_tree.columnCount()):
            self.results_tree.resizeColumnToContents(i)

    def on_scan_error(self, e):
        logging.error(f"Error during galaxy scan: {e}", exc_info=True)
        self.main_app.log_message(f"Galaxy Scan Error: {e}")
        self.main_app.update_status_bar(f"Feil under skanning: {e}", 100)
        self.scan_button.setEnabled(True)

    def show_bundle_context_menu(self, position):
        item = self.results_tree.itemAt(position)
        if not item or item.parent(): return
        menu = QMenu()
        copy_action = QAction("Kopier for EVE Multibuy", self)
        copy_action.triggered.connect(lambda: self.copy_bundle_to_clipboard(item))
        menu.addAction(copy_action)
        menu.exec(self.results_tree.viewport().mapToGlobal(position))

    def copy_bundle_to_clipboard(self, bundle_item):
        bundle_data = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        if not bundle_data or 'items' not in bundle_data: return
        multibuy_text = "\n".join([f"{item['name']}\t{item['quantity']}" for item in bundle_data['items']])
        QApplication.clipboard().setText(multibuy_text)
        self.main_app.update_status_bar(f"Kopierte {len(bundle_data['items'])} varer til utklippstavlen.")