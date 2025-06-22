from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel
)
from .base_tab import BaseTab

class SettingsTab(BaseTab):
    def __init__(self, main_app, parent=None):
        super().__init__(main_app, parent)
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.client_id_input = QLineEdit()
        self.secret_key_input = QLineEdit()
        self.secret_key_input.setEchoMode(QLineEdit.EchoMode.Password)

        form_layout.addRow(QLabel("Client ID:"), self.client_id_input)
        form_layout.addRow(QLabel("Secret Key:"), self.secret_key_input)

        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings)

        layout.addLayout(form_layout)
        layout.addWidget(self.save_button)
        layout.addStretch()

    def load_settings(self):
        client_id = self.main_app.get_config_value("client_id")
        secret_key = self.main_app.get_config_value("secret_key")

        if client_id:
            self.client_id_input.setText(client_id)
        if secret_key:
            self.secret_key_input.setText(secret_key)

    def save_settings(self, _=None):
        self.main_app.set_config_value("client_id", self.client_id_input.text())
        self.main_app.set_config_value("secret_key", self.secret_key_input.text())
        self.main_app.log_message("Settings saved.", "info")

