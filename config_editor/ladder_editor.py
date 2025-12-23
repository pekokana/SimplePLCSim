# ladder_editor.py
import yaml
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit,
    QPushButton, QMessageBox
)


class LadderEditor(QWidget):
    def __init__(self):
        super().__init__()

        self.text = QTextEdit()
        self.text.setPlainText(
            "kind: ladder\n"
            "version: 1.0\n\n"
            "rungs:\n"
            "  - \"[X0] --(Y0)\"\n"
            "  - \"END\"\n"
        )

        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self.validate)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addWidget(validate_btn)

    def validate(self):
        try:
            data = yaml.safe_load(self.text.toPlainText())
            assert data["kind"] == "ladder"
            assert isinstance(data["rungs"], list)
            QMessageBox.information(self, "OK", "Ladder YAML valid")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
