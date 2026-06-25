from __future__ import annotations

import json
from .settings import SETTINGS_PATH

EULA_VERSION = "1.0"


def has_accepted_eula() -> bool:
    if not SETTINGS_PATH.exists():
        return False
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("license_accepted") is True and data.get("accepted_version") == EULA_VERSION
    except Exception:
        return False


def accept_eula() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["license_accepted"] = True
    data["accepted_version"] = EULA_VERSION
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
