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

        self.name_edit = QLineEdit("Device_A")
        self.cycle_spin = QSpinBox()
        self.cycle_spin.setRange(10, 10000)
        self.cycle_spin.setValue(100)

        form = QFormLayout()
        form.addRow("Device Name", self.name_edit)
        form.addRow("Cycle (ms)", self.cycle_spin)

        # Signals area
        self.signal_layout = QVBoxLayout()
        self.signal_layout.addStretch()

        container = QWidget()
        container.setLayout(self.signal_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        add_signal_btn = QPushButton("+ Add Signal")
        add_signal_btn.clicked.connect(self.add_signal)

        save_btn = QPushButton("Save YAML")
        save_btn.clicked.connect(self.save_yaml)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(add_signal_btn)
        btns.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(scroll)
        layout.addLayout(btns)

    def add_signal(self):
        editor = SignalEditor(
            name="new_signal",
            data={"type": "coil", "address": 0},
            parent=self
        )
        self.signal_layout.insertWidget(
            self.signal_layout.count() - 1,
            editor
        )

    def to_yaml(self):
        signals = {}

        for i in range(self.signal_layout.count()):
            w = self.signal_layout.itemAt(i).widget()
            if isinstance(w, SignalEditor):
                name = w.name_edit.text().strip()
                if name:
                    signals[name] = w.to_dict()

        return {
            "kind": "device",
            "version": "1.0",
            "device": {
                "name": self.name_edit.text(),
                "cycle_ms": self.cycle_spin.value(),
                "signals": signals
            }
        }

    def load_yaml(self, data):
        dev = data["device"]
        self.name_edit.setText(dev["name"])
        self.cycle_spin.setValue(dev["cycle_ms"])

        for sig_name, sig in dev.get("signals", {}).items():
            editor = SignalEditor(sig_name, sig, parent=self)
            self.signal_layout.insertWidget(
                self.signal_layout.count() - 1,
                editor
            )


    def save_yaml(self):
        data = self.to_yaml()
        text = yaml.dump(data, allow_unicode=True, sort_keys=False)

        QMessageBox.information(self, "Generated YAML", text)
