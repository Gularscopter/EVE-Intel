import logging
import time
import config
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QHeaderView,
                             QLabel, QDoubleSpinBox, QComboBox, QTreeWidget,
                             QTreeWidgetItem, QCheckBox, QCompleter, QMenu, QApplication, QGridLayout)
from PyQt6.QtGui import QAction, QFont, QColor
from PyQt6.QtCore import Qt, QStringListModel
import db
import api
from logic.scanners.galaxy import run_galaxy_scan, build_bundles_from_trades

class GalaxyScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.all_regions = []
        self.full_scan_results = []
        self.system_name_cache = {}
        self.settings_key = "galaxy_scanner_settings"
        
        self.init_ui()
        self.load_region_data()
        self.load_settings()
        self.connect_signals()

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
        self.use_common_sell_station_check = QCheckBox("Bruk én felles salgsstasjon")
        checkbox_layout.addWidget(self.multistation_checkbox)
        checkbox_layout.addWidget(self.use_common_sell_station_check)
        bottom_controls.addLayout(checkbox_layout)

        sec_status_layout = QVBoxLayout()
        sec_status_layout.addWidget(QLabel("Inkluder kjøp fra:"))
        sec_hbox = QHBoxLayout()
        self.hisec_check = QCheckBox("High-sec")
        self.lowsec_check = QCheckBox("Low-sec")
        self.nullsec_check = QCheckBox("Null-sec")
        sec_hbox.addWidget(self.hisec_check); sec_hbox.addWidget(self.lowsec_check); sec_hbox.addWidget(self.nullsec_check)
        sec_status_layout.addLayout(sec_hbox)
        bottom_controls.addLayout(sec_status_layout)
        
        bottom_controls.addStretch()
        self.scan_button = QPushButton("Finn Rute")
        bottom_controls.addWidget(self.scan_button)
        main_layout.addLayout(bottom_controls)

        self.results_tree = QTreeWidget()
        headers = ["Pakke / Vare / Rute", "Antall", "Total Vare-Profitt", "Kjøpsstasjon", "Salgsstasjon", "Hopp", "Volum (Kjøp/Salg)"]
        self.results_tree.setHeaderLabels(headers)
        self.results_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        main_layout.addWidget(self.results_tree)
        
        self.controls = [
            self.buy_region_combo, self.sell_region_combo, self.cargo_capacity_input,
            self.max_investment_input, self.min_profit_total_input, self.min_profit_per_item_input,
            self.brokers_fee_input, self.sales_tax_input, self.multistation_checkbox,
            self.use_common_sell_station_check, self.hisec_check, self.lowsec_check,
            self.nullsec_check, self.scan_button
        ]

    def set_controls_enabled(self, enabled):
        """Aktiverer eller deaktiverer alle input-kontroller."""
        for control in self.controls:
            control.setEnabled(enabled)

    def connect_signals(self):
        for spinbox in [self.cargo_capacity_input, self.max_investment_input, self.min_profit_total_input, self.min_profit_per_item_input, self.brokers_fee_input, self.sales_tax_input]:
            spinbox.valueChanged.connect(self.save_settings)
        for checkbox in [self.multistation_checkbox, self.use_common_sell_station_check, self.hisec_check, self.lowsec_check, self.nullsec_check]:
            checkbox.stateChanged.connect(self.save_settings)
            checkbox.stateChanged.connect(self.update_display_from_filters)
        self.buy_region_combo.currentTextChanged.connect(self.save_settings)
        self.sell_region_combo.currentTextChanged.connect(self.save_settings)
        
        self.scan_button.clicked.connect(self.run_scan)
        self.results_tree.customContextMenuRequested.connect(self.show_bundle_context_menu)

    def save_settings(self):
        settings = {
            "buy_region": self.buy_region_combo.currentText(),
            "sell_region": self.sell_region_combo.currentText(),
            "cargo_capacity": self.cargo_capacity_input.value(),
            "max_investment": self.max_investment_input.value(),
            "min_profit_total": self.min_profit_total_input.value(),
            "min_profit_per_item": self.min_profit_per_item_input.value(),
            "brokers_fee": self.brokers_fee_input.value(),
            "sales_tax": self.sales_tax_input.value(),
            "allow_multistation": self.multistation_checkbox.isChecked(),
            "use_common_sell_station": self.use_common_sell_station_check.isChecked(),
            "include_hisec": self.hisec_check.isChecked(),
            "include_lowsec": self.lowsec_check.isChecked(),
            "include_nullsec": self.nullsec_check.isChecked(),
        }
        config.set(self.settings_key, settings)

    def load_settings(self):
        settings = config.get(self.settings_key)
        if not settings or not isinstance(settings, dict):
            self.hisec_check.setChecked(True) 
            self.multistation_checkbox.setChecked(True)
            self.save_settings()
            return

        self.buy_region_combo.setCurrentText(settings.get("buy_region", "The Forge"))
        self.sell_region_combo.setCurrentText(settings.get("sell_region", "Domain"))
        self.cargo_capacity_input.setValue(settings.get("cargo_capacity", 5000))
        self.max_investment_input.setValue(settings.get("max_investment", 100_000_000))
        self.min_profit_total_input.setValue(settings.get("min_profit_total", 1_000_000))
        self.min_profit_per_item_input.setValue(settings.get("min_profit_per_item", 100_000))
        self.brokers_fee_input.setValue(settings.get("brokers_fee", 2.5))
        self.sales_tax_input.setValue(settings.get("sales_tax", 1.5))
        self.multistation_checkbox.setChecked(settings.get("allow_multistation", True))
        self.use_common_sell_station_check.setChecked(settings.get("use_common_sell_station", False))
        self.hisec_check.setChecked(settings.get("include_hisec", True))
        self.lowsec_check.setChecked(settings.get("include_lowsec", False))
        self.nullsec_check.setChecked(settings.get("include_nullsec", False))
        logging.info("Galaxy scanner settings loaded.")

    def create_completer_combo(self):
        combo = QComboBox(); combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert); combo.setCompleter(QCompleter(self))
        return combo

    def load_region_data(self):
        self.all_regions = db.get_all_region_names(); model = QStringListModel(self.all_regions)
        self.buy_region_combo.completer().setModel(model); self.buy_region_combo.addItems(self.all_regions)
        self.sell_region_combo.completer().setModel(model); self.sell_region_combo.addItems(self.all_regions)

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
            'access_token': self.main_app.auth_manager.get_valid_token()
        }
        if scan_config['buy_region'] == scan_config['sell_region']:
            self.main_app.log_message("Start- og mål-region kan ikke være den samme."); return

        self.set_controls_enabled(False)
        self.main_app.update_status_bar(f"Søker rute fra {scan_config['buy_region']} til {scan_config['sell_region']}...", 0)
        self.results_tree.clear(); self.full_scan_results = []
        self.main_app.run_in_thread(run_galaxy_scan, on_success=self.on_scan_success, on_error=self.on_scan_error, scan_config=scan_config)

    def on_scan_success(self, all_trades):
        self.full_scan_results = all_trades
        self.update_display_from_filters()

    def update_display_from_filters(self, _=None):
        if not self.full_scan_results:
             self.set_controls_enabled(True)
             return

        self.set_controls_enabled(False)
        scan_config = {
            'ship_cargo_m3': self.cargo_capacity_input.value(), 'max_investment': self.max_investment_input.value(),
            'min_profit_total': self.min_profit_total_input.value(),
            'min_profit_per_item': self.min_profit_per_item_input.value(),
            'brokers_fee_rate': self.brokers_fee_input.value(), 'sales_tax_rate': self.sales_tax_input.value(),
            'allow_multistation': self.multistation_checkbox.isChecked(),
            'use_common_sell_station': self.use_common_sell_station_check.isChecked(),
            'include_hisec': self.hisec_check.isChecked(), 'include_lowsec': self.lowsec_check.isChecked(),
            'include_nullsec': self.nullsec_check.isChecked(),
            'character_id': self.main_app.character_id, 
            'access_token': self.main_app.auth_manager.get_valid_token()
        }
        
        self.main_app.update_status_bar("Bygger pakker med gjeldende filter...", 95)
        self.main_app.run_in_thread(build_bundles_from_trades, 
                                   on_success=self.display_bundles, 
                                   on_error=self.on_scan_error,
                                   all_trades=self.full_scan_results, 
                                   scan_config=scan_config)

    def get_system_names_from_ids(self, system_ids):
        names_to_fetch = [sys_id for sys_id in system_ids if sys_id not in self.system_name_cache]
        if names_to_fetch:
            fetched_names = db.get_system_names(names_to_fetch)
            self.system_name_cache.update(fetched_names)
        return [self.system_name_cache.get(sys_id, f"Ukjent system ({sys_id})") for sys_id in system_ids]

    def display_bundles(self, bundles):
        self.set_controls_enabled(True)
        self.main_app.update_status_bar(f"Viser {len(bundles)} handelspakke(r).", 100)
        self.results_tree.clear()
        if not bundles:
            root_item = QTreeWidgetItem(self.results_tree); root_item.setText(0, "Ingen pakker funnet med gjeldende filter.")
            return

        for i, bundle in enumerate(bundles):
            station_name = bundle.get('station_name', 'Ukjent')
            root_item = QTreeWidgetItem(self.results_tree)
            root_item.setData(0, Qt.ItemDataRole.UserRole, bundle)
            
            title = f"Pakke #{i+1}: Fra {station_name}"
            root_item.setText(0, title)
            root_item.setText(2, f"{bundle.get('total_profit', 0):,.2f} ISK")
            root_item.setText(3, f"Kost: {bundle.get('total_investment', 0):,.2f} ISK")
            root_item.setText(4, f"Volum: {bundle.get('total_volume', 0):,.2f} m³")
            
            all_jumps = [item.get('jumps') for item in bundle.get('items', []) if item.get('jumps') is not None]
            if all_jumps:
                min_jumps, max_jumps = min(all_jumps), max(all_jumps)
                jumps_text = f"{min_jumps}-{max_jumps}" if min_jumps != max_jumps else str(min_jumps)
                root_item.setText(5, jumps_text)

            for col in [2,3,4,5]: root_item.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            route_font = QFont(); route_font.setItalic(True); route_font.setBold(True)
            buy_route_color = QColor("#a6e22e")
            sell_route_color = QColor("#f92672")

            if 'buy_route_plan' in bundle:
                route_names = self.get_system_names_from_ids(bundle['buy_route_plan'])
                route_item = QTreeWidgetItem(root_item)
                route_text = f"Kjøpsrute ({bundle['buy_route_total_jumps']} hopp): {' → '.join(route_names)}"
                route_item.setText(0, route_text)
                route_item.setFont(0, route_font); route_item.setForeground(0, buy_route_color)
                route_item.setFirstColumnSpanned(True)

            if 'sell_route_plan' in bundle:
                route_names = self.get_system_names_from_ids(bundle['sell_route_plan'])
                route_item = QTreeWidgetItem(root_item)
                route_text = f"Salgsrute ({bundle['sell_route_total_jumps']} hopp): {' → '.join(route_names)}"
                route_item.setText(0, route_text)
                route_item.setFont(0, route_font); route_item.setForeground(0, sell_route_color)
                route_item.setFirstColumnSpanned(True)

            for item in bundle.get('items', []):
                child_item = QTreeWidgetItem(root_item)
                child_item.setText(0, f"  {item['name']}")
                child_item.setText(1, f"{item['quantity']:,}")
                child_item.setText(2, f"{item.get('total_profit_for_item', 0):,.2f} ISK")
                child_item.setText(3, item.get('buy_station_name'))
                child_item.setText(4, item.get('sell_station_name'))
                jumps = item.get('jumps')
                child_item.setText(5, str(jumps) if jumps is not None else "N/A")
                child_item.setText(6, item.get('volume_str'))
                for col in [1,2,5,6]: child_item.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.results_tree.expandAll()
        for i in range(self.results_tree.columnCount()):
            self.results_tree.resizeColumnToContents(i)
        self.results_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def on_scan_error(self, e):
        self.set_controls_enabled(True)
        logging.error(f"Error during galaxy scan: {e}", exc_info=True)
        self.main_app.log_message(f"Galaxy Scan Error: {str(e)}")
        self.main_app.update_status_bar(f"Feil under skanning: {e}", 100)

    def show_bundle_context_menu(self, position):
        item = self.results_tree.itemAt(position)
        if not item or item.parent(): return
        
        bundle_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not bundle_data: return

        menu = QMenu()
        
        copy_multibuy_action = QAction("Kopier for EVE Multibuy", self)
        copy_multibuy_action.triggered.connect(lambda: self.copy_bundle_to_clipboard(item))
        menu.addAction(copy_multibuy_action)
        
        if 'full_route_plan' in bundle_data:
            copy_route_action = QAction("Kopier full rute for Autopilot", self)
            copy_route_action.triggered.connect(lambda: self.copy_full_route_to_clipboard(item))
            menu.addAction(copy_route_action)
            
            set_esi_route_action = QAction("Sett rute i spillet via ESI", self)
            set_esi_route_action.triggered.connect(lambda: self.set_in_game_route(item))
            menu.addAction(set_esi_route_action)
        
        menu.exec(self.results_tree.viewport().mapToGlobal(position))

    def copy_bundle_to_clipboard(self, bundle_item):
        bundle_data = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        if not bundle_data or 'items' not in bundle_data: return
        multibuy_text = "\n".join([f"{item['name']}\t{item['quantity']}" for item in bundle_data['items']])
        QApplication.clipboard().setText(multibuy_text)
        self.main_app.update_status_bar(f"Kopierte {len(bundle_data['items'])} varer til utklippstavlen.")

    def copy_full_route_to_clipboard(self, bundle_item):
        bundle_data = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        if not bundle_data or 'full_route_plan' not in bundle_data: return
        
        route_ids = bundle_data['full_route_plan']
        route_names = self.get_system_names_from_ids(route_ids)
        
        route_text = "\n".join(route_names)
        QApplication.clipboard().setText(route_text)
        self.main_app.update_status_bar(f"Kopierte rute med {len(route_names)} stopp til utklippstavlen.")

    def set_in_game_route(self, bundle_item):
        bundle_data = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        route_plan = bundle_data.get('full_route_plan')
        if not route_plan:
            self.main_app.log_message("Fant ingen rute å sette.")
            return

        access_token = self.main_app.auth_manager.get_valid_token()
        if not access_token:
            self.main_app.log_message("Autentisering nødvendig for å sette rute.")
            return
        
        self.set_controls_enabled(False)
        self.main_app.run_in_thread(
            self._esi_route_setter_worker,
            on_success=self.on_set_route_success,
            on_error=self.on_set_route_error,
            route_plan=route_plan,
            access_token=access_token
        )

    def _esi_route_setter_worker(self, route_plan, access_token, status_callback):
        if len(route_plan) < 2:
            return {'status': 'Ruten har kun ett stopp (din nåværende posisjon). Ingen veipunkter å sette.'}

        waypoints_to_set = route_plan[1:]
        total_waypoints = len(waypoints_to_set)

        first_waypoint_id = waypoints_to_set[0]
        name = self.system_name_cache.get(first_waypoint_id, str(first_waypoint_id))
        status_callback(f"1/{total_waypoints}: Tømmer rute og setter start: {name}", int(100/total_waypoints * 1))
        
        success, message = api.set_waypoint(first_waypoint_id, access_token, clear_other_waypoints=True)
        if not success:
            raise Exception(message)

        if total_waypoints > 1:
            for i, system_id in enumerate(waypoints_to_set[1:], start=1):
                time.sleep(1.1)
                progress = int(100 / total_waypoints * (i + 1))
                name = self.system_name_cache.get(system_id, str(system_id))
                status_callback(f"{i+1}/{total_waypoints}: Setter veipunkt: {name}", progress)

                success, message = api.set_waypoint(system_id, access_token, clear_other_waypoints=False)
                if not success:
                    raise Exception(message)

        return {'status': f"Rute med {total_waypoints} stopp er satt i spillet!"}

    def on_set_route_success(self, result):
        self.set_controls_enabled(True)
        status = result.get('status', 'Rute satt!')
        self.main_app.log_message(status)
        self.main_app.update_status_bar(status, 100)

    def on_set_route_error(self, error):
        self.set_controls_enabled(True)
        logging.error(f"Feil ved ESI-rutesetting: {error}", exc_info=False)
        self.main_app.log_message(f"Feil ved ESI-rutesetting: {str(error)}")
        self.main_app.update_status_bar(f"Feil: {str(error)}", 100)