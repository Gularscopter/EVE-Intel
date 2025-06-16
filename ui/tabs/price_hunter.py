import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QTableWidget, QHeaderView,
                             QTableWidgetItem, QLabel)
from PyQt6.QtCore import Qt
from logic.scanners.price_hunter import find_best_deals
from ui.components.item_detail_window import ItemDetailWindow

class PriceHunterTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.item_detail_window = None # To hold reference to the detail window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Top controls
        controls_layout = QHBoxLayout()
        self.start_station_input = QLineEdit()
        self.start_station_input.setPlaceholderText("Start Station (e.g., Jita IV - Moon 4...)")
        self.end_station_input = QLineEdit()
        self.end_station_input.setPlaceholderText("End Station (e.g., Amarr VIII...)")
        self.volume_input = QLineEdit()
        self.volume_input.setPlaceholderText("Max Volume (m³)")
        self.tax_input = QLineEdit()
        self.tax_input.setPlaceholderText("Tax Rate (%)")
        self.search_button = QPushButton("Search Best Deals")
        self.search_button.clicked.connect(self.run_price_hunter)

        controls_layout.addWidget(QLabel("Start:"))
        controls_layout.addWidget(self.start_station_input)
        controls_layout.addWidget(QLabel("End:"))
        controls_layout.addWidget(self.end_station_input)
        controls_layout.addWidget(QLabel("Volume:"))
        controls_layout.addWidget(self.volume_input)
        controls_layout.addWidget(QLabel("Tax:"))
        controls_layout.addWidget(self.tax_input)
        controls_layout.addWidget(self.search_button)

        layout.addLayout(controls_layout)

        # Table for results
        self.deals_table = QTableWidget()
        self.deals_table.setColumnCount(9)
        self.deals_table.setHorizontalHeaderLabels([
            "Item Name", "Buy Station", "Buy Price", "Sell Station", "Sell Price",
            "Profit per Unit", "Volume", "Profit per Jump", "Margin (%)"
        ])
        self.deals_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.deals_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.deals_table.setSortingEnabled(True)
        self.deals_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.deals_table.itemDoubleClicked.connect(self.show_item_details)
        layout.addWidget(self.deals_table)

    def run_price_hunter(self):
        start_station = self.start_station_input.text()
        end_station = self.end_station_input.text()
        
        try:
            max_volume = float(self.volume_input.text()) if self.volume_input.text() else float('inf')
            tax_rate = float(self.tax_input.text()) if self.tax_input.text() else 0.0
        except ValueError:
            self.main_app.update_status_bar("Error: Volume and Tax must be numbers.")
            return

        if not start_station or not end_station:
            self.main_app.update_status_bar("Error: Start and End stations are required.")
            return

        self.main_app.update_status_bar("Searching for best deals... This might take a while.")
        
        try:
            # The find_best_deals function needs a callback to update the status bar
            deals = find_best_deals(start_station, end_station, max_volume, tax_rate, self.main_app.update_status_bar)
            self.display_deals(deals)
            self.main_app.update_status_bar("Search complete.")
        except Exception as e:
            logging.error(f"Error in price hunter: {e}", exc_info=True)
            self.main_app.update_status_bar(f"Error: {e}")

    def display_deals(self, deals):
        self.deals_table.setRowCount(0)
        for deal in deals:
            row_position = self.deals_table.rowCount()
            self.deals_table.insertRow(row_position)
            
            # Store item_id in the first column's data role
            item_name_item = QTableWidgetItem(deal['item_name'])
            item_name_item.setData(Qt.ItemDataRole.UserRole, deal['item_id'])

            buy_price_item = QTableWidgetItem()
            buy_price_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['buy_price']:,.2f} ISK")
            
            sell_price_item = QTableWidgetItem()
            sell_price_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['sell_price']:,.2f} ISK")

            profit_item = QTableWidgetItem()
            profit_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['profit_per_unit']:,.2f} ISK")
            
            volume_item = QTableWidgetItem()
            volume_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['volume']:.2f} m³")

            profit_jump_item = QTableWidgetItem()
            profit_jump_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['profit_per_jump']:,.2f} ISK")

            margin_item = QTableWidgetItem()
            margin_item.setData(Qt.ItemDataRole.DisplayRole, f"{deal['margin']:.2f}%")


            self.deals_table.setItem(row_position, 0, item_name_item)
            self.deals_table.setItem(row_position, 1, QTableWidgetItem(deal['buy_station']))
            self.deals_table.setItem(row_position, 2, buy_price_item)
            self.deals_table.setItem(row_position, 3, QTableWidgetItem(deal['sell_station']))
            self.deals_table.setItem(row_position, 4, sell_price_item)
            self.deals_table.setItem(row_position, 5, profit_item)
            self.deals_table.setItem(row_position, 6, volume_item)
            self.deals_table.setItem(row_position, 7, profit_jump_item)
            self.deals_table.setItem(row_position, 8, margin_item)
    
    def show_item_details(self, item):
        # Get the item from the first column which holds the ID
        item_with_id = self.deals_table.item(item.row(), 0)
        item_id = item_with_id.data(Qt.ItemDataRole.UserRole)
        if item_id:
            # Create a new window or reuse an existing one
            if self.item_detail_window is None or not self.item_detail_window.isVisible():
                self.item_detail_window = ItemDetailWindow(item_id, self)
                self.item_detail_window.show()
            else:
                # If window is already open, just bring it to front
                self.item_detail_window.activateWindow()
                self.item_detail_window.raise_()

