"""Arma el texto y el HTML de una carta a partir de los datos de una fila."""

from string import Template
import re

from pymail.campaign import Campaign


class UnfilledPlaceholder(ValueError):
    """La carta todavía tiene un $dato sin reemplazar."""


_LEFTOVER = re.compile(
    r"(?<!\$)\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)"
)


def header_parts(fields: dict) -> list[str]:
    parts = [
        (fields.get("name") or "").strip(),
        (fields.get("position") or "").strip(),
        (fields.get("afiliacion") or "").strip(),
    ]
    return [part for part in parts if part]


def build_header_block(fields: dict) -> str:
    parts = header_parts(fields)
    if not parts:
        return ""
    joined = "<br>\n      ".join(parts)
    return f"""
    <p>
      <em>{joined}</em>
    </p>"""


def build_header_text(fields: dict) -> str:
    parts = header_parts(fields)
    if not parts:
        return ""
    return "\n".join(parts)


def _fill(template: str, header: str) -> str:
    try:
        rendered = Template(template).substitute(header_block=header)
    except KeyError as exc:
        missing = exc.args[0] if exc.args else "desconocido"
        raise UnfilledPlaceholder(f"Falta el dato ${missing}.") from exc
    leftover = _LEFTOVER.search(rendered)
    if leftover:
        raise UnfilledPlaceholder(f"Quedó sin llenar {leftover.group(0)}.")
    return rendered


def render_message(campaign: Campaign, fields: dict) -> tuple[str, str]:
    html = _fill(campaign.body_html, build_header_block(fields))
    text = _fill(campaign.body_txt, build_header_text(fields))
    return html, text
