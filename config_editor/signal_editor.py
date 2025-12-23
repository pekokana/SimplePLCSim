# signal_editor.py
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget
)


class SignalEditor(QWidget):
    def __init__(self, name="", data=None, parent=None):
        super().__init__(parent)

        self.name_edit = QLineEdit(name)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["coil", "register", "pulse"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(0, 65535)

        # ---- pulse only ----
        self.pulse_ms = QSpinBox()
        self.pulse_ms.setRange(1, 60000)
        self.interval_ms = QSpinBox()
        self.interval_ms.setRange(1, 60000)

        self.stack = QStackedWidget()
        self.stack.addWidget(QWidget())            # coil
        self.stack.addWidget(QWidget())            # register
        self.stack.addWidget(self._pulse_widget()) # pulse

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_self)

        form = QFormLayout()
        form.addRow("Signal Name", self.name_edit)
        form.addRow("Type", self.type_combo)
        form.addRow("Address", self.addr_spin)
        form.addRow("", self.stack)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.remove_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns)

        if data:
            self.load(data)

    def _pulse_widget(self):
        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Pulse (ms)", self.pulse_ms)
        f.addRow("Interval (ms)", self.interval_ms)
        return w

    def _on_type_changed(self, t):
        self.stack.setCurrentIndex(
            {"coil": 0, "register": 1, "pulse": 2}[t]
        )

    def _remove_self(self):
        self.setParent(None)
        self.deleteLater()

    def load(self, data):
        self.type_combo.setCurrentText(data.get("type", "coil"))
        self.addr_spin.setValue(data.get("address", 0))
        self.pulse_ms.setValue(data.get("pulse_ms", 100))
        self.interval_ms.setValue(data.get("interval_ms", 1000))

    def to_dict(self):
        t = self.type_combo.currentText()
        d = {
            "type": t,
            "address": self.addr_spin.value()
        }
        if t == "pulse":
            d["pulse_ms"] = self.pulse_ms.value()
            d["interval_ms"] = self.interval_ms.value()
        return d
