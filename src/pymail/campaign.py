"""Carga una carpeta de campaña: campaign.toml y la carta."""

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib


BODY_FORMATS = ("txt", "html")
_SHEET_IN_URL = re.compile(
    r"spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9-_]+)",
    re.IGNORECASE,
)
_PUBLISHED_SHEET = re.compile(
    r"spreadsheets/(?:u/\d+/)?d/e/",
    re.IGNORECASE,
)
_SHEET_ID_ERROR = (
    "No se pudo leer el id de la hoja. Pega el enlace para editar o solo el id."
)


@dataclass(frozen=True)
class Campaign:
    id: str
    subject: str
    sheet_id: str
    sheet_name: str
    email_column: str
    delay_seconds: float
    cc_columns: tuple[str, ...]
    columns: dict[str, str]
    body_format: str
    body: str
    directory: Path


def sheet_id_from(value: str) -> str:
    """Devuelve el id de la hoja, venga solo o dentro de un enlace de Google."""
    text = value.strip()
    lowered = text.lower()
    looks_like_link = (
        lowered.startswith(("http://", "https://")) or "docs.google.com" in lowered
    )
    if not looks_like_link:
        return text
    if _PUBLISHED_SHEET.search(text):
        raise ValueError(_SHEET_ID_ERROR)
    match = _SHEET_IN_URL.search(text)
    if match is None:
        raise ValueError(_SHEET_ID_ERROR)
    return match.group(1)


def load_campaign(path: str | Path) -> Campaign:
    directory = Path(path)
    toml_path = directory / "campaign.toml"
    with toml_path.open("rb") as handle:
        data = tomllib.load(handle)

    columns = dict(data.get("columns") or {})
    cc_columns = tuple(str(name) for name in (data.get("cc_columns") or []))
    body_format = str(data.get("body_format", "txt"))
    if body_format not in BODY_FORMATS:
        allowed = " o ".join(f'"{name}"' for name in BODY_FORMATS)
        raise ValueError(f"body_format debe ser {allowed}, no {body_format!r}.")
    body_path = directory / f"body.{body_format}"
    if not body_path.is_file():
        raise ValueError(f"No está el archivo {body_path.name}.")
    return Campaign(
        id=str(data["id"]),
        subject=str(data["subject"]),
        sheet_id=sheet_id_from(str(data["sheet_id"])),
        sheet_name=str(data["sheet_name"]),
        email_column=str(data["email_column"]),
        delay_seconds=float(data.get("delay_seconds", 2)),
        cc_columns=cc_columns,
        columns=columns,
        body_format=body_format,
        body=body_path.read_text(encoding="utf-8"),
        directory=directory,
    )


def project_root_for(campaign_dir: Path) -> Path:
    start = campaign_dir.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return start.parent
