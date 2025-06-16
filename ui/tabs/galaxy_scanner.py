import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QHeaderView, QTableWidgetItem, QLabel,
                             QSpinBox, QDoubleSpinBox)
from logic.scanners.galaxy import find_best_trades_galaxy

class GalaxyScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls_layout = QHBoxLayout()
        self.min_profit_input = QSpinBox()
        self.min_profit_input.setRange(0, 1_000_000_000)
        self.min_profit_input.setSingleStep(100000)
        self.min_profit_input.setValue(1000000)
        
        self.min_margin_input = QDoubleSpinBox()
        self.min_margin_input.setRange(0, 1000)
        self.min_margin_input.setSingleStep(1)
        self.min_margin_input.setValue(20)

        self.scan_galaxy_button = QPushButton("Scan Galaxy")
        self.scan_galaxy_button.clicked.connect(self.run_galaxy_scan)

        controls_layout.addWidget(QLabel("Min Profit:"))
        controls_layout.addWidget(self.min_profit_input)
        controls_layout.addWidget(QLabel("Min Margin (%):"))
        controls_layout.addWidget(self.min_margin_input)
        controls_layout.addWidget(self.scan_galaxy_button)
        layout.addLayout(controls_layout)

        # Results table
        self.galaxy_table = QTableWidget()
        self.galaxy_table.setColumnCount(6)
        self.galaxy_table.setHorizontalHeaderLabels([
            "Item Name", "Buy Region", "Sell Region", "Profit", "Margin (%)", "Volume"
        ])
        self.galaxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.galaxy_table.setSortingEnabled(True)
        layout.addWidget(self.galaxy_table)

    def run_galaxy_scan(self):
        min_profit = self.min_profit_input.value()
        min_margin = self.min_margin_input.value()

        self.main_app.update_status_bar("Scanning galaxy... This will take a very long time.")
        
        try:
            # This function needs a callback to update the status
            profitable_trades = find_best_trades_galaxy(min_profit, min_margin, self.main_app.update_status_bar)
            self.display_galaxy_results(profitable_trades)
            self.main_app.update_status_bar("Galaxy scan complete.")
        except Exception as e:
            logging.error(f"Error during galaxy scan: {e}", exc_info=True)
            self.main_app.log_message(f"Galaxy Scan Error: {e}")

    def display_galaxy_results(self, trades):
        self.galaxy_table.setRowCount(0)
        for trade in trades:
            row = self.galaxy_table.rowCount()
            self.galaxy_table.insertRow(row)
            self.galaxy_table.setItem(row, 0, QTableWidgetItem(trade['item_name']))
            self.galaxy_table.setItem(row, 1, QTableWidgetItem(trade['buy_region']))
            self.galaxy_table.setItem(row, 2, QTableWidgetItem(trade['sell_region']))
            self.galaxy_table.setItem(row, 3, QTableWidgetItem(f"{trade['profit']:,.2f} ISK"))
            self.galaxy_table.setItem(row, 4, QTableWidgetItem(f"{trade['margin']:.2f}%"))
            self.galaxy_table.setItem(row, 5, QTableWidgetItem(f"{trade['volume']:.2f} m³"))
