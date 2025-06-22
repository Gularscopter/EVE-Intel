import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeWidget, QTreeWidgetItem,
                             QHeaderView, QLineEdit, QHBoxLayout, QLabel)
from PyQt6.QtCore import Qt
from api import get_character_assets_with_names

class AssetsTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Top controls
        controls_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Assets")
        self.refresh_button.clicked.connect(self.load_assets)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by item name or location...")
        self.filter_input.textChanged.connect(self.filter_assets)
        
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(QLabel("Filter:"))
        controls_layout.addWidget(self.filter_input)
        layout.addLayout(controls_layout)

        # Tree widget for assets
        self.assets_tree = QTreeWidget()
        self.assets_tree.setColumnCount(4)
        self.assets_tree.setHeaderLabels(["Item Name", "Location", "Quantity", "Volume (m³)"])
        self.assets_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.assets_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) # Allow resizing for name
        layout.addWidget(self.assets_tree)

    def load_assets(self):
        self.main_app.update_status_bar("Loading assets...")
        self.assets_tree.clear()
        
        if not self.main_app.character_id or not self.main_app.access_token:
            self.main_app.log_message("Cannot load assets: Not authenticated.")
            return

        try:
            assets_by_location = get_character_assets_with_names(self.main_app.character_id, self.main_app.access_token)
            
            for location_name, assets in assets_by_location.items():
                location_item = QTreeWidgetItem(self.assets_tree, [location_name])
                location_item.setExpanded(False) # Start collapsed
                
                for asset in assets:
                    asset_item = QTreeWidgetItem(location_item)
                    asset_item.setText(0, asset.get('name', 'Unknown Item'))
                    asset_item.setText(1, location_name) # Hide location for children for cleaner view
                    asset_item.setText(2, str(asset.get('quantity', 'N/A')))
                    asset_item.setText(3, f"{asset.get('volume', 0):.2f}")

            self.main_app.update_status_bar("Assets loaded successfully.")
        except Exception as e:
            logging.error(f"Error loading assets: {e}", exc_info=True)
            self.main_app.log_message(f"Failed to load assets: {e}")

    def filter_assets(self, text):
        search_text = text.lower()
        for i in range(self.assets_tree.topLevelItemCount()):
            location_item = self.assets_tree.topLevelItem(i)
            location_name_matches = search_text in location_item.text(0).lower()
            
            child_matches = False
            for j in range(location_item.childCount()):
                child_item = location_item.child(j)
                item_name_matches = search_text in child_item.text(0).lower()
                if item_name_matches:
                    child_item.setHidden(False)
                    child_matches = True
                else:
                    child_item.setHidden(True)
            
            # Hide location if no children match, unless the location name itself matches
            if not child_matches and not location_name_matches:
                location_item.setHidden(True)
            else:
                location_item.setHidden(False)
                # If there are matching children, ensure the parent is expanded
                if child_matches:
                    location_item.setExpanded(True)
