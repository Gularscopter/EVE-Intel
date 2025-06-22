from PyQt6.QtWidgets import QWidget

class BaseTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app

    def save_settings(self):
        """
        Base implementation for saving tab-specific settings.
        Subclasses should override this method to save their state.
        """
        pass 