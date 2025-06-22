import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QComboBox, QDoubleSpinBox, QCompleter, QGridLayout, QGroupBox)
from PyQt6.QtCore import QStringListModel, Qt
from functools import partial
import db
import config
from logic.calculations import get_single_item_analysis

class AnalyseTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.all_item_names = []
        self.result_labels = {}
        self.init_ui()
        self.load_initial_data()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        input_group = QGroupBox("Analyse-innstillinger")
        input_layout = QGridLayout(input_group)

        input_layout.addWidget(QLabel("Vare:"), 0, 0)
        self.item_combo = self.create_completer_combo()
        input_layout.addWidget(self.item_combo, 0, 1)

        input_layout.addWidget(QLabel("Kjøp fra:"), 1, 0)
        self.buy_station_combo = QComboBox()
        self.buy_station_combo.addItems(config.STATIONS_INFO.keys())
        input_layout.addWidget(self.buy_station_combo, 1, 1)

        input_layout.addWidget(QLabel("Selg til:"), 2, 0)
        self.sell_station_combo = QComboBox()
        self.sell_station_combo.addItems(config.STATIONS_INFO.keys())
        input_layout.addWidget(self.sell_station_combo, 2, 1)

        input_layout.addWidget(QLabel("Lasterom (m³):"), 3, 0)
        self.cargo_input = QDoubleSpinBox()
        self.cargo_input.setRange(0, 1000000); self.cargo_input.setValue(4000)
        self.cargo_input.setGroupSeparatorShown(True); self.cargo_input.setDecimals(0)
        input_layout.addWidget(self.cargo_input, 3, 1)
        
        button_layout = QHBoxLayout()
        self.run_vs_sell_button = QPushButton("Analyser mot Salgsordre (Seeding)")
        self.run_vs_buy_button = QPushButton("Analyser mot Kjøpsordre (Flipping)")
        
        self.run_vs_sell_button.clicked.connect(partial(self.run_analysis, 'sell_order'))
        self.run_vs_buy_button.clicked.connect(partial(self.run_analysis, 'buy_order'))

        button_layout.addWidget(self.run_vs_sell_button)
        button_layout.addWidget(self.run_vs_buy_button)
        input_layout.addLayout(button_layout, 4, 1)

        main_layout.addWidget(input_group)
        
        result_group = QGroupBox("Resultater")
        self.result_layout = QGridLayout(result_group)
        
        labels_info = {
            "buy_price": "Pris / enhet (Kjøp):", "sell_price": "Pris / enhet (Salg):",
            "buy_volume": "Volum på ordre (Kjøp):", "sell_volume": "Volum på ordre (Salg):",
            "transaction_cost": "Avgifter / enhet:", "profit_per_unit": "Netto profitt / enhet:",
            "units_per_trip": "Antall enheter per tur:", "total_investment": "Total investering:",
            "total_profit": "TOTAL NETTO PROFITT PER TUR:"
        }

        row = 0
        for key, text in labels_info.items():
            label_title = QLabel(text)
            label_value = QLabel("N/A")
            if key == 'total_profit':
                label_title.setStyleSheet("font-weight: bold; font-size: 14pt;")
                label_value.setStyleSheet("font-weight: bold; font-size: 14pt;")
            
            self.result_layout.addWidget(label_title, row, 0)
            self.result_layout.addWidget(label_value, row, 1, Qt.AlignmentFlag.AlignRight)
            self.result_labels[key] = label_value
            row += 1

        main_layout.addWidget(result_group)
        main_layout.addStretch()

    def create_completer_combo(self):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter(self)
        completer.setPopup(combo.view())
        combo.setCompleter(completer)
        combo.lineEdit().setPlaceholderText("Skriv for å søke...")
        return combo

    def load_initial_data(self):
        self.all_item_names = db.get_all_item_names()
        model = QStringListModel(self.all_item_names)
        completer = self.item_combo.completer()
        completer.setModel(model)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item_combo.setCurrentText("Tritanium")

    def run_analysis(self, analysis_type):
        for label in self.result_labels.values():
            label.setText("N/A"); label.setStyleSheet("")
        self.result_labels['total_profit'].setStyleSheet("font-weight: bold; font-size: 14pt;")

        analysis_config = {
            'item_name': self.item_combo.currentText(),
            'buy_station': self.buy_station_combo.currentText(),
            'sell_station': self.sell_station_combo.currentText(),
            'ship_cargo': self.cargo_input.value(),
            'brokers_fee_rate': float(self.main_app.get_config_value('brokers_fee', 3.0)),
            'sales_tax_rate': float(self.main_app.get_config_value('sales_tax', 8.0)),
            'analysis_type': analysis_type
        }
        
        self.main_app.update_status_bar(f"Analyserer {analysis_config['item_name']}...", 0)
        self.run_vs_buy_button.setEnabled(False); self.run_vs_sell_button.setEnabled(False)
        self.main_app.run_in_thread(
            get_single_item_analysis,
            on_success=self.display_results,
            on_error=self.on_analysis_error,
            analysis_config=analysis_config
        )

    def display_results(self, results):
        # --- DEBUG-UTSAGNFRASE ---
        print(f"\n--- DEBUG: Mottatt resultat i display_results ---")
        print(results)
        print("------------------------------------------------\n")
        # ---------------------------

        self.run_vs_buy_button.setEnabled(True); self.run_vs_sell_button.setEnabled(True)
        if 'error' in results:
            self.main_app.log_message(f"Analyse-feil: {results['error']}")
            self.main_app.update_status_bar("Analyse feilet.", 100)
            return

        self.result_labels['buy_price'].setText(f"{results.get('buy_price', 0):,.2f} ISK")
        self.result_labels['sell_price'].setText(f"{results.get('sell_price', 0):,.2f} ISK")
        self.result_labels['buy_volume'].setText(f"{results.get('buy_volume', 0):,}")
        self.result_labels['sell_volume'].setText(f"{results.get('sell_volume', 0):,}")
        self.result_labels['transaction_cost'].setText(f"{results.get('transaction_cost', 0):,.2f} ISK")
        self.result_labels['profit_per_unit'].setText(f"{results.get('profit_per_unit', 0):,.2f} ISK")
        self.result_labels['units_per_trip'].setText(f"{results.get('units_per_trip', 0):,} (basert på {results.get('item_volume', 0):.2f} m³)")
        self.result_labels['total_investment'].setText(f"{results.get('total_investment', 0):,.2f} ISK")
        self.result_labels['total_profit'].setText(f"{results.get('total_profit', 0):,.2f} ISK")

        profit_color = "green" if results.get('total_profit', 0) > 0 else "red"
        self.result_labels['total_profit'].setStyleSheet(f"font-weight: bold; font-size: 14pt; color: {profit_color};")
        self.main_app.update_status_bar("Analyse fullført.", 100)

    def on_analysis_error(self, e):
        self.run_vs_buy_button.setEnabled(True); self.run_vs_sell_button.setEnabled(True)
        self.main_app.log_message(f"Uventet feil i analyse: {e}")
        self.main_app.update_status_bar("Analyse feilet uventet.", 100)