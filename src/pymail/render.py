"""Arma el texto y el HTML de una carta a partir de los datos de una fila."""

from string import Template
import re

from pymail.campaign import Campaign


class UnfilledPlaceholder(ValueError):
    """La carta todavía tiene un $dato sin reemplazar."""


_LEFTOVER = re.compile(
    r"(?<!\$)\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)"
)
_LINK = re.compile(
    r"https?://[^\s<>]+"
    r"|"
    r"(?<![A-Za-z0-9@./-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9/])",
    re.IGNORECASE,
)
_PARAGRAPHS = re.compile(r"(?:\n[ \t]*){2,}")


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


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _trim_url(url: str) -> tuple[str, str]:
    trimmed = url
    while trimmed and trimmed[-1] in ".,;:!?":
        trimmed = trimmed[:-1]
    if trimmed.endswith(")") and trimmed.count("(") < trimmed.count(")"):
        trimmed = trimmed[:-1]
    return trimmed, url[len(trimmed) :]


def _linkify(line: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in _LINK.finditer(line):
        pieces.append(_escape(line[cursor : match.start()]))
        raw = match.group(0)
        if raw.lower().startswith(("http://", "https://")):
            target, rest = _trim_url(raw)
            href = target
        else:
            target, rest = raw, ""
            href = f"https://{target}"
        pieces.append(f'<a href="{_escape(href)}">{_escape(target)}</a>')
        pieces.append(_escape(rest))
        cursor = match.end()
    pieces.append(_escape(line[cursor:]))
    return "".join(pieces)


def text_to_html(body_txt: str) -> str:
    """Convierte el texto de la carta en HTML simple, dejando $header_block intacto."""
    normalized = body_txt.replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks: list[str] = []
    for paragraph in _PARAGRAPHS.split(normalized):
        if paragraph.strip() == "$header_block":
            chunks.append("$header_block")
            continue
        if not paragraph.strip():
            continue
        lines = [_linkify(line) for line in paragraph.split("\n")]
        chunks.append("<p>" + "<br>\n".join(lines) + "</p>")
    body = "\n\n".join(chunks)
    return f"<html>\n<body>\n{body}\n</body>\n</html>\n"


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
    html = _fill(text_to_html(campaign.body_txt), build_header_block(fields))
    text = _fill(campaign.body_txt, build_header_text(fields))
    return html, text
