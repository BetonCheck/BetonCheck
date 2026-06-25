from __future__ import annotations

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox, QListWidget, QListWidgetItem, QCheckBox, QTextEdit, QDialog,
    QDialogButtonBox
)

from betoncheck_customer.eula import has_accepted_eula, accept_eula
from betoncheck_customer.license_checker import check_license, load_license_key
from betoncheck_customer.module_manager import available_items, ensure_downloaded, ModuleItem
from betoncheck_customer.excel_launcher import open_encrypted_excel
from betoncheck_customer.updater import check_for_update


class EulaDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Licencni pogoji")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        try:
            text.setPlainText(open("LICENSE.txt", "r", encoding="utf-8").read())
        except FileNotFoundError:
            text.setPlainText("LICENSE.txt manjka.")
        self.checkbox = QCheckBox("Prebral sem in se strinjam z licencnimi pogoji.")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(text)
        layout.addWidget(self.checkbox)
        layout.addWidget(buttons)

    def accept(self):
        if not self.checkbox.isChecked():
            QMessageBox.warning(self, "Pogoji", "Pred nadaljevanjem morate sprejeti licencne pogoje.")
            return
        accept_eula()
        super().accept()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BetonCheck Launcher")
        self.resize(720, 520)
        self.license_result = None
        self.items: list[ModuleItem] = []

        self.info = QLabel("Vnesite licencni kljuc in kliknite Aktiviraj.")
        self.license_input = QLineEdit(load_license_key() or "")
        self.license_input.setPlaceholderText("Licencni kljuc")
        self.activate_btn = QPushButton("Aktiviraj / preveri licenco")
        self.activate_btn.clicked.connect(self.activate)

        self.update_btn = QPushButton("Preveri posodobitve")
        self.update_btn.clicked.connect(self.check_updates)

        self.list_widget = QListWidget()
        self.open_btn = QPushButton("Odpri izbrani Excel")
        self.open_btn.clicked.connect(self.open_selected)
        self.open_btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("BetonCheck"))
        layout.addWidget(self.info)
        layout.addWidget(self.license_input)
        layout.addWidget(self.activate_btn)
        layout.addWidget(self.update_btn)
        layout.addWidget(QLabel("Dovoljeni moduli in Excel kontrole:"))
        layout.addWidget(self.list_widget)
        layout.addWidget(self.open_btn)

    def activate(self):
        result = check_license(self.license_input.text().strip())
        self.license_result = result
        if not result.valid:
            QMessageBox.critical(self, "Licenca", result.message)
            self.info.setText(result.message)
            return
        self.info.setText(f"Licenca: {result.customer} | velja do {result.valid_until}")
        self.load_items(result.modules or [])

    def load_items(self, modules: list[str]):
        self.list_widget.clear()
        self.items = available_items(modules)
        for item in self.items:
            row = QListWidgetItem(f"{item.module_title} / {item.title}")
            self.list_widget.addItem(row)
        self.open_btn.setEnabled(bool(self.items))

    def open_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Izbor", "Izberite Excel kontrolo.")
            return
        item = self.items[row]
        try:
            encrypted_path = ensure_downloaded(item)
            open_encrypted_excel(encrypted_path)
        except Exception as exc:
            QMessageBox.critical(self, "Napaka", f"Modula ni bilo mogoce odpreti:\n{exc}")

    def check_updates(self):
        has_update, message = check_for_update()
        QMessageBox.information(self, "Posodobitve", message)


def main():
    app = QApplication(sys.argv)
    if not has_accepted_eula():
        dialog = EulaDialog()
        if dialog.exec() != QDialog.Accepted:
            sys.exit(0)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
