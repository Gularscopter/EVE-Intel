from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel
from config import save_config

class SettingsTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.client_id_input = QLineEdit()
        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        form_layout.addRow("Client ID:", self.client_id_input)
        form_layout.addRow("Client Secret:", self.client_secret_input)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings)
        
        self.status_label = QLabel("")

        layout.addLayout(form_layout)
        layout.addWidget(self.save_button)
        layout.addWidget(self.status_label)
        layout.addStretch() # Pushes content to the top

    def load_settings(self):
        """Loads settings from the main app's config."""
        self.client_id_input.setText(self.main_app.get_config_value("CLIENT_ID", ""))
        self.client_secret_input.setText(self.main_app.get_config_value("CLIENT_SECRET", ""))
        self.main_app.log_message("Settings loaded.")

    def save_settings(self):
        """Saves the current settings to the main app's config."""
        self.main_app.set_config_value("CLIENT_ID", self.client_id_input.text())
        self.main_app.set_config_value("CLIENT_SECRET", self.client_secret_input.text())
        self.status_label.setText("Settings saved successfully!")
        self.main_app.update_status_bar("Configuration saved.")
        self.main_app.log_message("Settings saved.")

