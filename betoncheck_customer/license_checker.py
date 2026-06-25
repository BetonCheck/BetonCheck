from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .settings import LICENSE_URL, PUBLIC_KEY_PATH, LOCAL_LICENSE_KEY_PATH


@dataclass
class LicenseResult:
    valid: bool
    message: str
    key: str | None = None
    customer: str | None = None
    valid_until: str | None = None
    modules: list[str] | None = None


def save_license_key(key: str) -> None:
    LOCAL_LICENSE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_LICENSE_KEY_PATH.write_text(key.strip(), encoding="utf-8")


def load_license_key() -> str | None:
    if LOCAL_LICENSE_KEY_PATH.exists():
        return LOCAL_LICENSE_KEY_PATH.read_text(encoding="utf-8").strip()
    return None


def fetch_signed_licenses() -> dict:
    response = requests.get(LICENSE_URL, timeout=15)
    response.raise_for_status()
    return response.json()


def verify_and_decode(signed: dict) -> dict:
    payload_b64 = signed["payload_b64"]
    signature_b64 = signed["signature_b64"]
    payload = base64.b64decode(payload_b64)
    signature = base64.b64decode(signature_b64)

    public_key = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
    public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
    return json.loads(payload.decode("utf-8"))


def check_license(key: str | None = None) -> LicenseResult:
    key = key or load_license_key()
    if not key:
        return LicenseResult(False, "Licencni kljuc ni vpisan.")

    try:
        payload = verify_and_decode(fetch_signed_licenses())
    except Exception as exc:
        return LicenseResult(False, f"Licence ni bilo mogoce preveriti: {exc}")

    for lic in payload.get("licenses", []):
        if lic.get("key") != key:
            continue
        if lic.get("status") != "active":
            return LicenseResult(False, "Licenca ni aktivna.")
        valid_until = lic.get("valid_until")
        try:
            until = date.fromisoformat(valid_until)
        except Exception:
            return LicenseResult(False, "Datum veljavnosti licence ni pravilen.")
        if date.today() > until:
            return LicenseResult(False, f"Licenca je potekla dne {valid_until}.")
        save_license_key(key)
        return LicenseResult(True, "Licenca je veljavna.", key, lic.get("customer"), valid_until, lic.get("modules", []))

    return LicenseResult(False, "Licencni kljuc ne obstaja.")
