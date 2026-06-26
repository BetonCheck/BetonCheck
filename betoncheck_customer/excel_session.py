from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .crypto_vault import decrypt_file, encrypt_file
from .project_manager import Calculation, update_calculation_timestamp
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

    temp_xlsx = TEMP_DIR / f"{calculation.path.name}.xlsx"

    decrypt_file(work_file, temp_xlsx, module_key)

    return temp_xlsx


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

    encrypt_file(temp_xlsx, work_file, module_key)
    update_calculation_timestamp(calculation)

    try:
        temp_xlsx.unlink()
    except FileNotFoundError:
        pass


def open_calculation_session(
    calculation: Calculation,
    module_key: str,
) -> Path:
    temp_xlsx = prepare_calculation_temp(calculation, module_key)
    open_file(temp_xlsx)
    return temp_xlsx


def export_pdf_placeholder(
    calculation: Calculation,
) -> Path:
    reports_dir = calculation.path / "reports"
    reports_dir.mkdir(exist_ok=True)

    pdf_path = reports_dir / f"{calculation.path.name}.pdf"

    raise NotImplementedError(
        "PDF export bo dodan v naslednjem koraku. "
        f"Predvidena pot: {pdf_path}"
    )