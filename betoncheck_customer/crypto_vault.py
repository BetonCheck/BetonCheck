from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet


def derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def decrypt_file(source: Path, target: Path, secret: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fernet = Fernet(derive_fernet_key(secret))
    target.write_bytes(fernet.decrypt(source.read_bytes()))
