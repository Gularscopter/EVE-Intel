import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QTableWidget, QHeaderView,
                             QTableWidgetItem, QLabel, QSpinBox, QDoubleSpinBox)
from logic.scanners.region import find_best_trades_in_region

class RegionScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls_layout = QHBoxLayout()
        self.region_name_input = QLineEdit()
        self.region_name_input.setPlaceholderText("Region Name (e.g., The Forge)")
        
        self.min_profit_input = QSpinBox()
        self.min_profit_input.setRange(0, 1_000_000_000)
        self.min_profit_input.setSingleStep(10000)
        self.min_profit_input.setValue(100000)

        self.min_margin_input = QDoubleSpinBox()
        self.min_margin_input.setRange(0, 1000)
        self.min_margin_input.setSingleStep(1)
        self.min_margin_input.setValue(10)
        
        self.scan_region_button = QPushButton("Scan Region")
        self.scan_region_button.clicked.connect(self.run_region_scan)

        controls_layout.addWidget(QLabel("Region:"))
        controls_layout.addWidget(self.region_name_input)
        controls_layout.addWidget(QLabel("Min Profit:"))
        controls_layout.addWidget(self.min_profit_input)
        controls_layout.addWidget(QLabel("Min Margin (%):"))
        controls_layout.addWidget(self.min_margin_input)
        controls_layout.addWidget(self.scan_region_button)
        layout.addLayout(controls_layout)

        # Results table
        self.region_deals_table = QTableWidget()
        self.region_deals_table.setColumnCount(7)
        self.region_deals_table.setHorizontalHeaderLabels([
            "Item Name", "Buy Station", "Sell Station", "Profit", "Margin (%)",
            "Daily Volume", "Price"
        ])
        self.region_deals_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.region_deals_table.setSortingEnabled(True)
        layout.addWidget(self.region_deals_table)

    def run_region_scan(self):
        region_name = self.region_name_input.text()
        min_profit = self.min_profit_input.value()
        min_margin = self.min_margin_input.value()

        if not region_name:
            self.main_app.update_status_bar("Error: Region name is required.")
            return

        self.main_app.update_status_bar(f"Scanning {region_name}... This may take a moment.")
        
        try:
            # Pass the status update callback to the scanner function
            deals = find_best_trades_in_region(region_name, min_profit, min_margin, self.main_app.update_status_bar)
            self.display_region_deals(deals)
            self.main_app.update_status_bar("Region scan complete.")
        except Exception as e:
            logging.error(f"Error in region scan: {e}", exc_info=True)
            self.main_app.log_message(f"Region Scan Error: {e}")

    def display_region_deals(self, deals):
        self.region_deals_table.setRowCount(0)
        for deal in deals:
            row = self.region_deals_table.rowCount()
            self.region_deals_table.insertRow(row)
            self.region_deals_table.setItem(row, 0, QTableWidgetItem(deal['item_name']))
            self.region_deals_table.setItem(row, 1, QTableWidgetItem(deal['buy_station']))
            self.region_deals_table.setItem(row, 2, QTableWidgetItem(deal['sell_station']))
            self.region_deals_table.setItem(row, 3, QTableWidgetItem(f"{deal['profit']:,.2f} ISK"))
            self.region_deals_table.setItem(row, 4, QTableWidgetItem(f"{deal['margin']:.2f}%"))
            self.region_deals_table.setItem(row, 5, QTableWidgetItem(f"{deal['volume_str']}"))
            self.region_deals_table.setItem(row, 6, QTableWidgetItem(f"{deal['price']:,.2f} ISK"))
