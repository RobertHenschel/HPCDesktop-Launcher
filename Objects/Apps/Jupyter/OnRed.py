from typing import Any, Dict
import re

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
    QCheckBox,
    QToolButton,
    QComboBox,
)
from PyQt5.QtCore import Qt
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

    # Collapsible Advanced section (starts collapsed)
    advanced_toggle = QToolButton(central)
    advanced_toggle.setText("Advanced")
    advanced_toggle.setCheckable(True)
    advanced_toggle.setChecked(False)
    advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    advanced_toggle.setArrowType(Qt.RightArrow)

    advanced_content = QWidget(central)
    advanced_content_layout = QVBoxLayout(advanced_content)
    dont_record_checkbox = QCheckBox("Don't record history", advanced_content)
    dont_record_checkbox.setChecked(False)
    advanced_content_layout.addWidget(dont_record_checkbox)

    # Python module selection combobox
    module_row = QHBoxLayout()
    module_label = QLabel("Python module:", advanced_content)
    python_module_combo = QComboBox(advanced_content)
    python_module_combo.setEditable(False)
    module_row.addWidget(module_label)
    module_row.addWidget(python_module_combo)
    advanced_content_layout.addLayout(module_row)

    def _parse_available_python_modules(raw_text: str):
        modules = []
        default_module = None
        for line in raw_text.splitlines():
            for m in re.finditer(r"(python[^\s()]+)\s*(?:\(([^)]+)\))?", line):
                name = m.group(1)
                flags_raw = m.group(2) or ""
                flags_upper = flags_raw.upper()
                if name not in modules:
                    modules.append(name)
                if default_module is None:
                    if flags_upper == "D" or "DEFAULT" in flags_upper:
                        default_module = name
        return modules, default_module

    def _populate_python_modules_combo() -> None:
        try:
            # Use login shell so that 'module' is available; capture stderr as well
            result = subprocess.run(
                ["bash", "-lc", "module av python 2>&1"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "") + (result.stderr or "")
            modules, default_module = _parse_available_python_modules(output)
        except Exception:
            modules, default_module = [], None

        if modules:
            for name in modules:
                display = f"{name} (default)" if default_module and name == default_module else name
                python_module_combo.addItem(display, name)
            if "python" in modules:
                idx = python_module_combo.findData("python")
                python_module_combo.setCurrentIndex(idx if idx >= 0 else 0)
            elif default_module and default_module in modules:
                idx = python_module_combo.findData(default_module)
                python_module_combo.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                python_module_combo.setCurrentIndex(0)
        else:
            # Fallback if nothing detected
            python_module_combo.addItem("python", "python")
            python_module_combo.setCurrentIndex(0)

    _populate_python_modules_combo()
    advanced_content.setVisible(False)

    def on_advanced_toggled(checked: bool) -> None:
        advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        advanced_content.setVisible(checked)

    advanced_toggle.toggled.connect(on_advanced_toggled)

    # Bottom: centered Launch and Cancel buttons
    buttons_layout = QHBoxLayout()
    launch_button = QPushButton("Launch", central)
    cancel_button = QPushButton("Cancel", central)

    def on_cancel() -> None:
        window.close()

    def on_launch() -> None:
        selected_dir = startup_dir_edit.text().strip()
        selected_interface = "notebook" if notebook_radio.isChecked() else "lab"
        selected_python_module_data = python_module_combo.currentData()
        selected_python_module = str(selected_python_module_data or python_module_combo.currentText()).strip() or "python"
        label = "Notebook" if selected_interface == "notebook" else "Lab"
        leaf = os.path.basename(os.path.normpath(selected_dir)) or selected_dir

        # Expose selections on the window for the launcher to read if desired
        setattr(window, "selected_startup_directory", selected_dir)
        setattr(window, "selected_interface", selected_interface)
        
        # Build the launch command chain
        interface_cmd = "jupyter-notebook" if selected_interface == "notebook" else "jupyter-lab"
        # Use a login shell to ensure the 'module' command is available
        chained_cmd = f"cd {shlex.quote(selected_dir)}; module load {shlex.quote(selected_python_module)}; {interface_cmd}"

        try:
            proc = subprocess.Popen(
                ["bash", "-lc", chained_cmd],
                start_new_session=True,
            )
            # Register started session with the launcher if possible
            try:
                if parent is not None:
                    try:
                        pgid = os.getpgid(proc.pid)
                    except Exception:
                        pgid = None
                    label_full = f"Jupyter {label}: {leaf}"
                    register_fn = getattr(parent, "register_started_session", None)
                    if callable(register_fn):
                        register_fn(proc.pid, label_full, pgid)
            except Exception:
                pass
            # Record history if enabled
            try:
                if not dont_record_checkbox.isChecked() and parent is not None:
                    # Provide a shell script for replay to keep the launcher generic
                    script_lines = [
                        "#!/usr/bin/env bash",
                        "set -e",
                        f"cd {shlex.quote(selected_dir)}",
                        f"module load {shlex.quote(selected_python_module)}",
                        "exec jupyter-notebook" if selected_interface == "notebook" else "exec jupyter-lab",
                    ]
                    replay_shell_script = "\n".join(script_lines) + "\n"
                    history_entry = {
                        "title": f"Jupyter {label}: {leaf}",
                        "icon": "../Apps/Jupyter/Resources/Jupyter.png",
                        "options": {
                            "startup_dir": selected_dir,
                            "interface": label,
                            "python_module": selected_python_module,
                        },
                        "replay_shell_script": replay_shell_script,
                    }
                    record_fn = getattr(parent, "record_history", None)
                    if callable(record_fn):
                        record_fn(history_entry)
            except Exception:
                pass
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
    root_layout.addWidget(advanced_toggle)
    root_layout.addWidget(advanced_content)
    root_layout.addStretch(1)
    root_layout.addLayout(buttons_layout)

    window.setCentralWidget(central)
    window.resize(700, 200)
    # Center the window on top of the launcher window
    try:
        if parent is not None:
            parent_geom = parent.geometry()
            parent_top_left = parent.mapToGlobal(parent_geom.topLeft())
            target_x = parent_top_left.x() + (parent_geom.width() - window.width()) // 2
            target_y = parent_top_left.y() + (parent_geom.height() - window.height()) // 2
            window.move(max(0, target_x), max(0, target_y))
    except Exception:
        pass
    return window


