from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding


def decrypt_module_key(
    encrypted_key_b64: str,
    launcher_private_key_path: Path,
) -> str:
    private_key = serialization.load_pem_private_key(
        launcher_private_key_path.read_bytes(),
        password=None,
    )

    encrypted = base64.b64decode(encrypted_key_b64)

    module_key = private_key.decrypt(
        encrypted,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    return module_key.decode("utf-8")