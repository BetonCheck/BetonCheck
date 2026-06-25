from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .crypto_vault import decrypt_file
from .settings import TEMP_DIR


def open_encrypted_excel(encrypted_path: Path, module_key: str) -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    temp_xlsx = TEMP_DIR / encrypted_path.name.replace(".bckx", ".xlsx")

    try:
        decrypt_file(encrypted_path, temp_xlsx, module_key)
    except Exception as exc:
        raise RuntimeError(
            "Datoteke ni bilo mogoče dešifrirati. "
            "Licenca ne vsebuje pravilnega ključa za ta modul."
        ) from exc

    if os.name == "nt":
        os.startfile(str(temp_xlsx))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(temp_xlsx)])

    time.sleep(1)