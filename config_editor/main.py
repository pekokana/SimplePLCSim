# main.py
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QFileDialog,
    QMessageBox,
)

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from plc_editor import PLCEditor
from device_editor import DeviceEditor
from ladder_editor import LadderEditor



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PLC / Device YAML Editor")
        self.resize(1200, 800)

        self.mdi = QMdiArea()
        self.setCentralWidget(self.mdi)

        self._build_menu()

    # -----------------------------
    # Menu
    # -----------------------------
    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        open_act = QAction("Open YAML", self)
        open_act.triggered.connect(self.open_yaml)

        new_plc = QAction("New PLC YAML", self)
        new_plc.triggered.connect(self.open_plc_editor)
        new_device = QAction("New Device YAML", self)
        new_device.triggered.connect(self.open_device_editor)
        exit_act = QAction("Exit", self)

        new_ladder = QAction("New Ladder YAML", self)
        new_ladder.triggered.connect(self.open_ladder_editor)

        file_menu.addAction(open_act)
        file_menu.addSeparator()
        file_menu.addAction(new_plc)
        file_menu.addAction(new_device)
        file_menu.addAction(new_ladder)
        file_menu.addSeparator()
        file_menu.addAction(exit_act)

    # -----------------------------
    # Open Editors
    # -----------------------------
    def open_plc_editor(self):
        editor = PLCEditor()
        self._open_subwindow(editor, "PLC Editor")

    def open_device_editor(self):
        editor = DeviceEditor()
        self._open_subwindow(editor, "Device Editor")

    def open_ladder_editor(self):
        self._open_subwindow(LadderEditor(), "Ladder Editor")

    def _open_subwindow(self, widget, title):
        sub = QMdiSubWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(title)
        sub.setAttribute(Qt.WA_DeleteOnClose)

        self.mdi.addSubWindow(sub)
        sub.show()

    def open_yaml(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open YAML", "", "YAML (*.yaml *.yml)"
        )
        if not path:
            return

        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        kind = data.get("kind")

        if kind == "plc":
            editor = PLCEditor()
            editor.load_yaml(data)
            self._open_subwindow(editor, f"PLC Editor - {path}")
        elif kind == "device":
            editor = DeviceEditor()
            editor.load_yaml(data)
            self._open_subwindow(editor, f"Device Editor - {path}")
        else:
            QMessageBox.warning(self, "Unknown", f"Unknown kind: {kind}")


    # -----------------------------
    # Help
    # -----------------------------
    def show_about(self):
        QMessageBox.information(
            self,
            "About",
            "PLC / Device Simulator YAML Editor\n"
            "MDI GUI Tool\n\n"
            "Designed for PLC Simulator + SCADA"
        )


# -----------------------------
# Entry
# -----------------------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
