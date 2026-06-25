from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def decrypt_file(
    source: Path,
    target: Path,
    module_key: str | bytes,
) -> None:

    target.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(module_key, str):
        module_key = module_key.encode("utf-8")

    try:
        fernet = Fernet(module_key)
        decrypted = fernet.decrypt(source.read_bytes())

    except InvalidToken as exc:
        raise RuntimeError(
            "Nepravilen ključ za modul ali poškodovana .bckx datoteka."
        ) from exc

    target.write_bytes(decrypted)