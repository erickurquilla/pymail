"""Lee destinatarios desde un CSV local o la exportación pública de Google Sheets."""

from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
import csv
import io
import re

from pymail.campaign import Campaign


_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Recipient:
    email: str
    fields: dict[str, str]
    cc: tuple[str, ...] = ()


@dataclass
class RecipientReport:
    recipients: list[Recipient] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    invalid_cc: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    blank_count: int = 0


def gviz_csv_url(sheet_id: str, sheet_name: str) -> str:
    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{sheet_id}/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
    )


def is_valid_email(value: str) -> bool:
    _, address = parseaddr(value.strip())
    if not address or "@" not in address:
        return False
    if not _ADDRESS.fullmatch(address):
        return False
    domain = address.split("@", 1)[1]
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


def load_recipients(campaign: Campaign, csv_path: Path | None = None) -> RecipientReport:
    if csv_path is not None:
        text = Path(csv_path).read_text(encoding="utf-8-sig")
    else:
        url = gviz_csv_url(campaign.sheet_id, campaign.sheet_name)
        with urlopen(url, timeout=30) as response:
            text = response.read().decode("utf-8-sig")
    return parse_recipients(text, campaign)


def parse_recipients(csv_text: str, campaign: Campaign) -> RecipientReport:
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or campaign.email_column not in reader.fieldnames:
        raise ValueError(
            f"La hoja no tiene la columna obligatoria {campaign.email_column!r}."
        )
    missing_cc = [name for name in campaign.cc_columns if name not in reader.fieldnames]
    if missing_cc:
        names = ", ".join(repr(name) for name in missing_cc)
        raise ValueError(f"La hoja no tiene la columna de copia {names}.")

    report = RecipientReport()
    seen: set[str] = set()
    for row in reader:
        raw = (row.get(campaign.email_column) or "").strip()
        if not raw:
            report.blank_count += 1
            continue
        key = raw.casefold()
        if key in seen:
            report.duplicates.append(raw)
            continue
        seen.add(key)
        if not is_valid_email(raw):
            report.invalid.append(raw)
            continue
        fields = {
            logical: (row.get(column) or "").strip()
            for logical, column in campaign.columns.items()
        }
        report.recipients.append(
            Recipient(email=raw, fields=fields, cc=_cc_addresses(row, campaign, report))
        )
    return report


def _cc_addresses(row: dict, campaign: Campaign, report: RecipientReport) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    for column in campaign.cc_columns:
        cell = row.get(column) or ""
        for piece in re.split(r"[,;]", cell):
            address = piece.strip()
            if not address:
                continue
            if not is_valid_email(address):
                report.invalid_cc.append(address)
                continue
            key = address.casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(address)
    return tuple(found)
