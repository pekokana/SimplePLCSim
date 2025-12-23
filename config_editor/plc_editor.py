# plc_editor.py
import yaml
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QSpinBox,
    QPushButton, QVBoxLayout, QFileDialog, QMessageBox
)


class PLCEditor(QWidget):
    def __init__(self):
        super().__init__()

        self._build_ui()
        self._set_default()

    def _build_ui(self):
        self.layout = QVBoxLayout(self)

        form = QFormLayout()

        # 基本
        self.name = QLineEdit()
        self.version = QLineEdit("1.0")

        # CPU
        self.scan_cycle = QSpinBox()
        self.scan_cycle.setRange(1, 10000)

        # Memory
        self.mem_x = QSpinBox()
        self.mem_y = QSpinBox()
        self.mem_m = QSpinBox()
        self.mem_d = QSpinBox()

        for w in (self.mem_x, self.mem_y, self.mem_m, self.mem_d):
            w.setRange(1, 1024)

        # Modbus
        self.port = QSpinBox()
        self.port.setRange(1, 65535)

        form.addRow("PLC Name", self.name)
        form.addRow("Version", self.version)
        form.addRow("Scan cycle (ms)", self.scan_cycle)
        form.addRow("Memory X", self.mem_x)
        form.addRow("Memory Y", self.mem_y)
        form.addRow("Memory M", self.mem_m)
        form.addRow("Memory D", self.mem_d)
        form.addRow("Modbus Port", self.port)

        self.layout.addLayout(form)

        self.save_btn = QPushButton("Save YAML")
        self.save_btn.clicked.connect(self.save_yaml)
        self.layout.addWidget(self.save_btn)

    def _set_default(self):
        self.name.setText("PLC_A")
        self.scan_cycle.setValue(100)
        self.mem_x.setValue(4)
        self.mem_y.setValue(4)
        self.mem_m.setValue(16)
        self.mem_d.setValue(16)
        self.port.setValue(15020)

    def build_yaml(self):
        return {
            "kind": "plc",
            "version": self.version.text(),
            "name": self.name.text(),
            "power": True,
            "cpu": {
                "scan_cycle_ms": self.scan_cycle.value()
            },
            "memory": {
                "X": self.mem_x.value(),
                "Y": self.mem_y.value(),
                "M": self.mem_m.value(),
                "D": self.mem_d.value()
            },
            "modbus": {
                "port": self.port.value()
            }
        }

    def load_yaml(self, data):
        self.name.setText(data.get("name", ""))
        self.version.setText(data.get("version", "1.0"))
        self.scan_cycle.setValue(data["cpu"]["scan_cycle_ms"])
        self.mem_x.setValue(data["memory"]["X"])
        self.mem_y.setValue(data["memory"]["Y"])
        self.mem_m.setValue(data["memory"]["M"])
        self.mem_d.setValue(data["memory"]["D"])
        self.port.setValue(data["modbus"]["port"])


    def save_yaml(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PLC YAML",
            "",
            "YAML Files (*.yaml *.yml)"
        )
        if not path:
            return

        data = self.build_yaml()

        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            QMessageBox.information(self, "Saved", f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
