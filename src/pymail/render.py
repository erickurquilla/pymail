"""Arma el texto y el HTML de una carta a partir de los datos de una fila."""

from html import escape, unescape
from html.parser import HTMLParser
from string import Template
import re

from pymail.campaign import Campaign


class UnfilledPlaceholder(ValueError):
    """La carta todavía tiene un $dato sin reemplazar."""


_LEFTOVER = re.compile(
    r"(?<!\$)\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)"
)
# Un $$ escapado, o un $ que viene dentro del enlace, no se vuelve a leer
# como placeholder cuando después se inserta $header_block.
_DOLLAR = "\x00"
_HEADER_TOKEN = re.compile(r"\$\{header_block\}|\$header_block(?![A-Za-z0-9_])")
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
    joined = "<br>\n      ".join(_escape(part) for part in parts)
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


_BLOCKS = {"p", "div", "blockquote", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIPPED = {"script", "style", "head"}


def _same_link(visible: str, href: str) -> bool:
    text = visible.strip().rstrip("/")
    target = href.strip()
    if target.lower().startswith("mailto:"):
        address = target[7:].split("?", 1)[0]
        return text.casefold() == address.casefold()
    right = target.rstrip("/")
    if text == right:
        return True
    for prefix in ("https://", "http://"):
        if right.lower().startswith(prefix) and text == right[len(prefix) :]:
            return True
        if text.lower().startswith(prefix) and right == text[len(prefix) :].rstrip("/"):
            return True
    return False


def _format_link(visible: str, href: str) -> str:
    text = " ".join(visible.replace("\xa0", " ").split())
    target = href.strip()
    if not target:
        return text
    if _same_link(text, target):
        if target.lower().startswith("mailto:"):
            return text or target[7:].split("?", 1)[0]
        if text.lower().startswith(("http://", "https://")):
            return text
        if target.lower().startswith(("http://", "https://")):
            return target
        return text or target
    if not text:
        return target
    return f"{text} ({target})"


class _HTMLToText(HTMLParser):
    """Pasa el HTML de una carta a texto, sin tocar $header_block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._pending_space = False
        self._skip: list[str] = []
        self._pre = 0
        self._pre_leading = False
        self._href: str | None = None
        self._anchor: list[str] | None = None
        self._anchor_space = False
        self._seen_text = False
        self._keep_leading_space = False
        self._keep_trailing_space = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip:
            if tag in _SKIPPED:
                self._skip.append(tag)
            return
        if tag in _SKIPPED:
            self._skip.append(tag)
            return
        if tag == "pre":
            self._pre += 1
            self._pre_leading = True
            self._paragraph()
            return
        if tag == "br":
            self._hard_line()
            return
        if tag == "li":
            self._hard_line()
            self._add_text("- ")
            return
        if tag in _BLOCKS:
            self._paragraph()
        if tag in {"td", "th"}:
            self._mark_space()
            return
        if tag == "img":
            alt = unescape(dict(attrs).get("alt") or "")
            if alt.strip():
                self._add_text(alt)
            return
        if tag == "a" and self._anchor is None:
            self._href = unescape(dict(attrs).get("href") or "")
            self._anchor = []
            self._anchor_space = False

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if tag == "pre":
            if self._pre:
                self._pre -= 1
            self._pre_leading = False
            self._paragraph()
            return
        if tag == "a" and self._anchor is not None:
            visible = "".join(self._anchor)
            href = self._href or ""
            self._anchor = None
            self._href = None
            self._append_token(_format_link(visible, href))
            return
        if tag in _BLOCKS:
            self._paragraph()

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        if self._anchor is not None:
            self._anchor_text(data)
            return
        if self._pre:
            text = data.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
            if self._pre_leading and text.startswith("\n"):
                text = text[1:]
            self._pre_leading = False
            self._add_raw(text)
            return
        self._add_text(data)

    def handle_comment(self, data: str) -> None:
        return

    def result(self) -> str:
        text = "".join(self.parts)
        if self._keep_leading_space:
            text = text.lstrip("\n")
        else:
            text = text.lstrip("\n").lstrip(" ")
        if self._keep_trailing_space:
            text = text.rstrip("\n")
        else:
            text = text.rstrip("\n").rstrip(" ")
        return text

    def _mark_space(self) -> None:
        if self._anchor is not None:
            if self._anchor:
                self._anchor_space = True
            return
        if self.parts and not self._ends_with_newline():
            self._pending_space = True

    def _paragraph(self) -> None:
        if self._anchor is not None:
            self._mark_space()
            return
        self._ensure_newlines(2)

    def _hard_line(self) -> None:
        if self._anchor is not None:
            self._mark_space()
            return
        if self._pre:
            self._add_raw("\n")
            return
        self._pending_space = False
        if self.parts and self._trailing_newlines() < 2:
            self.parts.append("\n")

    def _ensure_newlines(self, count: int) -> None:
        self._pending_space = False
        if not self.parts:
            return
        missing = count - self._trailing_newlines()
        if missing > 0:
            self.parts.append("\n" * missing)

    def _trailing_newlines(self) -> int:
        count = 0
        for chunk in reversed(self.parts):
            for char in reversed(chunk):
                if char != "\n":
                    return count
                count += 1
        return count

    def _ends_with_newline(self) -> bool:
        for chunk in reversed(self.parts):
            if chunk:
                return chunk.endswith("\n")
        return False

    def _add_raw(self, text: str) -> None:
        if not text:
            return
        if not self._seen_text:
            self._keep_leading_space = True
        self._keep_trailing_space = True
        self._seen_text = True
        self._pending_space = False
        self.parts.append(text)

    def _add_text(self, text: str) -> None:
        cleaned = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
        if not cleaned:
            return
        if cleaned.strip() == "":
            self._mark_space()
            return
        if cleaned[0].isspace():
            self._mark_space()
        for index, token in enumerate(cleaned.split()):
            if index:
                self._pending_space = True
            self._append_token(token)
        if cleaned[-1].isspace():
            self._pending_space = True

    def _append_token(self, token: str) -> None:
        if not token:
            return
        if self.parts and self._pending_space and not self._ends_with_newline():
            self.parts.append(" ")
        self._pending_space = False
        if not self._seen_text:
            self._keep_leading_space = False
        self._keep_trailing_space = False
        self._seen_text = True
        self.parts.append(token)

    def _anchor_text(self, text: str) -> None:
        anchor = self._anchor
        if anchor is None:
            return
        cleaned = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
        if not cleaned:
            return
        if cleaned.strip() == "":
            if anchor:
                self._anchor_space = True
            return
        if cleaned[0].isspace() and anchor:
            self._anchor_space = True
        for index, token in enumerate(cleaned.split()):
            if index:
                self._anchor_space = True
            if anchor and self._anchor_space:
                anchor.append(" ")
            anchor.append(token)
            self._anchor_space = False
        if cleaned[-1].isspace() and anchor:
            self._anchor_space = True


def html_to_text(body_html: str) -> str:
    """Convierte el HTML de la carta en texto, dejando $header_block intacto."""
    parser = _HTMLToText()
    parser.feed(body_html)
    parser.close()
    return parser.result()


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


def _apply_links(
    template: str,
    links: dict[str, str],
    allowed: tuple[str, ...],
    *,
    html: bool,
) -> str:
    """Sustituye $enlaces y deja $header_block para el paso siguiente."""
    known = set(allowed)

    def convert(match: re.Match) -> str:
        name = match.group("named") or match.group("braced")
        if match.group("escaped") is not None:
            return _DOLLAR
        if name is None:
            raise ValueError(f"Invalid placeholder in string: {match.group(0)!r}")
        if name == "header_block":
            return match.group(0)
        if name not in known:
            raise UnfilledPlaceholder(f"Falta el dato ${name}.")
        value = str(links.get(name, "")).strip()
        if not value:
            raise UnfilledPlaceholder(f"El dato ${name} está vacío.")
        if html:
            value = escape(value, quote=True)
        return value.replace("$", _DOLLAR)

    return Template.pattern.sub(convert, template)


def _finish(template: str, header: str) -> str:
    leftover = _LEFTOVER.search(header)
    if leftover:
        raise UnfilledPlaceholder(f"Quedó sin llenar {leftover.group(0)}.")
    rendered = _HEADER_TOKEN.sub(lambda _match: header, template)
    return rendered.replace(_DOLLAR, "$")


def _render_linked(campaign: Campaign, fields: dict, links: dict[str, str]) -> tuple[str, str]:
    allowed = campaign.link_columns
    if campaign.body_format == "html":
        html_template = _apply_links(campaign.body, links, allowed, html=True)
        text_template = _apply_links(
            html_to_text(campaign.body), links, allowed, html=False
        )
    elif campaign.body_format == "txt":
        linked = _apply_links(campaign.body, links, allowed, html=False)
        html_template = text_to_html(linked)
        text_template = linked
    else:
        raise ValueError(
            f'body_format debe ser "txt" o "html", no {campaign.body_format!r}.'
        )
    html = _finish(html_template, build_header_block(fields))
    text = _finish(text_template, build_header_text(fields))
    return html, text


def render_message(
    campaign: Campaign,
    fields: dict,
    links: dict[str, str] | None = None,
) -> tuple[str, str]:
    if campaign.link_columns:
        return _render_linked(campaign, fields, links or {})
    if campaign.body_format == "html":
        html_template = campaign.body
        text_template = html_to_text(campaign.body)
    elif campaign.body_format == "txt":
        html_template = text_to_html(campaign.body)
        text_template = campaign.body
    else:
        raise ValueError(
            f'body_format debe ser "txt" o "html", no {campaign.body_format!r}.'
        )
    html = _fill(html_template, build_header_block(fields))
    text = _fill(text_template, build_header_text(fields))
    return html, text
