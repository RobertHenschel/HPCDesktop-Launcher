from typing import Any, Dict

import os
from PyQt5.QtWidgets import (
    QMainWindow,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QRadioButton,
    QButtonGroup,
)
import subprocess
import shlex


def create_window(parent, context: Dict[str, Any]):
    """Factory function expected by the launcher.

    Must return a QMainWindow or QDialog (or any QWidget with .show()).
    The plugin MUST NOT create its own QApplication.
    """
    window = QMainWindow(parent)
    window.setWindowTitle("Jupyter OnRed")

    central = QWidget(window)
    root_layout = QVBoxLayout(central)

    # Top: Startup Directory selector
    startup_dir_layout = QHBoxLayout()
    startup_dir_label = QLabel("Startup Directory:", central)
    startup_dir_edit = QLineEdit(central)
    startup_dir_edit.setText(os.path.expanduser("~"))
    startup_dir_button = QPushButton("Browse…", central)

    def on_browse_startup_dir() -> None:
        current_path = startup_dir_edit.text() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(
            window,
            "Select Startup Directory",
            current_path,
        )
        if chosen:
            startup_dir_edit.setText(chosen)

    startup_dir_button.clicked.connect(on_browse_startup_dir)

    startup_dir_layout.addWidget(startup_dir_label)
    startup_dir_layout.addWidget(startup_dir_edit)
    startup_dir_layout.addWidget(startup_dir_button)

    # Next: Radio buttons for Jupyter flavor
    flavor_layout = QHBoxLayout()
    flavor_label = QLabel("Interface:", central)
    notebook_radio = QRadioButton("Jupyter Notebook", central)
    lab_radio = QRadioButton("Jupyter Lab", central)

    # Group for exclusivity; Notebook pre-selected
    flavor_group = QButtonGroup(window)
    flavor_group.setExclusive(True)
    flavor_group.addButton(notebook_radio)
    flavor_group.addButton(lab_radio)
    notebook_radio.setChecked(True)

    flavor_layout.addWidget(flavor_label)
    flavor_layout.addWidget(notebook_radio)
    flavor_layout.addWidget(lab_radio)
    flavor_layout.addStretch(1)

    # Bottom: centered Launch and Cancel buttons
    buttons_layout = QHBoxLayout()
    launch_button = QPushButton("Launch", central)
    cancel_button = QPushButton("Cancel", central)

    def on_cancel() -> None:
        window.close()

    def on_launch() -> None:
        selected_dir = startup_dir_edit.text().strip()
        selected_interface = "notebook" if notebook_radio.isChecked() else "lab"

        # Expose selections on the window for the launcher to read if desired
        setattr(window, "selected_startup_directory", selected_dir)
        setattr(window, "selected_interface", selected_interface)
        
        # Build the launch command chain
        interface_cmd = "jupyter-notebook" if selected_interface == "notebook" else "jupyter-lab"
        # Use a login shell to ensure the 'module' command is available
        chained_cmd = f"cd {shlex.quote(selected_dir)}; module load python; {interface_cmd}"

        try:
            subprocess.Popen(
                ["bash", "-lc", chained_cmd],
                start_new_session=True,
            )
        finally:
            # Close the window regardless; the server continues in the background
            window.close()

    cancel_button.clicked.connect(on_cancel)
    launch_button.clicked.connect(on_launch)

    buttons_layout.addStretch(1)
    buttons_layout.addWidget(launch_button)
    buttons_layout.addWidget(cancel_button)
    buttons_layout.addStretch(1)

    # Assemble layouts
    root_layout.addLayout(startup_dir_layout)
    root_layout.addLayout(flavor_layout)
    root_layout.addStretch(1)
    root_layout.addLayout(buttons_layout)

    window.setCentralWidget(central)
    window.resize(700, 200)
    return window


