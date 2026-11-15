"""Carga una carpeta de campaña: campaign.toml y la carta."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


BODY_FORMATS = ("txt", "html")


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
        sheet_id=str(data["sheet_id"]),
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
