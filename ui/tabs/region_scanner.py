import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLineEdit, QTableWidget, QHeaderView,
                             QTableWidgetItem, QLabel, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
from logic.scanners.region import find_best_trades_in_region

# --- Worker for multi-threading ---
class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    result = pyqtSignal(list)
    progress = pyqtSignal(str)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            # Pass the progress signal to the scanner function
            self.kwargs['status_callback'] = self.signals.progress.emit
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit(e)
        finally:
            self.signals.finished.emit()

# --- Main Region Scanner Tab Class ---
class RegionScannerTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.threadpool = QThreadPool()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()
        self.region_name_input = QLineEdit()
        self.region_name_input.setPlaceholderText("Region Name (e.g., The Forge)")
        
        self.min_profit_input = QSpinBox()
        self.min_profit_input.setRange(0, 1_000_000_000); self.min_profit_input.setSingleStep(10000); self.min_profit_input.setValue(100000)
        self.min_margin_input = QDoubleSpinBox()
        self.min_margin_input.setRange(0, 1000); self.min_margin_input.setSingleStep(1); self.min_margin_input.setValue(10)
        
        self.scan_region_button = QPushButton("Scan Region")
        self.scan_region_button.clicked.connect(self.run_region_scan)

        controls_layout.addWidget(QLabel("Region:")); controls_layout.addWidget(self.region_name_input)
        controls_layout.addWidget(QLabel("Min Profit:")); controls_layout.addWidget(self.min_profit_input)
        controls_layout.addWidget(QLabel("Min Margin (%):")); controls_layout.addWidget(self.min_margin_input)
        controls_layout.addWidget(self.scan_region_button)
        layout.addLayout(controls_layout)

        self.region_deals_table = QTableWidget()
        self.region_deals_table.setColumnCount(7)
        self.region_deals_table.setHorizontalHeaderLabels(["Item Name", "Buy Station", "Sell Station", "Profit", "Margin (%)", "Daily Volume", "Price"])
        self.region_deals_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.region_deals_table.setSortingEnabled(True)
        layout.addWidget(self.region_deals_table)

    def run_region_scan(self):
        region_name = self.region_name_input.text()
        if not region_name:
            self.main_app.update_status_bar("Error: Region name is required.")
            return

        min_profit = self.min_profit_input.value()
        min_margin = self.min_margin_input.value()

        self.scan_region_button.setEnabled(False)
        self.main_app.update_status_bar(f"Starting region scan for {region_name} in background...")
        self.main_app.log_message(f"Region Scan: Starting scan for '{region_name}'...")
        
        worker = Worker(find_best_trades_in_region, region_name, min_profit, min_margin)
        worker.signals.result.connect(self.display_region_deals)
        worker.signals.error.connect(self.on_scan_error)
        # --- FIX: Connect progress signal to a new method that logs AND updates status bar ---
        worker.signals.progress.connect(self.update_progress)
        worker.signals.finished.connect(self.on_scan_finished)
        
        self.threadpool.start(worker)

    def update_progress(self, message):
        """Updates both the status bar and the log window."""
        self.main_app.update_status_bar(message)
        self.main_app.log_message(f"Region Scan: {message}")

    def on_scan_error(self, e):
        logging.error(f"Error in region scan: {e}", exc_info=True)
        self.main_app.log_message(f"Region Scan ERROR: {e}")
        self.main_app.update_status_bar(f"Error: {e}")

    def on_scan_finished(self):
        """Re-enables the button and logs completion."""
        self.scan_region_button.setEnabled(True)
        self.main_app.log_message("Region Scan: Background task finished.")


    def display_region_deals(self, deals):
        self.main_app.log_message(f"Region Scan: Displaying {len(deals)} profitable deals.")
        self.region_deals_table.setRowCount(0)
        for deal in deals:
            row = self.region_deals_table.rowCount()
            self.region_deals_table.insertRow(row)
            self.region_deals_table.setItem(row, 0, QTableWidgetItem(deal['item_name']))
            self.region_deals_table.setItem(row, 1, QTableWidgetItem(deal['buy_station']))
            self.region_deals_table.setItem(row, 2, QTableWidgetItem(deal['sell_station']))
            self.region_deals_table.setItem(row, 3, QTableWidgetItem(f"{deal['profit']:,.2f} ISK"))
            self.region_deals_table.setItem(row, 4, QTableWidgetItem(f"{deal['margin']:.2f}%"))
            self.region_deals_table.setItem(row, 5, QTableWidgetItem(deal['volume_str']))
            self.region_deals_table.setItem(row, 6, QTableWidgetItem(f"{deal['price']:,.2f} ISK"))
        self.main_app.update_status_bar("Region scan complete.")