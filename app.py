from __future__ import annotations

import sys
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QTextEdit,
    QDialog,
    QDialogButtonBox,
)

from betoncheck_customer.eula import has_accepted_eula, accept_eula
from betoncheck_customer.license_checker import check_license, load_license_key
from betoncheck_customer.module_manager import (
    available_items,
    ensure_downloaded,
    ModuleItem,
)
from betoncheck_customer.excel_launcher import open_encrypted_excel
from betoncheck_customer.updater import check_for_update


class EulaDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Licenčni pogoji")
        self.resize(700, 500)

        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)

        try:
            with open("LICENSE.txt", "r", encoding="utf-8") as file:
                text.setPlainText(file.read())
        except FileNotFoundError:
            text.setPlainText("LICENSE.txt manjka.")

        self.checkbox = QCheckBox(
            "Prebral sem in se strinjam z licenčnimi pogoji."
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(text)
        layout.addWidget(self.checkbox)
        layout.addWidget(buttons)

    def accept(self):
        if not self.checkbox.isChecked():
            QMessageBox.warning(
                self,
                "Pogoji",
                "Pred nadaljevanjem morate sprejeti licenčne pogoje.",
            )
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
        self.module_keys: dict[str, str] = {}

        self.info = QLabel("Vnesite licenčni ključ in kliknite Aktiviraj.")

        self.license_input = QLineEdit(load_license_key() or "")
        self.license_input.setPlaceholderText("Licenčni ključ")

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
        try:
            result = check_license(self.license_input.text().strip())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licence ni bilo mogoče preveriti:\n{exc}",
            )
            self.info.setText(f"Licence ni bilo mogoče preveriti: {exc}")
            return

        self.license_result = result

        if not result.valid:
            QMessageBox.critical(self, "Licenca", result.message)
            self.info.setText(result.message)
            self.open_btn.setEnabled(False)
            return

        self.module_keys = self.extract_module_keys(result.modules or {})

        self.info.setText(
            f"Licenca: {result.customer} | velja do {result.valid_until}"
        )

        self.load_items(list(self.module_keys.keys()))

    def extract_module_keys(self, modules: dict[str, dict[str, Any]]) -> dict[str, str]:
        module_keys: dict[str, str] = {}

        for module_id, module_data in modules.items():
            module_key = module_data.get("key")

            if isinstance(module_key, str) and module_key.strip():
                module_keys[module_id] = module_key.strip()

        return module_keys

    def load_items(self, modules: list[str]):
        self.list_widget.clear()
        self.items = available_items(modules)

        for item in self.items:
            row = QListWidgetItem(f"{item.module_title} / {item.title}")
            self.list_widget.addItem(row)

        self.open_btn.setEnabled(bool(self.items))

        if not self.items:
            self.info.setText(
                "Licenca je veljavna, vendar nima dodeljenih modulov "
                "ali pa moduli nimajo veljavnih ključev."
            )

    def open_selected(self):
        row = self.list_widget.currentRow()

        if row < 0:
            QMessageBox.warning(self, "Izbor", "Izberite Excel kontrolo.")
            return

        item = self.items[row]

        module_key = self.module_keys.get(item.module_id)

        if not module_key:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licenca ne vsebuje ključa za modul: {item.module_id}",
            )
            return

        try:
            self.info.setText(f"Prenašam modul: {item.title} ...")
            QApplication.processEvents()

            encrypted_path = ensure_downloaded(item)

            self.info.setText(f"Odpiram modul: {item.title} ...")
            QApplication.processEvents()

            open_encrypted_excel(encrypted_path, module_key)

            self.info.setText(f"Odprt modul: {item.title}")

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Napaka",
                f"Modula ni bilo mogoče odpreti:\n{exc}",
            )
            self.info.setText(f"Napaka pri odpiranju modula: {exc}")

    def check_updates(self):
        try:
            _has_update, message = check_for_update()
            QMessageBox.information(self, "Posodobitve", message)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Posodobitve",
                f"Posodobitev ni bilo mogoče preveriti:\n{exc}",
            )


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