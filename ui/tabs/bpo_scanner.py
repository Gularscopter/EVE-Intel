import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QTableWidget, QHeaderView, QTableWidgetItem,
                             QLabel, QComboBox)
from logic.scanners.bpo import find_profitable_bpos

class BPOScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls_layout = QHBoxLayout()
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("Enter Region Name (e.g., The Forge)")
        self.scan_bpo_button = QPushButton("Scan BPOs")
        self.scan_bpo_button.clicked.connect(self.run_bpo_scan)
        
        controls_layout.addWidget(QLabel("Region:"))
        controls_layout.addWidget(self.region_input)
        controls_layout.addWidget(self.scan_bpo_button)
        layout.addLayout(controls_layout)

        # Results table
        self.bpo_table = QTableWidget()
        self.bpo_table.setColumnCount(5)
        self.bpo_table.setHorizontalHeaderLabels([
            "BPO Name", "Manufacturing Cost", "Sell Price", "Profit", "Margin (%)"
        ])
        self.bpo_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bpo_table.setSortingEnabled(True)
        layout.addWidget(self.bpo_table)

    def run_bpo_scan(self):
        region = self.region_input.text()
        if not region:
            self.main_app.update_status_bar("Please enter a region name.")
            return

        self.main_app.update_status_bar(f"Scanning BPOs in {region}... This may take a while.")
        
        try:
            # Note: This function might need access to the status bar update method
            # We can pass it as a callback if needed.
            profitable_bpos = find_profitable_bpos(region, self.main_app.update_status_bar)
            self.display_bpo_results(profitable_bpos)
            self.main_app.update_status_bar("BPO scan complete.")
        except Exception as e:
            logging.error(f"Error during BPO scan: {e}", exc_info=True)
            self.main_app.log_message(f"BPO Scan Error: {e}")

    def display_bpo_results(self, bpos):
        self.bpo_table.setRowCount(0)
        for bpo in bpos:
            row = self.bpo_table.rowCount()
            self.bpo_table.insertRow(row)
            self.bpo_table.setItem(row, 0, QTableWidgetItem(bpo['name']))
            self.bpo_table.setItem(row, 1, QTableWidgetItem(f"{bpo['cost']:,.2f} ISK"))
            self.bpo_table.setItem(row, 2, QTableWidgetItem(f"{bpo['price']:,.2f} ISK"))
            self.bpo_table.setItem(row, 3, QTableWidgetItem(f"{bpo['profit']:,.2f} ISK"))
            self.bpo_table.setItem(row, 4, QTableWidgetItem(f"{bpo['margin']:.2f}%"))
