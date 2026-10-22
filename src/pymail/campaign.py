"""Carga una carpeta de campaña: campaign.toml, body.html y body.txt."""

from dataclasses import dataclass
from pathlib import Path
import tomllib


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
    body_html: str
    body_txt: str
    directory: Path


def load_campaign(path: str | Path) -> Campaign:
    directory = Path(path)
    toml_path = directory / "campaign.toml"
    with toml_path.open("rb") as handle:
        data = tomllib.load(handle)

    columns = dict(data.get("columns") or {})
    cc_columns = tuple(str(name) for name in (data.get("cc_columns") or []))
    return Campaign(
        id=str(data["id"]),
        subject=str(data["subject"]),
        sheet_id=str(data["sheet_id"]),
        sheet_name=str(data["sheet_name"]),
        email_column=str(data["email_column"]),
        delay_seconds=float(data.get("delay_seconds", 2)),
        cc_columns=cc_columns,
        columns=columns,
        body_html=(directory / "body.html").read_text(encoding="utf-8"),
        body_txt=(directory / "body.txt").read_text(encoding="utf-8"),
        directory=directory,
    )


def project_root_for(campaign_dir: Path) -> Path:
    start = campaign_dir.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return start.parent
