from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QTextEdit,
    QDialog,
    QDialogButtonBox,
    QStyle,
    QFrame,
    QSplitter,
    QMenu,
)

from betoncheck_customer.eula import has_accepted_eula, accept_eula
from betoncheck_customer.license_checker import check_license, load_license_key, LicenseResult
from betoncheck_customer.module_manager import (
    available_items,
    ensure_downloaded,
    ModuleItem,
)
from betoncheck_customer.key_decryption import decrypt_module_key
from betoncheck_customer.settings import APP_NAME, APP_VERSION, LAUNCHER_PRIVATE_KEY_PATH
from betoncheck_customer.updater import check_for_update
from betoncheck_customer.project_manager import (
    Project,
    Calculation,
    create_project,
    open_project,
    list_calculations,
    create_calculation_from_template,
    generate_calculation_name,
    reset_calculation,
    rename_calculation,
    delete_calculation,
)
from betoncheck_customer.excel_session import (
    open_calculation_session,
    open_file as open_external_file,
)


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


class InfoDialog(QDialog):
    def __init__(self, parent: QWidget, license_result: Any | None = None):
        super().__init__(parent)
        self.setWindowTitle("O BetonCheck")
        self.resize(520, 320)

        layout = QVBoxLayout(self)

        name_label = QLabel(f"{APP_NAME} {APP_VERSION}")
        name_label.setFont(QFont("Segoe UI", 11, QFont.Bold))

        license_info = "Licenca ni aktivirana"
        if license_result is not None and getattr(license_result, "valid", False):
            license_info = (
                f"Licenca: {license_result.customer}\n"
                f"Velja do: {license_result.valid_until}"
            )
        elif license_result is not None:
            license_info = getattr(license_result, "message", "Licenca ni aktivirana")

        info_text = QLabel(
            "Credits: BetonCheck team\n"
            "Program za upravljanje in pregledanja konstrukcijskih kontrol.\n\n"
            "" + license_info + ""
        )
        info_text.setWordWrap(True)

        self.update_button = QPushButton("Preveri posodobitve")
        self.update_button.clicked.connect(self.on_check_updates)

        close_button = QPushButton("Zapri")
        close_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.update_button)
        button_layout.addWidget(close_button)

        layout.addWidget(name_label)
        layout.addWidget(info_text)
        layout.addStretch(1)
        layout.addLayout(button_layout)

    def on_check_updates(self) -> None:
        try:
            _has_update, message = check_for_update()
            QMessageBox.information(self, "Posodobitve", message)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Posodobitve",
                f"Posodobitev ni bilo mogoče preveriti:\n{exc}",
            )


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BetonCheck Engineering Center")
        self.resize(980, 680)

        self.license_result = None
        self.items: list[ModuleItem] = []
        self.module_keys: dict[str, str] = {}

        self.current_project: Project | None = None
        self.calculations: list[Calculation] = []

        self.folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        self.license_input = QLineEdit(load_license_key() or "")
        self.license_input.setPlaceholderText("Licenčni ključ")
        self.license_input.setMinimumWidth(320)

        self.license_status_label = QLabel("Licenca ni aktivirana")
        self.license_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.license_status_label.setStyleSheet(
            "font-weight: bold; color: #d9534f;"
        )

        self.license_validity_label = QLabel("")
        self.license_validity_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.license_validity_label.setStyleSheet(
            "color: #444444;"
        )

        self.customer_label = QLabel("")
        self.customer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.customer_label.setStyleSheet(
            "font-weight: normal; color: #111111;"
        )

        self.activate_btn = QPushButton("Aktiviraj")
        self.activate_btn.clicked.connect(self.activate)

        self.info_btn = QPushButton("Info")
        self.info_btn.clicked.connect(self.show_info_dialog)

        self.new_project_btn = QPushButton("Nov projekt")
        self.new_project_btn.clicked.connect(self.new_project)

        self.open_project_btn = QPushButton("Odpri projekt")
        self.open_project_btn.clicked.connect(self.open_project_dialog)

        self.project_label = QLabel("Projekt: ni odprt")

        self.module_tree = QTreeWidget()
        self.setup_tree(self.module_tree)
        self.module_tree.itemClicked.connect(self.on_module_item_clicked)
        self.module_tree.itemDoubleClicked.connect(self.new_calculation_from_tree)

        self.project_tree = QTreeWidget()
        self.setup_tree(self.project_tree)
        self.project_tree.itemClicked.connect(self.on_project_tree_item_clicked)
        self.project_tree.itemDoubleClicked.connect(self.on_project_tree_double_clicked)
        self.project_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(
            self.on_project_tree_context_menu
        )

        self.details_panel = QGroupBox("Podrobnosti")
        self.details_layout = QVBoxLayout(self.details_panel)
        self.details_title = QLabel("Izberi modul ali kontrolo")
        self.details_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.details_description = QLabel(
            "Izberite modul ali kontrolo, da si ogledate podrobnosti in ukrepe."
        )
        self.details_description.setWordWrap(True)
        self.details_description.setStyleSheet("color: #444444;")

        self.details_info_labels: list[QLabel] = []
        self.details_info_area = QVBoxLayout()

        self.details_layout.addWidget(self.details_title)
        self.details_layout.addWidget(self.details_description)
        self.details_layout.addLayout(self.details_info_area)
        self.details_layout.addStretch(1)

        self.context_panel = QGroupBox("Kontekst")
        self.context_layout = QVBoxLayout(self.context_panel)
        self.context_project_label = QLabel("Projekt: ni odprt")
        self.context_license_label = QLabel("Licenca: ni aktivirana")
        self.context_selected_label = QLabel("Izbrana postavka: ni")
        self.context_selected_label.setWordWrap(True)
        self.context_recent_label = QLabel("Nedavne kontrole: -")
        self.context_recent_label.setWordWrap(True)

        self.context_layout.addWidget(self.context_project_label)
        self.context_layout.addWidget(self.context_license_label)
        self.context_layout.addWidget(self.context_selected_label)
        self.context_layout.addStretch(1)
        self.context_layout.addWidget(self.context_recent_label)

        self.status_label = QLabel("Pripravljen")
        self.status_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.status_label.setStyleSheet("padding: 6px; background: #f8f8f8;")

        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.reset_status_bar)

        self.build_ui()

    def setup_tree(self, tree: QTreeWidget) -> None:
        tree.setColumnCount(1)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setUniformRowHeights(True)
        tree.setAnimated(True)
        tree.setIndentation(20)
        tree.setExpandsOnDoubleClick(False)

    def build_ui(self) -> None:
        root = QVBoxLayout(self)

        license_layout = QHBoxLayout()
        license_layout.setContentsMargins(0, 0, 0, 0)
        license_layout.setSpacing(10)
        license_layout.addWidget(QLabel("Licence:"))
        license_layout.addWidget(self.license_input)
        license_layout.addWidget(self.activate_btn)
        license_layout.addStretch(1)
        license_layout.addWidget(self.license_status_label)
        license_layout.addWidget(self.license_validity_label)
        license_layout.addStretch(1)
        license_layout.addWidget(self.customer_label)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(10)
        toolbar.addWidget(self.info_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.new_project_btn)
        toolbar.addWidget(self.open_project_btn)
        toolbar.addSpacing(20)
        toolbar.addWidget(self.project_label)

        main_splitter = QSplitter(Qt.Horizontal, self)

        modules_group = QGroupBox("Razpoložljivi moduli")
        modules_layout = QVBoxLayout(modules_group)
        modules_layout.addWidget(self.module_tree)

        project_group = QGroupBox("Projekt")
        project_layout = QVBoxLayout(project_group)
        project_layout.addWidget(self.project_label)
        project_layout.addWidget(self.project_tree)

        main_splitter.addWidget(modules_group)
        main_splitter.addWidget(project_group)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 7)

        root.addLayout(license_layout)
        root.addSpacing(4)
        root.addLayout(toolbar)
        root.addSpacing(6)
        root.addWidget(main_splitter)
        root.addWidget(self.status_label)

    def activate(self) -> None:
        try:
            result = check_license(self.license_input.text().strip())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licence ni bilo mogoče preveriti:\n{exc}",
            )
            self.set_status_message(f"Licence ni bilo mogoče preveriti: {exc}", error=True)
            return

        self.license_result = result

        if not result.valid:
            self.set_license_status(result)
            self.set_status_message(result.message, error=True)
            return

        try:
            self.module_keys = self.extract_module_keys(result.modules or {})
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Napaka pri dešifriranju modulskih ključev:\n{exc}",
            )
            self.set_status_message(
                "Napaka pri dešifriranju modulskih ključev.",
                error=True,
            )
            return

        self.set_license_status(result)
        self.set_status_message("Licenca uspešno aktivirana.")
        self.load_items(list(self.module_keys.keys()))

    def set_license_status(self, result: LicenseResult | None) -> None:
        if result is None or not result.valid:
            self.license_status_label.setText("Licenca ni aktivirana")
            self.license_status_label.setStyleSheet(
                "font-weight: bold; color: #d9534f;"
            )
            self.license_validity_label.setText("")
            self.customer_label.setText("")
            return

        self.license_status_label.setText("Licenca: aktivna")
        self.customer_label.setText(getattr(result, "customer", ""))
        valid_until = date.fromisoformat(result.valid_until)
        days_left = (valid_until - date.today()).days

        if days_left < 0:
            color = "#d9534f"
            message = "Licenca potekla"
        elif days_left <= 30:
            color = "#f0ad4e"
            message = f"Velja do: {result.valid_until} (poteka kmalu)"
        else:
            color = "#5cb85c"
            message = f"Velja do: {result.valid_until}"

        self.license_status_label.setStyleSheet(
            f"font-weight: bold; color: {color};"
        )
        self.license_validity_label.setText(message)

    def show_info_dialog(self) -> None:
        dialog = InfoDialog(self, self.license_result)
        dialog.exec()

    def on_project_tree_context_menu(self, position) -> None:
        item = self.project_tree.itemAt(position)
        if item is None:
            return

        data = item.data(0, Qt.UserRole) or {}
        if data.get("type") != "calculation":
            return

        calculation = self.get_selected_calculation()
        if calculation is None:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Preimenuj")
        reset_action = menu.addAction("Ponastavi kalkulacijo")
        delete_action = menu.addAction("Izbriši")

        selected_action = menu.exec(self.project_tree.viewport().mapToGlobal(position))
        if selected_action == rename_action:
            self.rename_calculation(calculation)
        elif selected_action == reset_action:
            self.reset_calculation(calculation)
        elif selected_action == delete_action:
            self.delete_calculation(calculation)

    def rename_calculation(self, calculation: Calculation) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Preimenuj kontrolo",
            "Novo ime kontrole:",
            text=calculation.name,
        )
        if not ok or not new_name.strip():
            return

        try:
            rename_calculation(calculation, new_name.strip())
            self.refresh_project_tree()
            self.set_status_message(f"Kontrola je bila preimenovana: {new_name}")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Napaka",
                f"Kontrole ni bilo mogoče preimenovati:\n{exc}",
            )

    def reset_calculation(self, calculation: Calculation) -> None:
        try:
            reset_calculation(calculation)
            self.set_status_message("Kontrola je bila ponastavljena na prvotno predlogo.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Napaka",
                f"Kontrole ni bilo mogoče ponastaviti:\n{exc}",
            )

    def delete_calculation(self, calculation: Calculation) -> None:
        confirm = QMessageBox.question(
            self,
            "Izbriši kontrolo",
            f"Ali res želite izbrisati kontrolo '{calculation.name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            delete_calculation(calculation)
            self.refresh_project_tree()
            self.set_status_message(f"Kontrola '{calculation.name}' je bila izbrisana.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Napaka",
                f"Kontrole ni bilo mogoče izbrisati:\n{exc}",
            )

    def extract_module_keys(self, modules: dict[str, dict[str, Any]]) -> dict[str, str]:
        module_keys: dict[str, str] = {}

        for module_id, module_data in modules.items():
            encrypted_key = module_data.get("encrypted_key")

            if not isinstance(encrypted_key, str) or not encrypted_key.strip():
                continue

            module_key = decrypt_module_key(
                encrypted_key,
                LAUNCHER_PRIVATE_KEY_PATH,
            )

            module_keys[module_id] = module_key

        return module_keys

    def load_items(self, modules: list[str]) -> None:
        self.module_tree.clear()
        self.items = available_items(modules)

        modules_by_id: dict[str, QTreeWidgetItem] = {}

        for item in self.items:
            parent = modules_by_id.get(item.module_id)

            if parent is None:
                parent = QTreeWidgetItem([item.module_title])
                parent.setExpanded(False)
                parent.setIcon(0, self.folder_icon)
                parent.setData(0, Qt.UserRole, {"type": "module", "module_id": item.module_id})
                parent.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
                parent.setBackground(0, QBrush(QColor("#f0f0f0")))
                self.module_tree.addTopLevelItem(parent)
                modules_by_id[item.module_id] = parent

            child = QTreeWidgetItem([item.title])
            child.setIcon(0, self.file_icon)
            child.setData(
                0,
                Qt.UserRole,
                {
                    "type": "module_item",
                    "module_id": item.module_id,
                    "item_id": item.item_id,
                },
            )
            child.setBackground(0, QBrush(QColor("white")))
            parent.addChild(child)

        if not self.items:
            self.set_status_message(
                "Licenca je veljavna, vendar nima dodeljenih modulov ali pa moduli nimajo veljavnih ključev.",
                error=True,
            )

    def on_module_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole) or {}

        item_type = data.get("type")
        if item_type == "module":
            item.setExpanded(not item.isExpanded())
            self.details_title.setText(item.text(0))
            self.details_description.setText(
                "Izberite predlogo modula za ustvarjanje nove kontrole."
            )
            self.clear_details_info()
            self.context_selected_label.setText(f"Modul: {item.text(0)}")
            return

        if item_type == "module_item":
            selected_item = self.get_selected_module_item()
            if selected_item is None:
                return

            self.details_title.setText(selected_item.title)
            self.details_description.setText(
                "Dvojni klik ustvari novo kontrolo v odprtem projektu."
            )
            self.set_details_info(
                [
                    f"Modul: {selected_item.module_title}",
                    f"Predloga: {selected_item.title}",
                ]
            )
            self.context_selected_label.setText(
                f"Izbran modul: {selected_item.module_title} / {selected_item.title}"
            )
            return

    def get_selected_module_item(self) -> ModuleItem | None:
        tree_item = self.module_tree.currentItem()

        if tree_item is None:
            return None

        data = tree_item.data(0, Qt.UserRole) or {}

        if data.get("type") != "module_item":
            return None

        module_id = data.get("module_id")
        item_id = data.get("item_id")

        return next(
            (
                item
                for item in self.items
                if item.module_id == module_id and item.item_id == item_id
            ),
            None,
        )

    def set_details_info(self, lines: list[str]) -> None:
        self.clear_details_info()
        for line in lines:
            label = QLabel(line)
            label.setStyleSheet("color: #333333;")
            self.details_info_area.addWidget(label)
            self.details_info_labels.append(label)

    def clear_details_info(self) -> None:
        for label in self.details_info_labels:
            self.details_info_area.removeWidget(label)
            label.deleteLater()
        self.details_info_labels.clear()

    def new_project(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Nov projekt",
            "Ime projekta:",
        )

        if not ok or not name.strip():
            return

        try:
            self.current_project = create_project(name.strip())
            self.project_label.setText(f"Projekt: {self.current_project.name}")
            self.refresh_project_tree()
            self.set_status_message(f"Projekt '{self.current_project.name}' ustvarjen.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Projekt",
                f"Projekta ni bilo mogoče ustvariti:\n{exc}",
            )

    def open_project_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Odpri BetonCheck projekt",
        )

        if not path:
            return

        try:
            self.current_project = open_project(Path(path))
            self.project_label.setText(f"Projekt: {self.current_project.name}")
            self.refresh_project_tree()
            self.set_status_message(f"Projekt '{self.current_project.name}' odprt.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Projekt",
                f"Projekta ni bilo mogoče odpreti:\n{exc}",
            )

    def refresh_project_tree(self) -> None:
        self.project_tree.clear()
        self.calculations = []

        if self.current_project is None:
            return

        self.calculations = list_calculations(self.current_project)

        project_root = QTreeWidgetItem([self.current_project.name])
        project_root.setIcon(0, self.folder_icon)
        project_root.setExpanded(True)
        project_root.setFont(0, QFont("Segoe UI", 11, QFont.Bold))
        project_root.setData(0, Qt.UserRole, {"type": "project_root"})
        self.project_tree.addTopLevelItem(project_root)

        modules_by_id: dict[str, QTreeWidgetItem] = {}

        for index, calculation in enumerate(self.calculations):
            module_parent = modules_by_id.get(calculation.module_id)

            if module_parent is None:
                module_parent = QTreeWidgetItem([calculation.module_id])
                module_parent.setIcon(0, self.folder_icon)
                module_parent.setExpanded(True)
                module_parent.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
                module_parent.setData(
                    0,
                    Qt.UserRole,
                    {"type": "project_module", "module_id": calculation.module_id},
                )
                project_root.addChild(module_parent)
                modules_by_id[calculation.module_id] = module_parent

            child = QTreeWidgetItem([calculation.name])
            child.setIcon(0, self.file_icon)
            child.setData(
                0,
                Qt.UserRole,
                {
                    "type": "calculation",
                    "index": index,
                },
            )
            module_parent.addChild(child)

            reports_root = QTreeWidgetItem(["Poročila"])
            reports_root.setIcon(0, self.folder_icon)
            reports_root.setData(
                0,
                Qt.UserRole,
                {
                    "type": "report_root",
                    "calculation_index": index,
                },
            )
            child.addChild(reports_root)
            reports_root.setExpanded(False)

            reports_dir = calculation.path / "reports"
            if reports_dir.exists():
                for report_file in sorted(reports_dir.iterdir()):
                    if not report_file.is_file():
                        continue

                    report_item = QTreeWidgetItem([report_file.name])
                    report_item.setIcon(0, self.file_icon)
                    report_item.setData(
                        0,
                        Qt.UserRole,
                        {
                            "type": "report_file",
                            "path": str(report_file),
                        },
                    )
                    reports_root.addChild(report_item)

        self.context_project_label.setText(f"Projekt: {self.current_project.name}")
        self.context_license_label.setText(
            f"Licenca: {'aktivirana' if self.license_result and self.license_result.valid else 'ni aktivirana'}"
        )
        self.context_recent_label.setText(
            f"Nedavne kontrole: {len(self.calculations)}"
        )

    def new_calculation_from_tree(
        self,
        item: QTreeWidgetItem | None = None,
        column: int = 0,
    ) -> None:
        if self.current_project is None:
            self.set_status_message(
                "Najprej ustvarite ali odprite projekt.",
                error=True,
            )
            return

        selected_item = self.get_selected_module_item()

        if selected_item is None:
            self.set_status_message(
                "Izberite Excel kontrolo znotraj modula.",
                error=True,
            )
            return

        module_key = self.module_keys.get(selected_item.module_id)

        if not module_key:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licenca ne vsebuje ključa za modul: {selected_item.module_id}",
            )
            return

        try:
            self.set_status_message(f"Prenašam predlogo: {selected_item.title} ...")
            QApplication.processEvents()

            encrypted_template_path = ensure_downloaded(selected_item)
            calculation_name = generate_calculation_name(
                self.current_project,
                selected_item,
            )

            calculation = create_calculation_from_template(
                project=self.current_project,
                item=selected_item,
                encrypted_template_path=encrypted_template_path,
                module_key=module_key,
                calculation_name=calculation_name,
            )

            self.refresh_project_tree()
            self.set_status_message(f"Ustvarjena kontrola: {calculation.name}")
            self.open_calculation_with_dialog(calculation, module_key)

        except Exception as exc:
            self.set_status_message(
                f"Kontrole ni bilo mogoče ustvariti: {exc}",
                error=True,
            )

    def get_selected_calculation(self) -> Calculation | None:
        item = self.project_tree.currentItem()

        if item is None:
            return None

        data = item.data(0, Qt.UserRole) or {}

        if data.get("type") != "calculation":
            return None

        index = data.get("index")

        if not isinstance(index, int):
            return None

        if index < 0 or index >= len(self.calculations):
            return None

        return self.calculations[index]

    def on_project_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole) or {}
        item_type = data.get("type")

        if item_type == "project_module":
            self.context_selected_label.setText(f"Projektni modul: {item.text(0)}")
            return

        if item_type == "calculation":
            calculation = self.get_selected_calculation()
            if calculation is None:
                return

            self.context_selected_label.setText(
                f"Izbrana kontrola: {calculation.name}"
            )
            self.details_title.setText(calculation.name)
            self.details_description.setText(
                "Dvojni klik za odpiranje v Excelu."
            )
            self.set_details_info(
                [
                    f"Modul: {calculation.module_id}",
                    f"Pot: {calculation.path}",
                ]
            )
            return

        if item_type == "report_root":
            self.context_selected_label.setText("Mapa poročil")
            self.details_title.setText("Poročila")
            self.details_description.setText(
                "Dvojni klik na datoteko poročila za odpiranje."
            )
            self.clear_details_info()
            return

        if item_type == "report_file":
            path_str = data.get("path")
            self.context_selected_label.setText(f"Poročilo: {item.text(0)}")
            self.details_title.setText(item.text(0))
            self.details_description.setText(
                "Dvojni klik odpre izbrano datoteko poročila."
            )
            self.set_details_info([f"Pot: {path_str}"])
            return

    def set_status_message(self, message: str, error: bool = False, timeout: int = 5000) -> None:
        self.status_label.setText(message)
        if error:
            self.status_label.setStyleSheet(
                "padding: 6px; background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;"
            )
        else:
            self.status_label.setStyleSheet(
                "padding: 6px; background: #f8f8f8; color: #333333;"
            )

        self.status_timer.start(timeout)

    def on_project_tree_double_clicked(
        self,
        item: QTreeWidgetItem | None = None,
        column: int = 0,
    ) -> None:
        if item is None:
            return

        data = item.data(0, Qt.UserRole) or {}
        item_type = data.get("type")

        if item_type == "calculation":
            calculation = self.get_selected_calculation()

            if calculation is None:
                self.set_status_message(
                    "Izberite shranjeno kontrolo v projektu.",
                    error=True,
                )
                return

            module_key = self.module_keys.get(calculation.module_id)

            if not module_key:
                QMessageBox.critical(
                    self,
                    "Licenca",
                    f"Licenca ne vsebuje ključa za modul: {calculation.module_id}",
                )
                return

            try:
                self.open_calculation_with_dialog(calculation, module_key)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Kontrola",
                    f"Kontrole ni bilo mogoče odpreti:\n{exc}",
                )
            return

        if item_type == "report_file":
            path_str = data.get("path")
            if not path_str:
                return

            self.open_file(Path(path_str))

    def open_file(self, path: Path) -> None:
        if not path.exists():
            self.set_status_message(
                f"Datoteka ni najdena: {path}",
                error=True,
            )
            return

        open_external_file(path)

    def reset_status_bar(self) -> None:
        self.status_label.setText("Pripravljen")
        self.status_label.setStyleSheet("padding: 6px; background: #f8f8f8; color: #333333;")

    def open_calculation_with_dialog(
        self,
        calculation: Calculation,
        module_key: str,
    ) -> None:
        temp_xlsx = open_calculation_session(calculation, module_key)
        self.set_status_message(
            f"Kontrola '{calculation.name}' je bila odprta v Excelu."
        )
        self.refresh_project_tree()

    def open_project_folder(self) -> None:
        if self.current_project is None:
            return

        self.open_folder(self.current_project.path)

    def open_reports_folder(self) -> None:
        calculation = self.get_selected_calculation()

        if calculation is None:
            self.set_status_message(
                "Izberite kontrolo, da odprete mapo s poročili.",
                error=True,
            )
            return

        reports_dir = calculation.path / "reports"
        reports_dir.mkdir(exist_ok=True)

        self.open_folder(reports_dir)

    def open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{path}"')

    def check_updates(self) -> None:
        try:
            _has_update, message = check_for_update()
            QMessageBox.information(self, "Posodobitve", message)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Posodobitve",
                f"Posodobitev ni bilo mogoče preveriti:\n{exc}",
            )


def main() -> None:
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