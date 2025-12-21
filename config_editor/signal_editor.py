# signal_editor.py
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QPushButton, QVBoxLayout, QHBoxLayout
)


class SignalEditor(QWidget):
    def __init__(self, name="", data=None, parent=None):
        super().__init__(parent)

        if not isinstance(name, str):
            raise TypeError(f"Signal name must be str, got {type(name)}")

        self.name_edit = QLineEdit()
        self.name_edit.setText(name)


        self.type_combo = QComboBox()
        self.type_combo.addItems(["coil", "register", "pulse"])

        self.addr_spin = QSpinBox()
        self.addr_spin.setRange(0, 65535)

        self.remove_btn = QPushButton("Remove")

        form = QFormLayout()
        form.addRow("Signal Name", self.name_edit)
        form.addRow("Type", self.type_combo)
        form.addRow("Address", self.addr_spin)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(self.remove_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(btns)

        if data:
            self.load(data)

    # -----------------------------
    # Load / Export
    # -----------------------------
    def load(self, data: dict):
        self.type_combo.setCurrentText(data.get("type", "coil"))
        self.addr_spin.setValue(data.get("address", 0))

    def to_dict(self):
        return {
            "type": self.type_combo.currentText(),
            "address": self.addr_spin.value()
        }
