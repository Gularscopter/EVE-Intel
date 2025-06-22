import logging
import time
import config
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QHeaderView,
                             QLabel, QDoubleSpinBox, QComboBox, QTreeWidget,
                             QTreeWidgetItem, QCheckBox, QCompleter, QMenu, QApplication, QGridLayout)
from PyQt6.QtGui import QAction, QFont, QColor, QGuiApplication
from PyQt6.QtCore import Qt, QStringListModel
import db
from logic.scanners.galaxy import run_galaxy_scan, build_bundles_from_trades
from logic.route_planner import find_shortest_path

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
        header = self.results_tree.header()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
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
        self.results_tree.customContextMenuRequested.connect(self.show_context_menu)

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
        config.save_config()

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
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self)
        combo.setCompleter(completer)
        return combo

    def load_region_data(self):
        self.all_regions = db.get_all_region_names()
        model = QStringListModel(self.all_regions)
        
        buy_completer = self.buy_region_combo.completer()
        if buy_completer:
            buy_completer.setModel(model)
        self.buy_region_combo.addItems(self.all_regions)
        
        sell_completer = self.sell_region_combo.completer()
        if sell_completer:
            sell_completer.setModel(model)
        self.sell_region_combo.addItems(self.all_regions)

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
            self.main_app.log_message("Start- og mål-region kan ikke være den samme.", "error"); return

        self.set_controls_enabled(False)
        self.main_app.log_message(f"Søker rute fra {scan_config['buy_region']} til {scan_config['sell_region']}...", "info")
        self.results_tree.clear(); self.full_scan_results = []
        self.main_app.run_in_thread(
            run_galaxy_scan, 
            on_success=self.on_scan_success, 
            on_error=self.on_scan_error, 
            scan_config=scan_config
        )

    def on_scan_success(self, all_trades):
        if not all_trades:
            self.main_app.log_message("Ingen handler funnet som matcher kriterien.", "info")
            self.set_controls_enabled(True)
            return
        self.full_scan_results = all_trades
        self.main_app.log_message(f"Fant {len(all_trades)} mulige handler. Bygger pakker...", "info")
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
        
        self.main_app.log_message("Bygger pakker med gjeldende filter...", "info")
        self.main_app.run_in_thread(
            build_bundles_from_trades, 
            on_success=self.display_bundles, 
            on_error=self.on_scan_error,
            all_trades=self.full_scan_results, 
            scan_config=scan_config
        )

    def get_system_names_from_ids(self, system_ids):
        names_to_fetch = [sys_id for sys_id in system_ids if sys_id not in self.system_name_cache]
        if names_to_fetch:
            # Assuming get_system_names returns a dict {id: name}
            fetched_names = db.get_system_names(names_to_fetch)
            self.system_name_cache.update(fetched_names)
        return [self.system_name_cache.get(sys_id, f"Ukjent system ({sys_id})") for sys_id in system_ids]

    def display_bundles(self, bundles):
        self.results_tree.clear()
        print("DEBUG: Bundles received by UI:")
        for bundle in bundles:
            print(bundle)
            profit = bundle['total_profit']
            jumps = bundle.get('jumps', 'N/A')
            bundle_item: QTreeWidgetItem = QTreeWidgetItem(self.results_tree)
            # QTreeWidgetItem always returns a valid item with a valid parent; setText is always valid
            bundle_item.setText(0, f"Pakke Profitt: {profit:,.2f} ISK")  # type: ignore
            bundle_item.setText(2, f"{profit:,.2f}")  # type: ignore
            bundle_item.setText(3, bundle.get('station_name', 'Multi-Stasjon'))  # type: ignore
            bundle_item.setText(4, bundle.get('station_name', 'Multi-Stasjon'))  # type: ignore
            bundle_item.setData(0, Qt.ItemDataRole.UserRole, bundle)
            for item in bundle.get('items', []):
                buy_location_name = item.get('buy_station_name', "Ukjent Stasjon/Struktur")
                sell_location_name = item.get('sell_station_name', "Ukjent Stasjon/Struktur")
                child: QTreeWidgetItem = QTreeWidgetItem(bundle_item)
                child.setText(0, item.get('item_name', ''))  # type: ignore
                child.setText(1, str(item.get('fitted_quantity', '')))  # type: ignore
                child.setText(2, f"{item.get('total_profit_for_item', 0):,.2f}")  # type: ignore
                child.setText(3, buy_location_name)  # type: ignore
                child.setText(4, sell_location_name)  # type: ignore
                child.setText(5, str(item.get('jumps', '')))  # type: ignore
                child.setText(6, item.get('volume_str', ''))  # type: ignore
                print(f"SetText: {buy_location_name} -> col 3, {sell_location_name} -> col 4")
        self.main_app.log_message(f"Viser {len(bundles)} handelspakke(r).", "info")
        self.results_tree.repaint()
        self.set_controls_enabled(True)

    def on_scan_error(self, e):
        self.set_controls_enabled(True)
        self.main_app.log_message(f"En feil oppstod under skanning: {e}", "error")
        logging.error(f"Galaxy scan error: {e}", exc_info=True)

    def show_context_menu(self, position):
        item = self.results_tree.itemAt(position)
        if item is None:
            return
        # Only allow context menu on bundle rows (top-level items)
        if item.parent() is not None:
            return
        menu = QMenu()
        push_action = QAction('Push route to EVE', self)
        push_action.triggered.connect(lambda: self.push_route_to_eve(item))
        menu.addAction(push_action)
        # --- Add Copy Wares to Clipboard Submenu ---
        multibuy_menu = QMenu('Copy wares for Multibuy', self)
        # Gather wares by buy station
        wares_by_station = {}
        for i in range(item.childCount()):
            child = item.child(i)
            if child is None:
                continue
            station = child.text(3)
            name = child.text(0)
            qty = child.text(1)
            try:
                if name and int(qty) > 0:
                    wares_by_station.setdefault(station, []).append((name, qty))
            except Exception:
                continue
        for station, wares in wares_by_station.items():
            action = QAction(station, self)
            action.triggered.connect(lambda checked, s=station: self.copy_wares_for_station(item, s))
            multibuy_menu.addAction(action)
        if wares_by_station:
            menu.addMenu(multibuy_menu)
        viewport = self.results_tree.viewport()
        if viewport is not None:
            menu.exec(viewport.mapToGlobal(position))

    def push_route_to_eve(self, bundle_item):
        bundle = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        route_plan = bundle.get('full_route_plan')
        if not route_plan:
            self.main_app.log_message("Ingen rute å pushe.", "warning")
            return
        token = self.main_app.auth_manager.get_valid_token()
        char_id = self.main_app.character_id
        if not token or not char_id:
            self.main_app.log_message("Du må være logget inn for å pushe rute til EVE.", "error")
            return
        self.main_app.log_message("Pusher rute til EVE...", "info")
        self.main_app.run_in_thread(
            self._esi_route_setter_worker,
            on_success=self.on_set_route_success,
            on_error=self.on_set_route_error,
            route_plan=route_plan,
            access_token=token
        )

    def _esi_route_setter_worker(self, route_plan, access_token):
        import time
        import sys
        import os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
        import api
        # First waypoint clears the old route
        api.add_waypoint(route_plan[0], access_token, clear_other_waypoints=True)
        time.sleep(1.1) # ESI rate limit
        # Add subsequent waypoints
        for waypoint_id in route_plan[1:]:
            api.add_waypoint(waypoint_id, access_token, add_to_beginning=False)
            time.sleep(1.1)
        return "Rute pushet til EVE!"

    def on_set_route_success(self, result):
        self.main_app.log_message(result, "info")

    def on_set_route_error(self, error):
        self.main_app.log_message(f"Feil ved pushing av rute: {error}", "error")
        import logging
        logging.error(f"Push route error: {error}", exc_info=True)

    def calculate_optimal_route(self, bundle_item):
        bundle_data = bundle_item.data(0, Qt.ItemDataRole.UserRole)
        if not bundle_data: return
        
        current_loc_id = self.main_app.auth_manager.get_current_character_location()
        # Patch: ensure current_loc_id is an int (system ID)
        if isinstance(current_loc_id, dict):
            current_loc_id = current_loc_id.get('system_id') or current_loc_id.get('location_id')
        if not current_loc_id or not isinstance(current_loc_id, int):
            self.main_app.log_message("Kan ikke hente gyldig system-ID for nåværende posisjon.", "error")
            return

        all_buy_systems = set([trade['buy_system_id'] for trade in bundle_data['trades']])
        all_buy_systems.add(current_loc_id)
        
        self.main_app.log_message("Planlegger optimal kjøpsrute...", "info")
        self.main_app.run_in_thread(
            self._tsp_worker,
            on_success=lambda result: self.display_optimal_route(bundle_item, "buy", result),
            all_system_ids=list(all_buy_systems),
            start_system_id=current_loc_id,
            waypoint_ids=list(set([trade['buy_system_id'] for trade in bundle_data['trades']])))

        all_sell_systems = set([trade['sell_system_id'] for trade in bundle_data['trades']])
        last_buy_system = self.get_last_system_from_route(bundle_item, "buy") or current_loc_id
        all_sell_systems.add(last_buy_system)
        
        self.main_app.log_message("Planlegger optimal salgsrute...", "info")
        self.main_app.run_in_thread(
            self._tsp_worker,
            on_success=lambda result: self.display_optimal_route(bundle_item, "sell", result),
            all_system_ids=list(all_sell_systems),
            start_system_id=last_buy_system,
            waypoint_ids=list(set([trade['sell_system_id'] for trade in bundle_data['trades']])))

    def get_last_system_from_route(self, bundle_item, route_type):
        for i in range(bundle_item.childCount()):
            child = bundle_item.child(i)
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(child_data, dict) and child_data.get("type") == "route" and child_data.get("route_type") == route_type:
                path = child_data.get("path_ids", [])
                if path:
                    return path[-1]
        return None

    def _tsp_worker(self, all_system_ids, start_system_id, waypoint_ids):
        path, distance = find_shortest_path(all_system_ids, start_system_id, waypoint_ids)
        path_names = self.get_system_names_from_ids(path)
        return {"path": path_names, "distance": distance, "path_ids": path}

    def display_optimal_route(self, bundle_item, route_type, route_info):
        path = route_info.get("path", [])
        distance = route_info.get("distance", 0)

        route_item = None
        for i in range(bundle_item.childCount()):
            child = bundle_item.child(i)
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(child_data, dict) and child_data.get("type") == "route" and child_data.get("route_type") == route_type:
                route_item = child
                break
        
        if route_item is None:
            route_item = QTreeWidgetItem(bundle_item)

        if not path:
            if route_item is not None:
                route_item.setText(0, f"Optimal {route_type} route: Kunne ikke kalkulere.")
            return

        route_str = " -> ".join(path)
        if route_item is not None:
            route_item.setText(0, f"Optimal {route_type} rute ({distance} hopp): {route_str}")
            route_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "route", "route_type": route_type, "path_ids": route_info.get("path_ids", [])})
            bundle_item.setExpanded(True)

    def copy_wares_for_station(self, bundle_item, station_name):
        lines = []
        for i in range(bundle_item.childCount()):
            child = bundle_item.child(i)
            if child is None:
                continue
            name = child.text(0)
            qty = child.text(1)
            station = child.text(3)
            try:
                if name and int(qty) > 0 and station == station_name:
                    lines.append(f"{name}\t{qty}")
            except Exception:
                continue
        if lines:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText("\n".join(lines))