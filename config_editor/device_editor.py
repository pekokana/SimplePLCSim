# device_editor.py
import yaml
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QSpinBox, QPushButton, QScrollArea, QMessageBox,
    QHBoxLayout
)

from signal_editor import SignalEditor


class DeviceEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # -----------------------------
        # Device base fields
        # -----------------------------
        self.name_edit = QLineEdit()
        self.cycle_spin = QSpinBox()
        self.cycle_spin.setRange(10, 10000)
        self.cycle_spin.setValue(100)

        form = QFormLayout()
        form.addRow("Device Name", self.name_edit)
        form.addRow("Cycle (ms)", self.cycle_spin)

        # -----------------------------
        # Signals Area
        # -----------------------------
        self.signal_area = QVBoxLayout()
        self.signal_area.addStretch()

        container = QWidget()
        container.setLayout(self.signal_area)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        add_signal_btn = QPushButton("+ Add Signal")
        add_signal_btn.clicked.connect(self.add_signal)

        # -----------------------------
        # Bottom Buttons
        # -----------------------------
        save_btn = QPushButton("Save YAML")
        save_btn.clicked.connect(self.save_yaml)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(add_signal_btn)
        btns.addWidget(save_btn)

        # -----------------------------
        # Main layout
        # -----------------------------
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(scroll)
        layout.addLayout(btns)

    # -----------------------------
    # Signal management
    # -----------------------------
    def add_signal(self, name="", data=None):
        name = "new_signal"
        data = {
            "type": "coil",
            "address": 0,
            "pattern": [
                {"value": True, "duration_ms": 1000},
                {"value": False, "duration_ms": 1000},
            ],
        }

        editor = SignalEditor(name, data, parent=self)
        if editor.exec():
            new_name, new_data = editor.get_result()
            self.signals[new_name] = new_data
            self.refresh_list()

    def remove_signal(self, editor):
        editor.setParent(None)
        editor.deleteLater()

    # -----------------------------
    # YAML
    # -----------------------------
    def to_yaml(self):
        signals = {}
        for i in range(self.signal_area.count()):
            w = self.signal_area.itemAt(i).widget()
            if isinstance(w, SignalEditor):
                name = w.name_edit.text().strip()
                if not name:
                    continue
                signals[name] = w.to_dict()

        return {
            "kind": "DeviceConfig",
            "version": "v1",
            "device": {
                "name": self.name_edit.text(),
                "cycle_ms": self.cycle_spin.value(),
                "signals": signals
            }
        }

    def save_yaml(self):
        data = self.to_yaml()
        text = yaml.dump(data, allow_unicode=True, sort_keys=False)

        QMessageBox.information(
            self,
            "Generated YAML",
            text
        )
