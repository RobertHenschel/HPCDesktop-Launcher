from typing import Any, Dict

from PyQt5.QtWidgets import QMainWindow, QLabel, QWidget, QVBoxLayout


def create_window(parent, context: Dict[str, Any]):
    """Factory function expected by the launcher.

    Must return a QMainWindow or QDialog (or any QWidget with .show()).
    The plugin MUST NOT create its own QApplication.
    """
    window = QMainWindow(parent)
    window.setWindowTitle("Jupyter OnRed")

    central = QWidget(window)
    layout = QVBoxLayout(central)
    layout.addWidget(QLabel("Hello from OnRed plugin!", central))
    layout.addWidget(QLabel(f"Base path: {context.get('base_path')}", central))
    layout.addWidget(QLabel(f"JSON: {context.get('json_path')}", central))
    window.setCentralWidget(central)
    window.resize(600, 400)
    return window


