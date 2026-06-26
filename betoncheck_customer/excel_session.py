from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import uuid4

from .crypto_vault import decrypt_file, encrypt_file
from .project_manager import Calculation, slugify, update_calculation_timestamp
from .settings import TEMP_DIR


def open_file(path: Path) -> subprocess.Popen | None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return None

    return subprocess.Popen(["xdg-open", str(path)])


def prepare_calculation_temp(
    calculation: Calculation,
    module_key: str,
) -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    work_file = calculation.path / "calculation.bckwork"

    if not work_file.exists():
        raise FileNotFoundError(f"Manjka delovna datoteka: {work_file}")

    temp_xlsx = TEMP_DIR / f"{slugify(calculation.name)}_{uuid4().hex}.xlsx"

    decrypt_file(work_file, temp_xlsx, module_key)

    return temp_xlsx


def _escape_vb_string(text: str) -> str:
    return text.replace('"', '""')


def _run_vbscript(script: str) -> None:
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".vbs",
        delete=False,
        encoding="utf-8",
    ) as script_file:
        script_file.write(script)
        temp_script_path = Path(script_file.name)

    try:
        subprocess.check_call(
            [
                "cscript",
                "//NoLogo",
                str(temp_script_path),
            ]
        )
    finally:
        try:
            temp_script_path.unlink()
        except FileNotFoundError:
            pass


def _save_workbook_if_open(temp_xlsx: Path) -> None:
    if os.name != "nt":
        return

    script = f"""
On Error Resume Next
Set excelApp = GetObject(, "Excel.Application")
If Err.Number = 0 Then
    For Each workbook In excelApp.Workbooks
        If LCase(workbook.FullName) = LCase("{_escape_vb_string(str(temp_xlsx))}") Then
            workbook.Save
            Exit For
        End If
    Next
End If
"""
    _run_vbscript(script)


def save_calculation_back(
    calculation: Calculation,
    module_key: str,
    temp_xlsx: Path,
) -> None:
    work_file = calculation.path / "calculation.bckwork"

    if not temp_xlsx.exists():
        raise FileNotFoundError(
            "Začasna Excel datoteka ne obstaja več, zato je ni mogoče shraniti nazaj."
        )

    _save_workbook_if_open(temp_xlsx)
    encrypt_file(temp_xlsx, work_file, module_key)
    update_calculation_timestamp(calculation)

    try:
        temp_xlsx.unlink()
    except (FileNotFoundError, PermissionError):
        pass


def open_calculation_session(
    calculation: Calculation,
    module_key: str,
) -> Path:
    temp_xlsx = prepare_calculation_temp(calculation, module_key)
    open_file(temp_xlsx)
    return temp_xlsx


def export_calculation_pdf(
    calculation: Calculation,
    temp_xlsx: Path,
) -> Path:
    if os.name != "nt":
        raise NotImplementedError("PDF export is currently supported only on Windows.")

    if not temp_xlsx.exists():
        raise FileNotFoundError(f"Začasna Excel datoteka ne obstaja: {temp_xlsx}")

    reports_dir = calculation.project.path / "reports" / calculation.module_id
    reports_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = reports_dir / f"{slugify(calculation.name)}.pdf"

    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except PermissionError:
            raise RuntimeError(
                f"PDF je že odprt ali zaklenjen: {pdf_path}. Zaprite ga in poskusite znova."
            )

    export_temp = TEMP_DIR / f"{slugify(calculation.name)}_{uuid4().hex}.xlsx"
    export_temp.parent.mkdir(parents=True, exist_ok=True)

    from shutil import copy2

    copy2(temp_xlsx, export_temp)

    try:
        script = f"""
On Error Resume Next
Set excelApp = GetObject(, "Excel.Application")
If Err.Number <> 0 Then
    Err.Clear
    Set excelApp = CreateObject("Excel.Application")
    createdNew = True
Else
    createdNew = False
End If

excelApp.Visible = False
excelApp.DisplayAlerts = False

foundWorkbook = False

For Each workbook In excelApp.Workbooks
    If LCase(workbook.FullName) = LCase("{_escape_vb_string(str(export_temp))}") Then
        workbook.ExportAsFixedFormat 0, "{_escape_vb_string(str(pdf_path))}"
        foundWorkbook = True
        Exit For
    End If
Next

If Not foundWorkbook Then
    Set workbook = excelApp.Workbooks.Open("{_escape_vb_string(str(export_temp))}")
    workbook.ExportAsFixedFormat 0, "{_escape_vb_string(str(pdf_path))}"
    workbook.Close False
End If

If createdNew Then
    excelApp.Quit
End If
"""
        _run_vbscript(script)
    finally:
        try:
            export_temp.unlink()
        except FileNotFoundError:
            pass

    if not pdf_path.exists():
        raise RuntimeError(f"PDF datoteka ni bila ustvarjena: {pdf_path}")

    return pdf_path


def export_calculation_pdf_from_saved(
    calculation: Calculation,
    module_key: str,
) -> Path:
    temp_xlsx = prepare_calculation_temp(calculation, module_key)

    try:
        return export_calculation_pdf(calculation, temp_xlsx)
    finally:
        try:
            temp_xlsx.unlink()
        except (FileNotFoundError, PermissionError):
            pass
