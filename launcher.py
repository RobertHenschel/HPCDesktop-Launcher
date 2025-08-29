#! /usr/bin/env python3

import argparse
import json
import os
import sys
import importlib.util
import html as html_lib
import shlex
from types import ModuleType
from typing import Dict, List, Optional, Any

from PyQt5.QtCore import Qt, QUrl, QSize, QObject, QEvent
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QWidget,
    QStyle,
    QToolBar,
    QAction,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView


def resolve_base_path(cli_base_path: Optional[str]) -> str:
    """Return the base path per spec.

    - If a CLI base path is provided, use it.
    - Otherwise, use the directory of this script appended with "/Objects/".
    """
    if cli_base_path:
        abs_cli = os.path.abspath(cli_base_path)
        # If a JSON file is provided, use its directory as base for browsing
        if abs_cli.lower().endswith(".json") and os.path.isfile(abs_cli):
            return os.path.dirname(abs_cli)
        return abs_cli
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "Objects")


def find_object_files(base_path: str) -> List[str]:
    """Return a list of absolute paths to all *.json object files in base_path."""
    if not os.path.isdir(base_path):
        return []
    object_files: List[str] = []
    try:
        for entry in os.listdir(base_path):
            if entry.lower().endswith(".json"):
                object_files.append(os.path.join(base_path, entry))
    except Exception:
        # Fail silent; return what we have
        pass
    return sorted(object_files)


