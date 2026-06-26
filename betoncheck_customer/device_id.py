from __future__ import annotations

import hashlib
import os
import platform
import uuid


def get_device_id_hash() -> str:
    identifier = _get_stable_device_identifier()
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


def get_device_name() -> str:
    return os.environ.get("COMPUTERNAME") or platform.node() or "Unknown device"


def _get_stable_device_identifier() -> str:
    machine_guid = _get_windows_machine_guid()
    if machine_guid:
        return f"windows-machine-guid:{machine_guid}"

    node = uuid.getnode()
    if node:
        return f"uuid-node:{node}"

    return f"platform-node:{platform.node() or 'unknown'}"


def _get_windows_machine_guid() -> str | None:
    if os.name != "nt":
        return None

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, "MachineGuid")
            if isinstance(value, str) and value.strip():
                return value.strip()
    except OSError:
        return None

    return None
