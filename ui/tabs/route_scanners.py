import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QTableWidget, QHeaderView,
                             QTableWidgetItem, QLabel, QSpinBox, QDoubleSpinBox)
from logic.scanners.route import find_best_trades_along_route

class RouteScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        controls_layout = QHBoxLayout()
        self.start_system_input = QLineEdit()
        self.start_system_input.setPlaceholderText("Start System")
        self.end_system_input = QLineEdit()
        self.end_system_input.setPlaceholderText("End System")
        
        self.max_jumps_input = QSpinBox()
        self.max_jumps_input.setRange(1, 100)
        self.max_jumps_input.setValue(10)

        self.scan_route_button = QPushButton("Scan Route")
        self.scan_route_button.clicked.connect(self.run_route_scan)
        
        controls_layout.addWidget(QLabel("Start:"))
        controls_layout.addWidget(self.start_system_input)
        controls_layout.addWidget(QLabel("End:"))
        controls_layout.addWidget(self.end_system_input)
        controls_layout.addWidget(QLabel("Max Jumps from route:"))
        controls_layout.addWidget(self.max_jumps_input)
        controls_layout.addWidget(self.scan_route_button)
        layout.addLayout(controls_layout)

        # Results table
        self.route_deals_table = QTableWidget()
        self.route_deals_table.setColumnCount(6)
        self.route_deals_table.setHorizontalHeaderLabels([
            "Item Name", "Buy Station", "Sell Station", "Profit", "Margin (%)", "Jumps"
        ])
        self.route_deals_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.route_deals_table.setSortingEnabled(True)
        layout.addWidget(self.route_deals_table)

    def run_route_scan(self):
        start_system = self.start_system_input.text()
        end_system = self.end_system_input.text()
        max_jumps_from_route = self.max_jumps_input.value()

        if not start_system or not end_system:
            self.main_app.update_status_bar("Error: Start and End systems are required.")
            return

        self.main_app.update_status_bar("Scanning route... This could take some time.")

        try:
            # Pass the status update callback to the scanner function
            deals = find_best_trades_along_route(start_system, end_system, max_jumps_from_route, self.main_app.update_status_bar)
            self.display_route_deals(deals)
            self.main_app.update_status_bar("Route scan complete.")
        except Exception as e:
            logging.error(f"Error in route scan: {e}", exc_info=True)
            self.main_app.log_message(f"Route Scan Error: {e}")

    def display_route_deals(self, deals):
        self.route_deals_table.setRowCount(0)
        for deal in deals:
            row = self.route_deals_table.rowCount()
            self.route_deals_table.insertRow(row)
            self.route_deals_table.setItem(row, 0, QTableWidgetItem(deal['item_name']))
            self.route_deals_table.setItem(row, 1, QTableWidgetItem(deal['buy_station']))
            self.route_deals_table.setItem(row, 2, QTableWidgetItem(deal['sell_station']))
            self.route_deals_table.setItem(row, 3, QTableWidgetItem(f"{deal['profit']:,.2f} ISK"))
            self.route_deals_table.setItem(row, 4, QTableWidgetItem(f"{deal['margin']:.2f}%"))
            self.route_deals_table.setItem(row, 5, QTableWidgetItem(str(deal['jumps'])))
