from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTableWidget, QTableWidgetItem, QProgressBar, QHBoxLayout, QGroupBox, QFormLayout, QCompleter, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
from logic.scanners import bpo
from db import get_all_manufacturable_item_names
import logging

class ManufacturingTab(QWidget):
    progress_updated = pyqtSignal(str, int)

    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()
        self.load_initial_data()
        self.progress_updated.connect(self.update_progress_bar)

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Input Group ---
        input_group = QGroupBox("Manufacturing Calculation")
        form_layout = QFormLayout()

        self.bpo_search = self.create_completer_combo()
        form_layout.addRow("Blueprint Product:", self.bpo_search)

        self.me_input = QLineEdit("10")
        form_layout.addRow("Material Efficiency (%):", self.me_input)

        self.te_input = QLineEdit("20")
        form_layout.addRow("Time Efficiency (%):", self.te_input)
        
        self.tax_input = QLineEdit("2.5")
        form_layout.addRow("System Cost Index (%):", self.tax_input)

        form_layout.addRow("Market:", QLabel("Jita IV - Moon 4 - Caldari Navy Assembly Plant"))

        self.calculate_btn = QPushButton("Calculate Profitability")
        self.calculate_btn.clicked.connect(self.run_calculation)
        form_layout.addRow(self.calculate_btn)
        
        input_group.setLayout(form_layout)
        main_layout.addWidget(input_group)
        
        # --- Progress Bar ---
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # --- Results Table ---
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(['Blueprint', 'Manufacturing Cost', 'Market Price', 'Profit', 'Margin (%)'])
        main_layout.addWidget(self.results_table)

        # --- Materials Table ---
        materials_group = QGroupBox("Required Materials")
        materials_layout = QVBoxLayout(materials_group)
        self.materials_table = QTableWidget()
        self.materials_table.setColumnCount(4)
        self.materials_table.setHorizontalHeaderLabels(['Material', 'Quantity', 'Price/Unit', 'Total Cost'])
        materials_layout.addWidget(self.materials_table)
        main_layout.addWidget(materials_group)

        self.controls = [self.bpo_search, self.me_input, self.te_input, self.tax_input, self.calculate_btn]

    def create_completer_combo(self):
        """
        Creates a QComboBox with a QCompleter, styled to act like a search box.
        This mirrors the working implementation from the Analyse tab.
        """
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.lineEdit().setPlaceholderText("Search for a Blueprint Producing...")
        
        # Create completer without model first, like in the working example
        completer = QCompleter(self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setPopup(combo.view())
        
        combo.setCompleter(completer)
        return combo

    def load_initial_data(self):
        """
        Loads data and sets the model for the completer, separate from UI creation.
        """
        manufacturable_items = get_all_manufacturable_item_names()
        logging.info(f"Loaded {len(manufacturable_items)} manufacturable items for completer.")
        model = QStringListModel(manufacturable_items)
        
        # Get the already-created completer and set its model now
        self.bpo_search.completer().setModel(model)

    def set_controls_enabled(self, enabled):
        for control in self.controls:
            control.setEnabled(enabled)

    def run_calculation(self):
        product_name = self.bpo_search.currentText()
        try:
            me_level = float(self.me_input.text())
            te_level = float(self.te_input.text())
            tax_rate = float(self.tax_input.text())
        except ValueError:
            self.main_app.update_status_bar("Invalid ME/TE/Tax value. Please enter a number.")
            return
        
        if not product_name:
            self.main_app.update_status_bar("Please enter a product name to search for a blueprint.")
            return

        self.set_controls_enabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.results_table.setRowCount(0)
        self.materials_table.setRowCount(0)
        
        self.main_app.run_in_thread(
            bpo.find_profitable_bpos,
            on_success=self.on_calculation_success,
            on_error=self.on_calculation_error,
            status_callback=self.handle_progress_update,
            product_name=product_name,
            me_level=me_level,
            te_level=te_level,
            tax_rate=tax_rate
        )

    def handle_progress_update(self, message, percentage):
        self.progress_updated.emit(message, percentage)

    def update_progress_bar(self, message, percentage):
        self.main_app.update_status_bar(message)
        self.progress_bar.setValue(percentage)

    def on_calculation_success(self, results):
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        
        self.results_table.setRowCount(0)
        self.materials_table.setRowCount(0)

        if not results:
            self.main_app.update_status_bar("No profitable blueprints found matching the criteria.")
            return

        # Since we are analyzing one BPO at a time, we'll just use the first result.
        result_data = results[0]

        # Populate the main results table
        self.results_table.insertRow(0)
        self.results_table.setItem(0, 0, QTableWidgetItem(result_data.get('name', 'N/A')))
        self.results_table.setItem(0, 1, QTableWidgetItem(f"{result_data.get('cost', 0):,.2f} ISK"))
        self.results_table.setItem(0, 2, QTableWidgetItem(f"{result_data.get('price', 0):,.2f} ISK"))
        self.results_table.setItem(0, 3, QTableWidgetItem(f"{result_data.get('profit', 0):,.2f} ISK"))
        self.results_table.setItem(0, 4, QTableWidgetItem(f"{result_data.get('margin', 0):.2f}%"))
        
        # Populate the materials table
        materials = result_data.get('materials', [])
        for i, material in enumerate(materials):
            self.materials_table.insertRow(i)
            self.materials_table.setItem(i, 0, QTableWidgetItem(material.get('name', 'N/A')))
            self.materials_table.setItem(i, 1, QTableWidgetItem(f"{material.get('quantity', 0):,.2f}"))
            self.materials_table.setItem(i, 2, QTableWidgetItem(f"{material.get('price_per_unit', 0):,.2f} ISK"))
            self.materials_table.setItem(i, 3, QTableWidgetItem(f"{material.get('total_cost', 0):,.2f} ISK"))

        self.main_app.update_status_bar("Calculation complete.")

    def on_calculation_error(self, error):
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        logging.error(f"Error during manufacturing calculation: {error}")
        self.main_app.update_status_bar(f"Error: {error}")
