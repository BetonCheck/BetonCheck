from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .crypto_vault import decrypt_file
from .settings import APP_SECRET, TEMP_DIR


def open_encrypted_excel(encrypted_path: Path) -> None:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_xlsx = TEMP_DIR / encrypted_path.name.replace(".bckx", ".xlsx")
    decrypt_file(encrypted_path, temp_xlsx, APP_SECRET)

    if os.name == "nt":
        os.startfile(str(temp_xlsx))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(temp_xlsx)])

    # Datoteke ni mogoce zanesljivo izbrisati, dokler je odprta v Excelu.
    # Ob naslednjih zagonih lahko temp mapo ocistis ali uporabis background cleanup.
    time.sleep(1)
