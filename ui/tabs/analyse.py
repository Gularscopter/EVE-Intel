from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit, QFileDialog, QLabel
import pandas as pd

class AnalyseTab(QWidget):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.label = QLabel("This tab is for analyzing market data from a file.")
        layout.addWidget(self.label)
        
        self.load_button = QPushButton("Load Market Data")
        self.load_button.clicked.connect(self.load_data)
        layout.addWidget(self.load_button)
        
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        layout.addWidget(self.text_area)

    def load_data(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Market Data", "", "CSV Files (*.csv);;All Files (*)")
        if file_name:
            try:
                df = pd.read_csv(file_name)
                # Enkel analyse: Viser de første radene og litt info
                self.text_area.setText(f"File Loaded: {file_name}\n\n")
                self.text_area.append("First 5 rows:\n")
                self.text_area.append(df.head().to_string())
                self.text_area.append("\n\nData Info:\n")
                
                # Pandas info() skriver til buffer, så vi må fange det opp
                import io
                buffer = io.StringIO()
                df.info(buf=buffer)
                self.text_area.append(buffer.getvalue())

                self.main_app.update_status_bar(f"Successfully loaded and analyzed {file_name}")
            except Exception as e:
                self.main_app.log_message(f"Error loading data for analysis: {e}")
                self.text_area.setText(f"Could not load or parse the file.\nError: {e}")
