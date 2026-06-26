from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def encrypt_file(
    source: Path,
    target: Path,
    module_key: str | bytes,
) -> None:
    """
    Šifrira datoteko (.xlsx -> .bckx ali .bckwork).
    """

    target.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(module_key, str):
        module_key = module_key.encode("utf-8")

    fernet = Fernet(module_key)

    encrypted = fernet.encrypt(source.read_bytes())

    target.write_bytes(encrypted)


def decrypt_file(
    source: Path,
    target: Path,
    module_key: str | bytes,
) -> None:
    """
    Dešifrira datoteko (.bckx ali .bckwork -> .xlsx).
    """

    target.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(module_key, str):
        module_key = module_key.encode("utf-8")

    try:
        fernet = Fernet(module_key)

        decrypted = fernet.decrypt(source.read_bytes())

    except InvalidToken as exc:
        raise RuntimeError(
            "Nepravilen ključ za modul ali poškodovana datoteka."
        ) from exc

    target.write_bytes(decrypted)