from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .crypto_vault import decrypt_file, encrypt_file
from .module_manager import ModuleItem
from .settings import PROJECTS_DIR, TEMP_DIR

NUMBER_PREFIX_RE = re.compile(r"^\s*(\d+)(?:\.(\d+))?\s+-\s+")


@dataclass
class Project:
    name: str
    path: Path


@dataclass
class Calculation:
    project: Project
    name: str
    path: Path
    module_id: str
    module_title: str
    item_id: str
    title: str


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s-]+", "_", text)
    return text or "calculation"


def create_project(name: str) -> Project:
    name = name.strip()

    if not name:
        raise ValueError("Ime projekta ne sme biti prazno.")

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    project_name = slugify(name)
    project_path = PROJECTS_DIR / project_name

    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "calculations").mkdir(exist_ok=True)
    (project_path / "reports").mkdir(exist_ok=True)

    metadata = {
        "name": name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "version": 1,
    }

    (project_path / "project.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return Project(name=name, path=project_path)


def open_project(path: Path) -> Project:
    project_file = path / "project.json"

    if not project_file.exists():
        raise FileNotFoundError("Izbrana mapa ni BetonCheck projekt.")

    data = json.loads(project_file.read_text(encoding="utf-8"))

    return Project(
        name=data.get("name", path.name),
        path=path,
    )


def list_calculations(project: Project) -> list[Calculation]:
    calculations_dir = project.path / "calculations"

    if not calculations_dir.exists():
        return []

    result: list[Calculation] = []

    for calc_dir in sorted(p for p in calculations_dir.iterdir() if p.is_dir()):
        metadata_file = calc_dir / "metadata.json"

        if not metadata_file.exists():
            continue

        data = json.loads(metadata_file.read_text(encoding="utf-8"))

        result.append(
            Calculation(
                project=project,
                name=data.get("name", calc_dir.name),
                path=calc_dir,
                module_id=data["module_id"],
                module_title=data.get("module_title", data["module_id"]),
                item_id=data["item_id"],
                title=data.get("title", calc_dir.name),
            )
        )

    return sorted(result, key=calculation_sort_key)


def calculation_sort_key(calculation: Calculation) -> tuple[str, str, str, int, int, str]:
    major, minor = parse_calculation_number(calculation.name)

    return (
        calculation.module_title.casefold(),
        calculation.module_id.casefold(),
        calculation.title.casefold(),
        major or 999999,
        minor or 999999,
        calculation.name.casefold(),
    )


def parse_calculation_number(name: str) -> tuple[int | None, int | None]:
    match = NUMBER_PREFIX_RE.match(name)
    if match is None:
        return None, None

    major = int(match.group(1))
    minor_text = match.group(2)
    minor = int(minor_text) if minor_text is not None else None

    return major, minor


def generate_calculation_name(project: Project, item: ModuleItem) -> str:
    calculations = list_calculations(project)
    existing_same_item = [
        calc
        for calc in calculations
        if calc.item_id == item.item_id
    ]

    existing_group_numbers = [
        major
        for major, _minor in (
            parse_calculation_number(calc.name)
            for calc in existing_same_item
        )
        if major is not None
    ]

    if existing_group_numbers:
        group_number = min(existing_group_numbers)
    else:
        used_group_numbers = [
            major
            for major, _minor in (
                parse_calculation_number(calc.name)
                for calc in calculations
            )
            if major is not None
        ]
        group_number = max(used_group_numbers, default=0) + 1

    item_number = len(existing_same_item) + 1

    return f"{group_number}.{item_number} - {item.title}"


def create_calculation_from_template(
    project: Project,
    item: ModuleItem,
    encrypted_template_path: Path,
    module_key: str,
    calculation_name: str,
) -> Calculation:
    calc_id = slugify(calculation_name)
    calc_dir = project.path / "calculations" / calc_id
    calc_dir.mkdir(parents=True, exist_ok=True)

    template_file = calc_dir / "template.bckwork"
    work_file = calc_dir / "calculation.bckwork"
    metadata_file = calc_dir / "metadata.json"
    reports_dir = calc_dir / "reports"

    reports_dir.mkdir(exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(encrypted_template_path, template_file)

    temp_xlsx = TEMP_DIR / f"{calc_id}_template.xlsx"

    decrypt_file(template_file, temp_xlsx, module_key)
    encrypt_file(temp_xlsx, work_file, module_key)

    try:
        temp_xlsx.unlink()
    except FileNotFoundError:
        pass

    metadata = {
        "name": calculation_name,
        "module_id": item.module_id,
        "module_title": item.module_title,
        "item_id": item.item_id,
        "title": item.title,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "work_file": "calculation.bckwork",
        "template_file": "template.bckwork",
        "reports_dir": "reports",
    }

    metadata_file.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return Calculation(
        project=project,
        name=calculation_name,
        path=calc_dir,
        module_id=item.module_id,
        module_title=item.module_title,
        item_id=item.item_id,
        title=item.title,
    )


def reset_calculation(calculation: Calculation) -> None:
    metadata_file = calculation.path / "metadata.json"

    if not metadata_file.exists():
        raise FileNotFoundError("Manjka metadata datoteka za reset kontrole.")

    data = json.loads(metadata_file.read_text(encoding="utf-8"))

    template_file = calculation.path / data.get("template_file", "template.bckwork")
    work_file = calculation.path / data.get("work_file", "calculation.bckwork")

    if not template_file.exists():
        raise FileNotFoundError("Izvirna predloga za reset ni na voljo.")

    shutil.copy2(template_file, work_file)
    update_calculation_timestamp(calculation)


def rename_calculation(calculation: Calculation, new_name: str) -> None:
    new_name = new_name.strip()

    if not new_name:
        raise ValueError("Novo ime kontrole ne sme biti prazno.")

    metadata_file = calculation.path / "metadata.json"

    if not metadata_file.exists():
        raise FileNotFoundError("Manjka metadata datoteka za preimenovanje kontrole.")

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    data["name"] = new_name
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")

    metadata_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def delete_calculation(calculation: Calculation) -> None:
    if calculation.path.exists():
        shutil.rmtree(calculation.path)


def update_calculation_timestamp(calculation: Calculation) -> None:
    metadata_file = calculation.path / "metadata.json"

    if not metadata_file.exists():
        return

    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")

    metadata_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