def load_object_descriptor(json_path: str) -> Optional[Dict[str, str]]:
    """Load a single object JSON and return its dictionary or None on failure."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data  # type: ignore[return-value]
    except Exception:
        return None
    return None


def resolve_icon_path(base_path: str, icon_value: Optional[str]) -> Optional[str]:
    """Resolve icon path from the descriptor.

    Supports absolute paths and relative paths resolved against base_path.
    Returns absolute path if it exists, otherwise None.
    """
    if not icon_value:
        return None

    # Normalize potential leading ./ or similar
    potential_path = icon_value

    # Treat as absolute if it is
    if os.path.isabs(potential_path):
        return potential_path if os.path.isfile(potential_path) else None

    # Otherwise, resolve relative to base_path
    abs_candidate = os.path.abspath(os.path.join(base_path, potential_path))
    if os.path.isfile(abs_candidate):
        return abs_candidate

    # Try also relative to the directory of the JSON file might be same as base_path
    # but if nested paths are ever used this provides a small extra chance.
    return None


class LauncherWindow(QMainWindow):
    def __init__(self, base_path: str) -> None:
        super().__init__()
        self.base_path = os.path.abspath(base_path)
        self.root_base_path = self.base_path
        self.child_windows: List[Any] = []

        self.setWindowTitle("HPC Desktop Launcher")
        self.resize(1200, 800)

        # Breadcrumb toolbar (top)
        self.breadcrumbs = QToolBar("Navigation")
        self.addToolBar(self.breadcrumbs)

        # Splitter for resizable layout: left 2/3, right 1/3
        self.splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(self.splitter)

        # Left: icon grid
        self.icon_list = QListWidget()
        self.icon_list.setViewMode(QListWidget.IconMode)
        self.icon_list.setIconSize(QSize(96, 96))
        self.icon_list.setResizeMode(QListWidget.Adjust)
        self.icon_list.setMovement(QListWidget.Static)
        self.icon_list.setUniformItemSizes(False)
        self.icon_list.setWordWrap(True)
        self.icon_list.setSpacing(12)

        # Right: web view for index.html
        self.web_view = QWebEngineView()

        self.splitter.addWidget(self.icon_list)
        self.splitter.addWidget(self.web_view)

        # Set stretch so that left is 2/3, right is 1/3
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)

        self.populate_objects()
        self.load_index_html()
        self.update_breadcrumbs()

        # Hook selection changes and click behavior
        self.icon_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.icon_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.icon_list.viewport().installEventFilter(self)

    def populate_objects(self) -> None:
        object_files = find_object_files(self.base_path)
        for json_path in object_files:
            descriptor = load_object_descriptor(json_path)
            if not descriptor:
                continue

            title = str(descriptor.get("title") or os.path.splitext(os.path.basename(json_path))[0])
            icon_path = resolve_icon_path(self.base_path, descriptor.get("icon"))

            # Build item with icon and text
            item = QListWidgetItem()
            item.setText(title)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)

            if icon_path and os.path.isfile(icon_path):
                item.setIcon(QIcon(icon_path))
            else:
                # Graceful fallback icon if missing
                item.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))

            # Store descriptor and json path on the item for later use
            item.setData(Qt.UserRole, descriptor)
            item.setData(Qt.UserRole + 1, json_path)
            self.icon_list.addItem(item)

    def load_index_html(self) -> None:
        index_html_path = os.path.join(self.base_path, "index.html")
        if os.path.isfile(index_html_path):
            url = QUrl.fromLocalFile(os.path.abspath(index_html_path))
            self.web_view.load(url)
        else:
            # Minimal inline content if file is absent
            self.web_view.setHtml(
                """
                <!DOCTYPE html>
                <html>
                  <head><meta charset=\"utf-8\"><title>No index.html</title></head>
                  <body>
                    <h2>No index.html found</h2>
                    <p>Expected at: {}</p>
                  </body>
                </html>
                """.format(index_html_path)
            )

    def load_details_for_descriptor(self, descriptor: Dict[str, str]) -> None:
        details_value = descriptor.get("details")
        if not details_value:
            # No details -> load index.html
            self.load_index_html()
            return
        # Resolve details path relative to base_path unless absolute
        details_path = details_value
        if not os.path.isabs(details_path):
            details_path = os.path.abspath(os.path.join(self.base_path, details_path))

        if os.path.isfile(details_path):
            self.web_view.load(QUrl.fromLocalFile(details_path))
        else:
            # Fallback to index.html if details file not found
            self.load_index_html()

    def _on_selection_changed(self) -> None:
        selected_items = self.icon_list.selectedItems()
        if not selected_items:
            # No selection -> show index.html
            self.load_index_html()
            return
        item = selected_items[0]
        descriptor = item.data(Qt.UserRole) or {}
        if isinstance(descriptor, dict):
            self.load_details_for_descriptor(descriptor)
        else:
            self.load_index_html()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        descriptor = item.data(Qt.UserRole) or {}
        if not isinstance(descriptor, dict):
            return
        json_path = item.data(Qt.UserRole + 1) or ""
        if isinstance(json_path, str):
            self.execute_openaction(descriptor, json_path)
        return

    def execute_openaction(self, descriptor: Dict[str, str], json_path: str) -> None:
        open_action = descriptor.get("openaction")
        if not isinstance(open_action, dict):
            return
        command = open_action.get("command")
        arg0 = open_action.get("arg0")
        if not isinstance(arg0, str) or not arg0:
            return

        if command == "path":
            # Resolve new base path
            new_base = arg0 if os.path.isabs(arg0) else os.path.abspath(os.path.join(self.base_path, arg0))
            if os.path.isdir(new_base):
                self.change_base_path(new_base)
            return

        if command == "python":
            # Resolve plugin file path
            plugin_path = arg0 if os.path.isabs(arg0) else os.path.abspath(os.path.join(self.base_path, arg0))
            if os.path.isfile(plugin_path):
                context = {
                    "base_path": self.base_path,
                    "root_base_path": self.root_base_path,
                    "descriptor": descriptor,
                    "json_path": json_path,
                }
                self.run_python_plugin(plugin_path, context)
            return

        if command == "shell":
            # Resolve and execute a shell script (login shell to access 'module')
            script_path = arg0 if os.path.isabs(arg0) else os.path.abspath(os.path.join(self.base_path, arg0))
            if os.path.isfile(script_path):
                try:
                    import subprocess as _subprocess
                    _subprocess.Popen(["bash", "-lc", shlex.quote(script_path)], start_new_session=True)
                except Exception:
                    pass
            return

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Detect clicks on empty area to clear selection
        if watched is self.icon_list.viewport():
            if event.type() == QEvent.MouseButtonPress:
                pos = event.pos()
                item_at_pos: Optional[QListWidgetItem] = self.icon_list.itemAt(pos)
                if item_at_pos is None:
                    # Click into empty area -> clear selection
                    self.icon_list.clearSelection()
                    # Ensure right view shows index.html
                    self.load_index_html()
        return super().eventFilter(watched, event)

    def change_base_path(self, new_base_path: str) -> None:
        self.base_path = os.path.abspath(new_base_path)
        # Repopulate objects and refresh right panel
        self.icon_list.clear()
        self.populate_objects()
        self.load_index_html()
        self.update_breadcrumbs()

    def update_breadcrumbs(self) -> None:
        # Clear existing actions
        self.breadcrumbs.clear()

        def add_action(label: str, target_path: str) -> None:
            # Insert a small arrow before every crumb after the first
            if self.breadcrumbs.actions():
                arrow = QAction("->", self)
                arrow.setEnabled(False)
                arrow.setSeparator(False)
                self.breadcrumbs.addAction(arrow)

            action = QAction(label, self)
            action.triggered.connect(lambda _=False, p=target_path: self.change_base_path(p))
            self.breadcrumbs.addAction(action)

        # Always provide Home (root)
        add_action("Home", self.root_base_path)

        # If current equals root, we're done
        if os.path.abspath(self.base_path) == os.path.abspath(self.root_base_path):
            return

        try:
            rel = os.path.relpath(self.base_path, self.root_base_path)
            if rel == ".":
                return
            parts = [p for p in rel.split(os.sep) if p]
            accum = self.root_base_path
            for part in parts:
                accum = os.path.join(accum, part)
                add_action(part, accum)
        except Exception:
            # Fallback: show current base as a single crumb
            add_action(self.base_path, self.base_path)

    def record_history(self, entry: Dict[str, str]) -> None:
        """Create a history JSON file under <root_base_path>/History/.

        Expected keys in entry: "title" and "icon".
        Optional: "options" (dict) to be documented in a sibling .html file.
        Silently no-op on error.
        """
        try:
            title = entry.get("title") if isinstance(entry, dict) else None
            icon = entry.get("icon") if isinstance(entry, dict) else None
            options = entry.get("options") if isinstance(entry, dict) else None
            if not isinstance(title, str) or not isinstance(icon, str):
                return

            history_dir = os.path.join(self.root_base_path, "History")
            try:
                os.makedirs(history_dir, exist_ok=True)
            except Exception:
                return

            # Build a filename based on timestamp; ensure uniqueness
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            base_name = f"{timestamp}.json"
            target_path = os.path.join(history_dir, base_name)
            counter = 1
            while os.path.exists(target_path):
                base_name = f"{timestamp}-{counter}.json"
                target_path = os.path.join(history_dir, base_name)
                counter += 1

            # Pre-compute sibling HTML path for details reference
            html_path = os.path.splitext(target_path)[0] + ".html"
            # Prepare sibling shell script path for replay
            sh_path = os.path.splitext(target_path)[0] + ".sh"

            # Write shell script only if provided by the entry
            wrote_shell = False
            try:
                replay_script = entry.get("replay_shell_script") if isinstance(entry, dict) else None
                if isinstance(replay_script, str) and replay_script.strip():
                    with open(sh_path, "w", encoding="utf-8") as sf:
                        sf.write(replay_script if replay_script.endswith("\n") else replay_script + "\n")
                    try:
                        os.chmod(sh_path, 0o755)
                    except Exception:
                        pass
                    wrote_shell = True
            except Exception:
                # Ignore failures to write script; JSON will still be created
                pass

            payload = {
                "title": title,
                "icon": icon,
                "details": os.path.basename(html_path),
            }
            if wrote_shell and os.path.isfile(sh_path):
                payload["openaction"] = {
                    "command": "shell",
                    "arg0": os.path.basename(sh_path),
                }
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            # Also write an .html file with the same stem documenting options
            try:
                parts = [
                    "<!DOCTYPE html>",
                    "<html>",
                    "  <head>",
                    "    <meta charset=\"utf-8\">",
                    f"    <title>{html_lib.escape(title)}</title>",
                    "  </head>",
                    "  <body>",
                    f"    <h2>{html_lib.escape(title)}</h2>",
                ]
                if isinstance(options, dict) and options:
                    parts.append("    <h3>Launch Options</h3>")
                    parts.append("    <ul>")
                    for key, value in options.items():
                        parts.append(
                            f"      <li><strong>{html_lib.escape(str(key))}:</strong> {html_lib.escape(str(value))}</li>"
                        )
                    parts.append("    </ul>")
                parts.append("  </body>")
                parts.append("</html>")
                with open(html_path, "w", encoding="utf-8") as hf:
                    hf.write("\n".join(parts))
            except Exception:
                pass
        except Exception:
            # Fail silently
            return

    def run_python_plugin(self, plugin_file: str, context: Dict[str, Any]) -> None:
        # Dynamically import plugin module from a file path
        try:
            module_name = f"plugin_{abs(hash(plugin_file))}"
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception:
            return

        # Expect a factory function create_window(parent, context)
        create_fn = getattr(module, "create_window", None)
        if not callable(create_fn):
            return

        try:
            window = create_fn(self, context)
            if window is None:
                return
            # Keep reference to prevent GC
            self.child_windows.append(window)
            window.show()
        except Exception:
            return


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HPC Desktop Launcher (PyQt5)")
    parser.add_argument(
        "base_path",
        nargs="?",
        default=None,
        help="Base path containing object JSON files and index.html. If omitted, uses <script_dir>/Objects/",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    base_path = resolve_base_path(args.base_path)
    json_to_execute: Optional[str] = None
    if args.base_path:
        candidate = os.path.abspath(args.base_path)
        if candidate.lower().endswith(".json") and os.path.isfile(candidate):
            json_to_execute = candidate

    app = QApplication(sys.argv)
    window = LauncherWindow(base_path)
    window.show()
    # If a JSON file was provided on CLI, execute its openaction right away
    if json_to_execute:
        descriptor = load_object_descriptor(json_to_execute)
        if isinstance(descriptor, dict):
            try:
                window.execute_openaction(descriptor, json_to_execute)
            except Exception:
                pass
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())


