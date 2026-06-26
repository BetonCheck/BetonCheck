from __future__ import annotations

import os
import sys
import json
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
    QHeaderView,
    QMenu,
    QSizePolicy,
)

from betoncheck_customer.eula import has_accepted_eula, accept_eula
from betoncheck_customer.license_checker import check_license, load_license_key, LicenseResult
from betoncheck_customer.module_manager import (
    available_items,
    ensure_downloaded,
    ModuleItem,
)
from betoncheck_customer.key_decryption import decrypt_module_key
from betoncheck_customer.settings import (
    APP_NAME,
    APP_VERSION,
    LAUNCHER_PRIVATE_KEY_PATH,
    LOCAL_LICENSE_KEY_PATH,
    PROJECTS_DIR,
)
from betoncheck_customer.updater import check_for_update
from betoncheck_customer.project_manager import (
    Project,
    Calculation,
    create_project,
    open_project,
    list_calculations,
    create_calculation_from_template,
    generate_calculation_name,
    rename_calculation,
    reset_calculation,
    delete_calculation,
)
from betoncheck_customer.excel_session import (
    export_calculation_pdf,
    export_calculation_pdf_from_saved,
    open_calculation_session,
    open_file as open_external_file,
    save_calculation_back,
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

        self.terms_button = QPushButton("Pogoji uporabe")
        self.terms_button.clicked.connect(self.on_show_terms)

        close_button = QPushButton("Zapri")
        close_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.update_button)
        button_layout.addWidget(self.terms_button)
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

    def on_show_terms(self) -> None:
        try:
            with open("LICENSE.txt", "r", encoding="utf-8") as file:
                terms = file.read()
        except FileNotFoundError:
            terms = "Pogoji uporabe niso najdeni."
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Pogoji uporabe",
                f"Pogojev uporabe ni bilo mogoče prebrati:\n{exc}",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Pogoji uporabe")
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(terms)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.button(QDialogButtonBox.Close).setText("Zapri")
        button_box.rejected.connect(dialog.reject)

        layout.addWidget(text)
        layout.addWidget(button_box)

        dialog.exec()

    def on_refresh_license(self) -> None:
        pass


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(1464, 807)
        self.setMinimumSize(1280, 640)

        self.license_result = None
        self.active_license_key: str | None = None
        self.items: list[ModuleItem] = []
        self.module_keys: dict[str, str] = {}

        self.current_project: Project | None = None
        self.calculations: list[Calculation] = []

        self.folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        self.save_icon = self.style().standardIcon(QStyle.SP_DialogSaveButton)
        self.export_icon = self.style().standardIcon(QStyle.SP_ArrowRight)
        self.opened_sessions: dict[str, Path] = {}
        self.opened_sessions_seen_locked: set[str] = set()
        self._close_dialog_in_progress = False

        self.license_input = QLineEdit(load_license_key() or "")
        self.license_input.setPlaceholderText("Licenčni ključ")
        self.license_input.setMinimumWidth(440)
        self.license_input.setMaximumWidth(650)

        self.license_status_label = QLabel("Licenca ni aktivirana")
        self.license_status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.license_status_label.setMinimumWidth(145)
        self.license_status_label.setStyleSheet(
            "font-weight: bold; color: #d9534f;"
        )

        self.license_validity_label = QLabel("")
        self.license_validity_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.license_validity_label.setMinimumWidth(220)
        self.license_validity_label.setStyleSheet(
            "color: #444444;"
        )

        self.customer_label = QLabel("")
        self.customer_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.customer_label.setMinimumWidth(130)
        self.customer_label.setStyleSheet(
            "font-weight: bold; color: #111111;"
        )

        self.activate_btn = QPushButton("Aktiviraj")
        self.activate_btn.setMinimumWidth(158)
        self.activate_btn.clicked.connect(self.activate)

        self.info_btn = QPushButton("Info")
        self.info_btn.setMinimumWidth(112)
        self.info_btn.clicked.connect(self.show_info_dialog)

        self.new_project_btn = QPushButton("Nov projekt")
        self.new_project_btn.setMinimumWidth(110)
        self.new_project_btn.clicked.connect(self.new_project)

        self.open_project_btn = QPushButton("Odpri projekt")
        self.open_project_btn.setMinimumWidth(118)
        self.open_project_btn.clicked.connect(self.open_project_dialog)

        self.project_label = QLabel("Projekt: ni odprt")
        self.project_label.setMinimumWidth(190)

        self.generate_report_btn = QPushButton("Generiraj PDF")
        self.generate_report_btn.setMinimumWidth(112)
        self.generate_report_btn.clicked.connect(self.generate_report_pdfs)

        self.intro_page_btn = QPushButton("Uvodna stran")
        self.intro_page_btn.setMinimumWidth(120)
        self.intro_page_btn.clicked.connect(self.edit_intro_page)

        self.export_final_report_btn = QPushButton("Izvozi PDF")
        self.export_final_report_btn.setMinimumWidth(112)
        self.export_final_report_btn.clicked.connect(self.export_final_report_pdf)

        self.module_tree = QTreeWidget()
        self.setup_tree(self.module_tree, 1)
        self.module_tree.setEnabled(False)
        self.module_tree.itemClicked.connect(self.on_module_item_clicked)
        self.module_tree.itemDoubleClicked.connect(self.new_calculation_from_tree)

        self.project_tree = QTreeWidget()
        self.setup_tree(self.project_tree, 1)
        self.project_tree.itemClicked.connect(self.on_project_tree_item_clicked)
        self.project_tree.itemDoubleClicked.connect(self.on_project_tree_double_clicked)
        self.project_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(
            self.on_project_tree_context_menu
        )

        self.report_tree = QTreeWidget()
        self.setup_tree(self.report_tree, 1)
        self.report_tree.itemDoubleClicked.connect(self.on_report_item_double_clicked)
        self.report_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.report_tree.customContextMenuRequested.connect(
            self.on_report_tree_context_menu
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
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.status_label.setFixedHeight(44)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.status_label.setStyleSheet(self.status_bar_style())

        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.reset_status_bar)

        self.watch_excel_close_timer = QTimer(self)
        self.watch_excel_close_timer.setInterval(1500)
        self.watch_excel_close_timer.timeout.connect(self.check_opened_sessions)
        self.watch_excel_close_timer.start()

        self.apply_window_style()
        self.build_ui()
        self.license_input.textChanged.connect(self.on_license_input_changed)
        if self.license_input.text().strip():
            QTimer.singleShot(0, self.activate_saved_license)

    def apply_window_style(self) -> None:
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(
            """
            QWidget {
                background: #f0f0f0;
                color: #000000;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QLineEdit {
                background: #ffffff;
                border: 1px solid #8f8f8f;
                padding: 3px 5px;
                min-height: 24px;
            }
            QPushButton {
                background: #e9e9e9;
                border: 1px solid #adadad;
                border-radius: 0;
                padding: 4px 12px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: #e5f1fb;
                border-color: #0078d7;
            }
            QPushButton:pressed {
                background: #cce4f7;
                border-color: #005a9e;
            }
            QGroupBox {
                border: 1px solid #dddddd;
                margin-top: 14px;
                padding-top: 7px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                background: #f0f0f0;
            }
            QTreeWidget {
                background: #ffffff;
                border: 1px solid #9aa4b1;
                outline: 0;
                padding: 3px 0;
            }
            QTreeWidget::item {
                min-height: 30px;
            }
            QTreeWidget::item:selected {
                background: #e8e8e8;
                color: #000000;
            }
            QSplitter::handle {
                background: #f0f0f0;
            }
            QLabel#StatusLabel {
                background: #fbfbfb;
                color: #111111;
                border: 1px solid #ffffff;
                border-top: 2px groove #c7c7c7;
                padding: 8px 14px;
            }
            """
        )

    def status_bar_style(self, error: bool = False) -> str:
        if error:
            return (
                "padding: 8px 14px; background: #f8d7da; color: #721c24; "
                "border: 1px solid #f5c6cb; border-top: 2px groove #c7c7c7;"
            )

        return (
            "padding: 8px 14px; background: #fbfbfb; color: #111111; "
            "border: 1px solid #ffffff; border-top: 2px groove #c7c7c7;"
        )

    def setup_tree(self, tree: QTreeWidget, columns: int = 3) -> None:
        tree.setColumnCount(columns)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setUniformRowHeights(True)
        tree.setAnimated(True)
        tree.setIndentation(20)
        tree.setExpandsOnDoubleClick(False)
        tree.setTextElideMode(Qt.ElideNone)
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)

        if columns > 1:
            tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
            tree.setColumnWidth(1, 0)

        if columns > 2:
            tree.header().setSectionResizeMode(2, QHeaderView.Fixed)
            tree.setColumnWidth(2, 100)

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 10)
        root.setSpacing(7)

        license_layout = QHBoxLayout()
        license_layout.setContentsMargins(0, 0, 0, 0)
        license_layout.setSpacing(10)
        license_layout.addWidget(QLabel("Licence:"))
        license_layout.addWidget(self.license_input, 1)
        license_layout.addWidget(self.activate_btn)
        license_layout.addSpacing(10)
        license_layout.addWidget(self.customer_label)
        license_layout.addSpacing(16)
        license_layout.addWidget(self.license_status_label)
        license_layout.addSpacing(16)
        license_layout.addWidget(self.license_validity_label)
        license_layout.addStretch(1)

        top_panel = QWidget(self)
        top_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(7)
        top_layout.addLayout(license_layout)

        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.setHandleWidth(8)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        modules_group = QGroupBox("Razpoložljivi moduli")
        modules_layout = QVBoxLayout(modules_group)
        modules_layout.setContentsMargins(14, 14, 14, 12)
        modules_layout.addWidget(self.module_tree)

        project_group = QGroupBox("Projekt")
        project_layout = QVBoxLayout(project_group)
        project_layout.setContentsMargins(14, 14, 14, 12)
        project_layout.addWidget(self.project_tree)

        report_group = QGroupBox("Poročilo")
        report_layout = QVBoxLayout(report_group)
        report_layout.setContentsMargins(14, 14, 14, 12)
        report_layout.addWidget(self.report_tree)

        main_splitter.addWidget(modules_group)
        main_splitter.addWidget(project_group)
        main_splitter.addWidget(report_group)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setStretchFactor(2, 4)
        main_splitter.setSizes([430, 500, 500])

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        modules_toolbar = QWidget(self)
        modules_toolbar_layout = QHBoxLayout(modules_toolbar)
        modules_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        modules_toolbar_layout.setSpacing(8)
        modules_toolbar_layout.addWidget(self.info_btn)
        modules_toolbar_layout.addStretch(1)

        project_toolbar = QWidget(self)
        project_toolbar_layout = QHBoxLayout(project_toolbar)
        project_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        project_toolbar_layout.setSpacing(8)
        project_toolbar_layout.addStretch(1)
        project_toolbar_layout.addWidget(self.new_project_btn)
        project_toolbar_layout.addWidget(self.open_project_btn)
        project_toolbar_layout.addWidget(self.project_label)
        project_toolbar_layout.addStretch(1)

        report_toolbar = QWidget(self)
        report_toolbar_layout = QHBoxLayout(report_toolbar)
        report_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        report_toolbar_layout.setSpacing(8)
        report_toolbar_layout.addStretch(1)
        report_toolbar_layout.addWidget(self.generate_report_btn)
        report_toolbar_layout.addWidget(self.intro_page_btn)
        report_toolbar_layout.addWidget(self.export_final_report_btn)

        toolbar.addWidget(modules_toolbar, 3)
        toolbar.addWidget(project_toolbar, 4)
        toolbar.addWidget(report_toolbar, 4)
        top_layout.addLayout(toolbar)

        root.addWidget(top_panel)
        root.addWidget(main_splitter, 1)
        root.addWidget(self.status_label)

    def activate_saved_license(self) -> None:
        if not self.license_input.text().strip():
            return

        self.set_status_message("Preverjam shranjeno licenco ...")
        self.activate()

    def on_license_input_changed(self, text: str) -> None:
        key = text.strip()

        if (
            key
            and self.active_license_key == key
            and self.license_result is not None
            and self.license_result.valid
        ):
            return

        had_access = (
            self.active_license_key is not None
            or bool(self.module_keys)
            or bool(self.items)
            or self.module_tree.topLevelItemCount() > 0
        )

        if not key or had_access:
            self.clear_saved_license_key()

        self.revoke_license_access()

        if had_access:
            if key:
                self.set_status_message(
                    "Licenca je bila spremenjena. Za dostop do modulov jo znova aktivirajte.",
                    error=True,
                )
            else:
                self.set_status_message(
                    "Licenčni ključ je odstranjen. Moduli niso dostopni.",
                    error=True,
                )

    def clear_saved_license_key(self) -> None:
        try:
            LOCAL_LICENSE_KEY_PATH.unlink(missing_ok=True)
        except OSError as exc:
            self.set_status_message(
                f"Shranjene licence ni bilo mogoče odstraniti: {exc}",
                error=True,
            )

    def clear_module_access(self) -> None:
        self.module_keys.clear()
        self.items.clear()
        self.module_tree.clear()
        self.module_tree.setEnabled(False)
        self.context_license_label.setText("Licenca: ni aktivirana")

    def revoke_license_access(self, result: LicenseResult | None = None) -> None:
        self.active_license_key = None
        self.license_result = result
        self.clear_module_access()
        self.set_license_status(result)

    def activate(self) -> None:
        license_key = self.license_input.text().strip()
        if not license_key:
            self.clear_saved_license_key()
            self.revoke_license_access()
            self.set_status_message("Licenčni ključ ni vpisan.", error=True)
            return

        try:
            result = check_license(license_key)
        except Exception as exc:
            self.revoke_license_access()
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licence ni bilo mogoče preveriti:\n{exc}",
            )
            self.set_status_message(f"Licence ni bilo mogoče preveriti: {exc}", error=True)
            return

        self.license_result = result

        if not result.valid:
            self.revoke_license_access(result)
            self.set_status_message(result.message, error=True)
            return

        try:
            self.module_keys = self.extract_module_keys(result.modules or {})
        except Exception as exc:
            self.revoke_license_access()
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

        self.active_license_key = result.key or license_key
        self.set_license_status(result)
        self.context_license_label.setText("Licenca: aktivirana")
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
            color = "#35b64b"
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
        item_type = data.get("type")

        menu = QMenu(self)

        if item_type == "calculation":
            calculation = self.get_selected_calculation()
            if calculation is None:
                return

            open_action = menu.addAction("Odpri")
            rename_action = menu.addAction("Preimenuj")
            delete_action = menu.addAction("Izbriši")

            selected_action = menu.exec(self.project_tree.viewport().mapToGlobal(position))
            if selected_action == open_action:
                module_key = self.module_keys.get(calculation.module_id)
                if module_key:
                    self.open_calculation_with_dialog(calculation, module_key)
            elif selected_action == rename_action:
                self.rename_calculation(calculation)
            elif selected_action == delete_action:
                self.delete_calculation(calculation)
            return


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
        self.module_tree.setEnabled(True)
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

        if not ok:
            return

        name = name.strip()

        if not name:
            QMessageBox.warning(
                self,
                "Projekt",
                "Ime projekta ne sme biti prazno.",
            )
            return

        try:
            try:
                self.current_project = create_project(name)
            except TypeError as exc:
                if "'NoneType' object is not iterable" not in str(exc):
                    raise

                self.current_project = create_project(
                    name=name,
                    calculations=[],
                )

            if self.current_project is None:
                raise RuntimeError("Funkcija create_project je vrnila None.")

            self.project_label.setText(f"Projekt: {self.current_project.name}")
            self.refresh_project_tree()
            self.refresh_report_tree()
            self.set_status_message(f"Projekt '{self.current_project.name}' ustvarjen.")

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Projekt",
                f"Projekta ni bilo mogoče ustvariti:\n{exc}",
            )
            self.set_status_message(
                f"Projekta ni bilo mogoče ustvariti: {exc}",
                error=True,
            )

    def open_project_dialog(self) -> None:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        path = QFileDialog.getExistingDirectory(
            self,
            "Odpri BetonCheck projekt",
            str(PROJECTS_DIR),
        )

        if not path:
            return

        try:
            self.current_project = open_project(Path(path))
            self.project_label.setText(f"Projekt: {self.current_project.name}")
            self.refresh_project_tree()
            self.refresh_report_tree()
            self.set_status_message(f"Projekt '{self.current_project.name}' odprt.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Projekt",
                f"Projekta ni bilo mogoče odpreti:\n{exc}",
            )

    def refresh_project_tree(self) -> None:
        expanded_keys, selected_key, selected_module_id, selected_calc_index = self.get_project_tree_state()
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
        selected_restored = False

        for index, calculation in enumerate(self.calculations):
            module_parent = modules_by_id.get(calculation.module_id)

            if module_parent is None:
                module_title = getattr(calculation, "module_title", calculation.module_id)
                module_parent = QTreeWidgetItem([module_title])
                module_parent.setIcon(0, self.folder_icon)
                module_key = f"project_module:{calculation.module_id}"
                module_parent.setExpanded(module_key in expanded_keys)
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
            child.setToolTip(0, calculation.name)
            child.setData(
                0,
                Qt.UserRole,
                {
                    "type": "calculation",
                    "index": index,
                    "module_id": calculation.module_id,
                    "path": str(calculation.path),
                },
            )
            module_parent.addChild(child)

            module_key = f"project_module:{calculation.module_id}"
            if module_key in expanded_keys:
                module_parent.setExpanded(True)

            if selected_key == f"calculation:{calculation.path}" or (
                selected_calc_index == index and selected_module_id == calculation.module_id
            ):
                self.project_tree.setCurrentItem(child)
                selected_restored = True

        project_root.setExpanded(True)

        if not selected_restored:
            if selected_key == "project_root":
                self.project_tree.setCurrentItem(project_root)
            elif selected_module_id is not None:
                selected_module_item = modules_by_id.get(selected_module_id)
                if selected_module_item is not None:
                    self.project_tree.setCurrentItem(selected_module_item)

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
            self.expand_and_select_calculation(calculation)
            self.set_status_message(f"Ustvarjena kontrola: {calculation.name}")
            self.open_calculation_with_dialog(calculation, module_key)

        except Exception as exc:
            self.set_status_message(
                f"Kontrole ni bilo mogoče ustvariti: {exc}",
                error=True,
            )

    def refresh_report_tree(self) -> None:
        self.report_tree.clear()

        if self.current_project is None:
            return

        reports_dir = self.current_project.path / "reports"
        if not reports_dir.exists():
            return

        intro_path = reports_dir / "00_uvodna_stran.pdf"
        if intro_path.exists():
            item = QTreeWidgetItem([intro_path.name])
            item.setIcon(0, self.file_icon)
            item.setData(
                0,
                Qt.UserRole,
                {
                    "type": "report_pdf",
                    "path": str(intro_path),
                },
            )
            self.report_tree.addTopLevelItem(item)

        pdf_files = sorted(
            p
            for p in reports_dir.rglob("*.pdf")
            if p.name not in {"00_uvodna_stran.pdf", "koncno_porocilo.pdf"}
        )

        for pdf_file in pdf_files:
            item = QTreeWidgetItem([pdf_file.relative_to(reports_dir).as_posix()])
            item.setIcon(0, self.file_icon)
            item.setData(
                0,
                Qt.UserRole,
                {
                    "type": "report_pdf",
                    "path": str(pdf_file),
                },
            )
            self.report_tree.addTopLevelItem(item)

    def on_report_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        data = item.data(0, Qt.UserRole) or {}
        if data.get("type") != "report_pdf":
            return

        path = data.get("path")
        if path:
            self.open_file(Path(path))

    def on_report_tree_context_menu(self, position) -> None:
        item = self.report_tree.itemAt(position)
        if item is None:
            return

        data = item.data(0, Qt.UserRole) or {}
        if data.get("type") != "report_pdf":
            return

        path_str = data.get("path")
        if not path_str:
            return

        menu = QMenu(self)
        open_action = menu.addAction("Odpri")
        folder_action = menu.addAction("Pokaži v mapi")
        delete_action = menu.addAction("Izbriši")

        selected_action = menu.exec(self.report_tree.viewport().mapToGlobal(position))
        if selected_action == open_action:
            self.open_file(Path(path_str))
        elif selected_action == folder_action:
            self.open_folder(Path(path_str).parent)
        elif selected_action == delete_action:
            self.delete_pdf_file(Path(path_str))

    def generate_report_pdfs(self) -> None:
        if self.current_project is None:
            self.set_status_message("Najprej odprite projekt.", error=True)
            return

        if not self.calculations:
            self.set_status_message("V projektu ni nobene kontrole.", error=True)
            return

        success_count = 0
        errors: list[str] = []

        for calculation in self.calculations:
            module_key = self.module_keys.get(calculation.module_id)
            if module_key is None:
                errors.append(f"{calculation.name}: ni licenčnega ključa za modul.")
                continue

            calc_path = str(calculation.path)
            temp_xlsx = self.opened_sessions.get(calc_path)

            if temp_xlsx is not None and temp_xlsx.exists():
                if self._is_file_locked(temp_xlsx):
                    errors.append(f"{calculation.name}: Excel je zaklenjen. Zaprite ga in poskusite znova.")
                    continue

                try:
                    export_calculation_pdf(calculation, temp_xlsx)
                    success_count += 1
                    continue
                except Exception as exc:
                    errors.append(f"{calculation.name}: {exc}")
                    continue

            try:
                export_calculation_pdf_from_saved(calculation, module_key)
                success_count += 1
            except Exception as exc:
                errors.append(f"{calculation.name}: {exc}")

        self.refresh_report_tree()

        message = f"Ustvarjenih PDF poročil: {success_count}, napak: {len(errors)}"
        if errors:
            warning_text = "\n".join(errors)
            QMessageBox.warning(self, "Generiraj PDF", f"{message}\n\n{warning_text}")

        self.set_status_message(message)

    def edit_intro_page(self) -> None:
        if self.current_project is None:
            self.set_status_message("Najprej odprite projekt.", error=True)
            return

        reports_dir = self.current_project.path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        intro_file = reports_dir / "uvodna_stran.json"
        intro_text = self._load_intro_text(intro_file)

        dialog = QDialog(self)
        dialog.setWindowTitle("Uredi uvodno stran")
        dialog.resize(640, 480)
        layout = QVBoxLayout(dialog)

        edit = QTextEdit()
        edit.setPlainText(intro_text)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Save).setText("Shrani")
        button_box.button(QDialogButtonBox.Cancel).setText("Prekliči")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        layout.addWidget(edit)
        layout.addWidget(button_box)

        if dialog.exec() != QDialog.Accepted:
            return

        try:
            intro_file.write_text(
                json.dumps({"content": edit.toPlainText()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.generate_intro_page_pdf()
            self.refresh_report_tree()
            self.set_status_message("Uvodna stran je bila posodobljena.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Uvodna stran",
                f"Uvodne strani ni bilo mogoče shraniti:\n{exc}",
            )

    def _load_intro_text(self, intro_file: Path) -> str:
        if intro_file.exists():
            try:
                data = json.loads(intro_file.read_text(encoding="utf-8"))
                return data.get("content", "")
            except Exception:
                return intro_file.read_text(encoding="utf-8")

        alternative = self.current_project.path / "reports" / "uvodna_stran.txt"
        if alternative.exists():
            return alternative.read_text(encoding="utf-8")

        return (
            "BETONCHECK POROČILO\n\n"
            "Projekt:\n"
            "Investitor:\n"
            "Objekt:\n"
            "Projektant:\n"
            "Datum:\n"
            "Opombe:\n"
        )

    def generate_intro_page_pdf(self) -> Path:
        if self.current_project is None:
            raise RuntimeError("Projekt ni odprt.")

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            raise RuntimeError(
                "Manjka knjižnica reportlab. Namestite jo z ukazom: pip install reportlab"
            )

        reports_dir = self.current_project.path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        intro_file = reports_dir / "uvodna_stran.json"
        intro_text = self._load_intro_text(intro_file)

        output_pdf = reports_dir / "00_uvodna_stran.pdf"
        c = canvas.Canvas(str(output_pdf), pagesize=A4)
        width, height = A4
        margin = 50

        c.setFont("Helvetica-Bold", 24)
        c.drawString(margin, height - margin, "BETONCHECK POROČILO")

        c.setFont("Helvetica", 12)
        y = height - margin - 40
        c.drawString(margin, y, f"Projekt: {self.current_project.name}")
        y -= 20
        c.drawString(margin, y, f"Datum: {date.today().isoformat()}")
        y -= 30

        for line in intro_text.splitlines():
            if y < margin + 20:
                c.showPage()
                y = height - margin
                c.setFont("Helvetica", 12)
            c.drawString(margin, y, line)
            y -= 18

        c.showPage()
        c.save()

        return output_pdf

    def export_final_report_pdf(self) -> None:
        if self.current_project is None:
            self.set_status_message("Najprej odprite projekt.", error=True)
            return

        try:
            from pypdf import PdfWriter
        except ImportError:
            QMessageBox.critical(
                self,
                "Izvozi PDF",
                "Manjka knjižnica pypdf. Namestite jo z ukazom: pip install pypdf",
            )
            return

        reports_dir = self.current_project.path / "reports"
        if not reports_dir.exists():
            self.set_status_message("Mapa poročil ne obstaja.", error=True)
            return

        output_pdf = reports_dir / "koncno_porocilo.pdf"
        writer = PdfWriter()

        intro_path = reports_dir / "00_uvodna_stran.pdf"
        if intro_path.exists():
            writer.append(str(intro_path))

        pdf_files = sorted(
            p
            for p in reports_dir.rglob("*.pdf")
            if p.name not in {"00_uvodna_stran.pdf", "koncno_porocilo.pdf"}
        )

        for pdf_file in pdf_files:
            writer.append(str(pdf_file))

        try:
            with output_pdf.open("wb") as output_file:
                writer.write(output_file)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Izvozi PDF",
                f"Končnega poročila ni bilo mogoče ustvariti:\n{exc}",
            )
            return

        self.refresh_report_tree()
        self.set_status_message(f"Končno poročilo je bilo ustvarjeno: {output_pdf}")
        self.open_file(output_pdf)

    def get_project_tree_state(self) -> tuple[set[str], str | None, str | None, int | None]:
        expanded_keys: set[str] = set()
        selected_key: str | None = None
        selected_module_id: str | None = None
        selected_calc_index: int | None = None

        current = self.project_tree.currentItem()
        if current is not None:
            data = current.data(0, Qt.UserRole) or {}
            item_type = data.get("type", "")
            selected_key = self.project_tree_item_key(current)
            if item_type == "calculation":
                selected_calc_index = data.get("index")
                selected_module_id = data.get("module_id")
            elif item_type == "project_module":
                selected_module_id = data.get("module_id")

        def walk(item: QTreeWidgetItem) -> None:
            for i in range(item.childCount()):
                child = item.child(i)
                key = self.project_tree_item_key(child)
                if child.isExpanded():
                    expanded_keys.add(key)
                walk(child)

        walk(self.project_tree.invisibleRootItem())
        return expanded_keys, selected_key, selected_module_id, selected_calc_index

    def project_tree_item_key(self, item: QTreeWidgetItem) -> str:
        data = item.data(0, Qt.UserRole) or {}
        item_type = data.get("type", "")

        if item_type == "project_root":
            return "project_root"

        if item_type == "project_module":
            return f"project_module:{data.get('module_id', item.text(0))}"

        if item_type == "calculation":
            return f"calculation:{data.get('path', item.text(0))}"

        return f"{item_type}:{item.text(0)}"

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


    def set_status_message(self, message: str, error: bool = False, timeout: int = 5000) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(self.status_bar_style(error))

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

    def expand_and_select_calculation(self, calculation: Calculation) -> None:
        root = self.project_tree.topLevelItem(0)
        if root is None:
            return

        root.setExpanded(True)

        for i in range(root.childCount()):
            module_item = root.child(i)
            data = module_item.data(0, Qt.UserRole) or {}
            if data.get("type") != "project_module":
                continue

            if data.get("module_id") != calculation.module_id:
                continue

            module_item.setExpanded(True)
            for j in range(module_item.childCount()):
                child = module_item.child(j)
                child_data = child.data(0, Qt.UserRole) or {}
                if child_data.get("type") == "calculation" and child.text(0) == calculation.name:
                    self.project_tree.setCurrentItem(child)
                    return


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
        self.status_label.setStyleSheet(self.status_bar_style())

    def _is_file_locked(self, path: Path) -> bool:
        if not path.exists():
            return False

        try:
            with open(path, "r+b"):
                return False
        except OSError:
            return True

    def open_calculation_with_dialog(
        self,
        calculation: Calculation,
        module_key: str,
    ) -> None:
        calc_path = str(calculation.path)
        temp_xlsx = self.opened_sessions.get(calc_path)

        if temp_xlsx is not None:
            if temp_xlsx.exists() and self._is_file_locked(temp_xlsx):
                self.set_status_message(
                    f"Kontrola '{calculation.name}' je že odprta v Excelu."
                )
                return
            self.opened_sessions.pop(calc_path, None)
            self.opened_sessions_seen_locked.discard(calc_path)

        temp_xlsx = open_calculation_session(calculation, module_key)
        self.opened_sessions[calc_path] = temp_xlsx
        self.opened_sessions_seen_locked.discard(calc_path)
        self.set_status_message(
            f"Kontrola '{calculation.name}' je bila odprta v Excelu."
        )

    def check_opened_sessions(self) -> None:
        if self._close_dialog_in_progress or not self.opened_sessions:
            return

        for calc_path, temp_xlsx in list(self.opened_sessions.items()):
            if not temp_xlsx.exists():
                self.opened_sessions.pop(calc_path, None)
                self.opened_sessions_seen_locked.discard(calc_path)
                continue

            if self._is_file_locked(temp_xlsx):
                self.opened_sessions_seen_locked.add(calc_path)
                continue

            if calc_path not in self.opened_sessions_seen_locked:
                continue

            calculation = next(
                (
                    calc
                    for calc in self.calculations
                    if str(calc.path) == calc_path
                ),
                None,
            )

            if calculation is None:
                continue

            self._close_dialog_in_progress = True
            try:
                self._prompt_save_on_excel_close(calculation, temp_xlsx)
            finally:
                self._close_dialog_in_progress = False
            return

    def _prompt_save_on_excel_close(
        self,
        calculation: Calculation,
        temp_xlsx: Path,
    ) -> None:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Excel se je zaprl")
        message_box.setText(
            f"Excel je bil zaprt za kontrolo '{calculation.name}'.\n"
            "Ali želite shraniti spremembe?"
        )
        save_button = message_box.addButton("Shrani", QMessageBox.AcceptRole)
        cancel_button = message_box.addButton("Prekliči", QMessageBox.RejectRole)
        message_box.setDefaultButton(save_button)
        message_box.exec()

        if message_box.clickedButton() == save_button:
            module_key = self.module_keys.get(calculation.module_id)
            if module_key is None:
                QMessageBox.critical(
                    self,
                    "Licenca",
                    f"Licenca ne vsebuje ključa za modul: {calculation.module_id}",
                )
                return

            try:
                save_calculation_back(calculation, module_key, temp_xlsx)
                self.opened_sessions.pop(str(calculation.path), None)
                self.opened_sessions_seen_locked.discard(str(calculation.path))
                self.set_status_message(
                    f"Kontrola '{calculation.name}' je bila shranjena po zaprtju Excela."
                )
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Shrani",
                    f"Kontrolni datoteki ni bilo mogoče shraniti:\n{exc}",
                )
        else:
            try:
                temp_xlsx.unlink()
            except (FileNotFoundError, PermissionError):
                pass
            self.opened_sessions.pop(str(calculation.path), None)
            self.opened_sessions_seen_locked.discard(str(calculation.path))
            self.set_status_message(
                f"Spremembe za kontrolo '{calculation.name}' niso bile shranjene."
            )

    def save_calculation_item(self, calculation: Calculation) -> None:
        module_key = self.module_keys.get(calculation.module_id)
        if module_key is None:
            QMessageBox.critical(
                self,
                "Licenca",
                f"Licenca ne vsebuje ključa za modul: {calculation.module_id}",
            )
            return

        calc_path = str(calculation.path)
        temp_xlsx = self.opened_sessions.get(calc_path)
        if temp_xlsx is None or not temp_xlsx.exists():
            self.set_status_message(
                "Najprej odprite kontrolo v Excelu, nato jo shranite.",
                error=True,
            )
            return

        if self._is_file_locked(temp_xlsx):
            QMessageBox.information(
                self,
                "Shrani",
                "Excel je odprt. Zaprite ali shranite datoteko v Excelu, nato ponovite Shrani.",
            )
            return

        try:
            save_calculation_back(calculation, module_key, temp_xlsx)
            self.opened_sessions.pop(calc_path, None)
            self.opened_sessions_seen_locked.discard(calc_path)
            self.set_status_message(f"Kontrola '{calculation.name}' je bila shranjena.")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Shrani",
                f"Kontrolni datoteki ni bilo mogoče shraniti:\n{exc}",
            )
        finally:
            self.refresh_project_tree()


    def open_project_folder(self) -> None:
        if self.current_project is None:
            return

        self.open_folder(self.current_project.path)

    def open_reports_folder(self) -> None:
        if self.current_project is None:
            self.set_status_message(
                "Najprej odprite projekt.",
                error=True,
            )
            return

        reports_dir = self.current_project.path / "reports"
        reports_dir.mkdir(exist_ok=True)
        self.open_folder(reports_dir)

    def delete_pdf_file(self, path: Path) -> None:
        if not path.exists():
            self.set_status_message(f"Datoteka ni najdena: {path}", error=True)
            return

        confirm = QMessageBox.question(
            self,
            "Izbriši PDF",
            f"Ali res želite izbrisati PDF '{path.name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            path.unlink()
            self.set_status_message(f"PDF '{path.name}' je bil izbrisan.")
            self.refresh_report_tree()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Napaka",
                f"PDF ni bilo mogoče izbrisati:\n{exc}",
            )

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
