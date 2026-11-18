"""Pruebas sin red y sin SMTP real."""

from dataclasses import replace
from pathlib import Path
import os
import sys

from pymail.campaign import load_campaign, sheet_id_from
from pymail.cli import ADDRESS_PROMPT, PASSWORD_PROMPT, main
from pymail.ledger import Ledger
from pymail.recipients import Recipient, parse_recipients
from pymail.render import UnfilledPlaceholder, html_to_text, render_message, text_to_html
from pymail.smtp_sender import deliver

import pytest


CAMPAIGN = Path("campaigns/example")

SAMPLE_CSV = """\
Email,Nombre,Carrera,Institucion,cced1,cced2,link1,link2
ana@example.com,Ana,Física,UES,,,https://example.com,https://example.com/two
ana@example.com,Ana Otra,Química,UCA,,,https://example.com/otra,https://example.com/two
bad-email,Beto,Bio,UES,,,https://example.com/beto,https://example.com/two
,Sin correo,Mate,UES,,,https://example.com/mate,https://example.com/two
"""


class FakeSMTP:
    def __init__(self):
        self.sent = []
        self.logged_in = None

    def ehlo(self):
        return None

    def starttls(self):
        return None

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent.append(message)

    def quit(self):
        return None


def _csv(tmp_path: Path) -> Path:
    path = tmp_path / "people.csv"
    path.write_text(SAMPLE_CSV, encoding="utf-8")
    return path


def test_header_omitted_when_empty():
    campaign = load_campaign(CAMPAIGN)
    links = {"link1": "https://example.com"}
    html, text = render_message(
        campaign, {"name": "", "position": " ", "afiliacion": None}, links
    )
    assert "<em>" not in html
    assert "$header_block" not in html
    assert "$header_block" not in text
    assert "$link1" not in html
    assert 'href="https://example.com"' in html

    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}, links
    )
    assert "<em>Ana<br>" in html
    assert "Ana\nFísica\nUES" in text


def test_unfilled_placeholder_refused():
    campaign = load_campaign(CAMPAIGN)
    broken = replace(campaign, body_format="txt", body="Hola $nombre\n$header_block")
    with pytest.raises(UnfilledPlaceholder):
        render_message(broken, {"name": "Ana", "position": "", "afiliacion": ""})


def test_text_to_html_builds_basic_letter():
    html = text_to_html(
        "Hola,\n\n"
        "$header_block\n\n"
        "Physics & Astronomy <lab>\n"
        "Completa la encuesta aquí: https://forms.gle/abc\n"
        "Fecha límite: 29 de octubre de 2026\n\n"
        "Co-founder inspirastem.com\n"
        "ana@example.com\n"
    )

    assert html.startswith("<html>\n<body>\n")
    assert html.endswith("</body>\n</html>\n")
    assert "<p>Hola,</p>" in html
    assert "$header_block" in html
    assert "<p>$header_block</p>" not in html
    assert "Physics &amp; Astronomy &lt;lab&gt;" in html
    assert '<a href="https://forms.gle/abc">https://forms.gle/abc</a>' in html
    assert "Fecha límite: 29 de octubre de 2026" in html
    assert "<br>\n" in html
    assert '<a href="https://inspirastem.com">inspirastem.com</a>' in html
    assert "ana@example.com" in html
    assert 'href="https://example.com"' not in html


def test_generated_html_keeps_italic_header():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="txt",
        body="Hola,\n\n$header_block\n\nAdiós\n",
    )
    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    )

    assert "<p>Hola,</p>" in html
    assert "<em>Ana<br>" in html
    assert "<p>Adiós</p>" in html
    assert "$header_block" not in html
    assert "Hola,\n\nAna\nFísica\nUES\n\nAdiós" in text


def _campaign_dir(
    tmp_path,
    *,
    body_format=None,
    body=None,
    sheet_id="x",
    cc_columns=None,
    link_columns=None,
):
    directory = tmp_path / "camp"
    directory.mkdir()
    lines = [
        'id = "camp"',
        'subject = "Hola"',
        f'sheet_id = "{sheet_id}"',
        'sheet_name = "Sheet1"',
        'email_column = "Email"',
    ]
    if body_format is not None:
        lines.append(f'body_format = "{body_format}"')
    if cc_columns is not None:
        lines.append(f"cc_columns = {cc_columns}")
    if link_columns is not None:
        lines.append(f"link_columns = {link_columns}")
    lines.extend(
        [
            "",
            "[columns]",
            'name = "Nombre"',
            'position = "Carrera"',
            'afiliacion = "Institucion"',
            "",
        ]
    )
    (directory / "campaign.toml").write_text("\n".join(lines), encoding="utf-8")
    if body is not None:
        (directory / f"body.{body_format or 'txt'}").write_text(body, encoding="utf-8")
    return directory


def test_example_campaign_loads_html():
    campaign = load_campaign(CAMPAIGN)
    assert campaign.body_format == "html"
    assert campaign.body == (CAMPAIGN / "body.html").read_text(encoding="utf-8")


_SHEET = "1DMcbmrzLUTErmQ53HEFMDUAiebcypitCwC_hgX08eK0"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example-sheet-id", "example-sheet-id"),
        ("x", "x"),
        (f"  {_SHEET}  ", _SHEET),
        (
            f"https://docs.google.com/spreadsheets/d/{_SHEET}/edit?usp=sharing",
            _SHEET,
        ),
        (f"https://docs.google.com/spreadsheets/d/{_SHEET}/edit#gid=0", _SHEET),
        (f"https://docs.google.com/spreadsheets/u/0/d/{_SHEET}/edit", _SHEET),
        (f"docs.google.com/spreadsheets/d/{_SHEET}/edit", _SHEET),
    ],
)
def test_sheet_id_accepts_link_or_bare_id(value, expected):
    assert sheet_id_from(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        f"https://docs.google.com/spreadsheets/d/e/2PACX-{_SHEET}/pubhtml",
        "https://example.com/not-a-sheet",
        "https://docs.google.com/document/d/abc",
    ],
)
def test_sheet_id_rejects_unusable_link(value):
    with pytest.raises(ValueError, match="enlace para editar"):
        sheet_id_from(value)


def test_load_campaign_stores_sheet_id_from_url(tmp_path):
    url = f"https://docs.google.com/spreadsheets/d/{_SHEET}/edit?usp=sharing#gid=0"
    directory = _campaign_dir(tmp_path, body="Hola\n", sheet_id=url)
    campaign = load_campaign(directory)
    assert campaign.sheet_id == _SHEET


def test_omitted_format_reads_txt_and_ignores_html(tmp_path):
    directory = _campaign_dir(tmp_path, body="Carta\n")
    (directory / "body.html").write_text("<p>otra</p>\n", encoding="utf-8")
    campaign = load_campaign(directory)
    assert campaign.body_format == "txt"
    assert campaign.body == "Carta\n"


def test_load_html_template(tmp_path):
    directory = _campaign_dir(tmp_path, body_format="html", body="<p>Hola</p>\n")
    campaign = load_campaign(directory)
    assert campaign.body_format == "html"
    assert campaign.body == "<p>Hola</p>\n"


def test_body_format_rejected(tmp_path):
    directory = _campaign_dir(tmp_path, body_format="markdown", body="Hola\n")
    with pytest.raises(ValueError, match='"txt" o "html"'):
        load_campaign(directory)


@pytest.mark.parametrize("fmt", ["txt", "html"])
def test_missing_body_file(tmp_path, fmt):
    directory = _campaign_dir(tmp_path, body_format=fmt)
    with pytest.raises(ValueError, match=f"No está el archivo body.{fmt}."):
        load_campaign(directory)


def test_text_to_html_escapes_query_ampersand():
    html = text_to_html("Ver https://example.com?a=1&b=2 ahora")
    assert '<a href="https://example.com?a=1&amp;b=2">' in html
    assert "https://example.com?a=1&amp;b=2</a>" in html
    assert "&amp;amp;" not in html


def test_html_to_text_keeps_structure():
    text = html_to_text(
        "<html><head><title>OCULTO</title><style>p { color: red }</style></head>"
        "<body>"
        "<p>Hola,</p>"
        "$header_block"
        "<h1>Título</h1>"
        "<p>Physics &amp; Astronomy &#243;<br>Fecha l&iacute;mite A&nbsp;B</p>"
        "<blockquote>Cita</blockquote>"
        "<div>Bloque</div>"
        '<p>Enlace: <a href="https://example.com">https://example.com</a></p>'
        '<p>Formulario: <a href="https://forms.gle/abc">la encuesta</a></p>'
        '<p>Correo: <a href="mailto:ana@example.com">ana@example.com</a></p>'
        "<ul><li>Uno</li><li>Dos</li></ul>"
        "<table><tr><td>Celda</td><td>Otra</td></tr></table>"
        "<pre>  a  b\nc</pre>"
        "<script>alert('secreto')</script>"
        '<p><img alt="Marca" src="x.png"></p>'
        "<!-- comentario -->"
        "</body></html>"
    )

    assert html_to_text("<pre>  a  b\nc</pre>") == "  a  b\nc"
    assert html_to_text("<p>Uno<br><br>Dos</p>") == "Uno\n\nDos"
    assert html_to_text("<p>Uno<br><br><br>Dos</p>") == "Uno\n\nDos"
    assert "$header_block" in text
    assert "Título" in text
    assert "Physics & Astronomy ó\nFecha límite A B" in text
    assert "Cita" in text
    assert "Bloque" in text
    assert text.count("https://example.com") == 1
    assert "la encuesta (https://forms.gle/abc)" in text
    assert text.count("ana@example.com") == 1
    assert "mailto:" not in text
    assert "- Uno\n- Dos" in text
    assert "Celda Otra" in text
    assert "  a  b\nc" in text
    assert "Marca" in text
    assert "x.png" not in text
    assert "secreto" not in text
    assert "OCULTO" not in text
    assert "comentario" not in text
    assert "red" not in text
    assert "<" not in text


def test_render_html_source_fills_header():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="html",
        body="<p>Hola,</p>\n$header_block\n<p>Adiós</p>\n",
    )
    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    )

    assert html.count("<html>") == 0
    assert "<p>Hola,</p>" in html
    assert "<em>Ana<br>" in html
    assert "<p>Adiós</p>" in html
    assert "$header_block" not in html
    assert "$header_block" not in text
    assert "Hola,\n\nAna\nFísica\nUES\n\nAdiós" in text


def test_html_source_refuses_unfilled_placeholder():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="html",
        body="<p>Hola $nombre</p>\n$header_block\n",
    )
    with pytest.raises(UnfilledPlaceholder):
        render_message(campaign, {"name": "Ana", "position": "", "afiliacion": ""})


def test_header_escapes_html_only():
    campaign = load_campaign(CAMPAIGN)
    html, text = render_message(
        campaign,
        {"name": "Ana & Bo <lab>", "position": "", "afiliacion": ""},
        {"link1": "https://example.com"},
    )
    assert "Ana &amp; Bo &lt;lab&gt;" in html
    assert "Ana & Bo <lab>" in text
    assert "<lab>" not in html


def test_message_is_multipart_alternative(tmp_path):
    fields = {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    recipient = Recipient("ana@example.com", fields)
    base = load_campaign(CAMPAIGN)
    campaigns = [
        replace(
            base,
            delay_seconds=0,
            body_format="txt",
            body="Hola Física\n\n$header_block\n",
        ),
        replace(
            base,
            delay_seconds=0,
            body_format="html",
            body="<p>Hola Física</p>\n$header_block\n",
        ),
    ]
    for index, campaign in enumerate(campaigns):
        ledger = Ledger(tmp_path / f"sends-{index}.db")
        opened: list[FakeSMTP] = []

        def factory(box=opened):
            smtp = FakeSMTP()
            box.append(smtp)
            return smtp

        deliver(
            campaign,
            [recipient],
            ledger,
            "from@example.com",
            "secret",
            smtp_factory=factory,
            sleeper=lambda _seconds: None,
        )
        message = opened[0].sent[0]
        assert message.get_content_type() == "multipart/alternative"
        parts = message.get_payload()
        assert [part.get_content_type() for part in parts] == [
            "text/plain",
            "text/html",
        ]
        assert parts[0].get_content_charset() == "utf-8"
        assert parts[1].get_content_charset() == "utf-8"
        assert "Física" in parts[0].get_content()
        assert "Física" in parts[1].get_content()
        assert "Ana" in parts[0].get_content()
        assert "<em>Ana<br>" in parts[1].get_content()
        ledger.close()


def test_cc_comes_from_the_row(tmp_path):
    campaign = replace(load_campaign(CAMPAIGN), delay_seconds=0, cc_columns=("Copia",))
    report = parse_recipients(
        """\
Email,Nombre,Carrera,Institucion,Copia,link1,link2
ana@example.com,Ana,Física,UES,"boss@example.com, not-an-email",https://example.com,https://example.com/two
beto@example.com,Beto,Bio,UCA,,https://example.com/beto,https://example.com/two
""",
        campaign,
    )
    assert report.recipients[0].cc == ("boss@example.com",)
    assert report.invalid_cc == ["not-an-email"]
    assert report.recipients[1].cc == ()

    ledger = Ledger(tmp_path / "sends.db")
    opened: list[FakeSMTP] = []

    def factory():
        smtp = FakeSMTP()
        opened.append(smtp)
        return smtp

    deliver(
        campaign,
        report.recipients,
        ledger,
        "from@example.com",
        "secret",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )
    assert opened[0].sent[0]["To"] == "ana@example.com"
    assert opened[0].sent[0]["Cc"] == "boss@example.com"
    assert opened[0].sent[1]["To"] == "beto@example.com"
    assert opened[0].sent[1]["Cc"] is None

    deliver(
        campaign,
        report.recipients,
        Ledger(tmp_path / "test-send.db"),
        "from@example.com",
        "secret",
        to_address="erickurq@gmail.com",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )
    assert opened[1].sent[0]["To"] == "erickurq@gmail.com"
    assert opened[1].sent[0]["Cc"] is None
    ledger.close()


def test_to_address_excludes_cc(tmp_path):
    campaign = replace(load_campaign(CAMPAIGN), delay_seconds=0)
    ledger = Ledger(tmp_path / "sends.db")
    recipients = [
        Recipient(
            "ana@example.com",
            {"name": "Ana", "position": "Física", "afiliacion": "UES"},
            cc=("copia@example.com",),
            links={"link1": "https://example.com"},
        )
    ]
    opened: list[FakeSMTP] = []

    def factory():
        smtp = FakeSMTP()
        opened.append(smtp)
        return smtp

    deliver(
        campaign,
        recipients,
        ledger,
        "from@example.com",
        "secret",
        to_address="erickurq@gmail.com",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )
    test_message = opened[0].sent[0]
    assert test_message["To"] == "erickurq@gmail.com"
    assert test_message["Cc"] is None
    assert not ledger.already_sent(campaign.id, "erickurq@gmail.com")
    assert not ledger.already_sent(campaign.id, "ana@example.com")

    deliver(
        campaign,
        recipients,
        ledger,
        "from@example.com",
        "secret",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )

    normal_message = opened[1].sent[0]
    assert normal_message["To"] == "ana@example.com"
    assert normal_message["Cc"] == "copia@example.com"
    assert ledger.already_sent(campaign.id, "ana@example.com")
    ledger.close()


def test_to_address_sends_when_everyone_is_recorded(tmp_path):
    campaign = replace(load_campaign(CAMPAIGN), delay_seconds=0)
    ledger = Ledger(tmp_path / "sends.db")
    ledger.record(campaign.id, "ana@example.com", "sent")
    recipients = [
        Recipient(
            "ana@example.com",
            {"name": "Ana", "position": "Física", "afiliacion": "UES"},
            links={"link1": "https://example.com"},
        )
    ]
    opened: list[FakeSMTP] = []

    def factory():
        smtp = FakeSMTP()
        opened.append(smtp)
        return smtp

    deliver(
        campaign,
        recipients,
        ledger,
        "from@example.com",
        "secret",
        to_address="erickurquilla1999@gmail.com",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )

    assert len(opened) == 1
    assert len(opened[0].sent) == 1
    assert opened[0].sent[0]["To"] == "erickurquilla1999@gmail.com"
    assert ledger.already_sent(campaign.id, "ana@example.com")
    assert not ledger.already_sent(campaign.id, "erickurquilla1999@gmail.com")
    ledger.close()


def test_second_send_is_skipped(tmp_path):
    campaign = replace(load_campaign(CAMPAIGN), delay_seconds=0)
    ledger = Ledger(tmp_path / "sends.db")
    recipients = [
        Recipient(
            "ana@example.com",
            {"name": "Ana", "position": "Física", "afiliacion": "UES"},
            links={"link1": "https://example.com"},
        )
    ]
    opened: list[FakeSMTP] = []

    def factory():
        smtp = FakeSMTP()
        opened.append(smtp)
        return smtp

    deliver(
        campaign,
        recipients,
        ledger,
        "from@example.com",
        "secret",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )
    deliver(
        campaign,
        recipients,
        ledger,
        "from@example.com",
        "secret",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )

    assert len(opened) == 1
    assert len(opened[0].sent) == 1
    assert opened[0].sent[0]["To"] == "ana@example.com"
    assert ledger.already_sent(campaign.id, "ana@example.com")
    ledger.close()


def test_preview_sends_nothing(monkeypatch, tmp_path, capsys):
    def open_smtp(*args, **kwargs):
        raise AssertionError("preview abrió SMTP")

    def fail_deliver(*args, **kwargs):
        raise AssertionError("preview envió")

    monkeypatch.setattr("pymail.smtp_sender.smtplib.SMTP", open_smtp)
    monkeypatch.setattr("pymail.cli.deliver", fail_deliver)

    code = main(["preview", str(CAMPAIGN), "--csv", str(_csv(tmp_path))])
    captured = capsys.readouterr()

    assert code == 0
    assert "Destinatarios válidos: 1" in captured.out
    assert "Duplicados: 1" in captured.out
    assert "ana@example.com" in captured.out
    assert "Inválidos: 1" in captured.out
    assert "bad-email" in captured.out
    assert "Primeros 5:" in captured.out
    assert (
        "1. ana@example.com | name: Ana | position: Física | afiliacion: UES"
        " | link1: https://example.com | link2: https://example.com/two"
        in captured.out
    )
    assert "Muestra para ana@example.com" in captured.out
    assert "https://example.com" in captured.out


TWO_CSV = """\
Email,Nombre,Carrera,Institucion,cced1,cced2,link1,link2
ana@example.com,Ana,Física,UES,,,https://example.com,https://example.com/two
beto@example.com,Beto,Bio,UCA,,,https://example.com/beto,https://example.com/two
"""

SUBJECT_PROMPT = "¿Confirmas el asunto? [yes/no]: "
RECIPIENT_PROMPT = "¿Confirmas el destinatario? [yes/no]: "
TEXT_PROMPT = "¿Confirmas el texto? [yes/no]: "
ALL_PROMPT = "¿Envías todos los correos pendientes? [yes/no]: "
TEST_PROMPTS = [SUBJECT_PROMPT, RECIPIENT_PROMPT, TEXT_PROMPT]
SHEET_PROMPTS = TEST_PROMPTS + [ALL_PROMPT]


def _write_csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "people.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _prepare_send(
    monkeypatch,
    answers,
    *,
    tty=True,
    password="  secret  ",
    address="  from@example.com  ",
):
    monkeypatch.setenv("EMAIL_ADDRESS", "stored@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "from-env")
    calls = []

    def fake_deliver(*args, **kwargs):
        assert os.environ.get("EMAIL_ADDRESS") == "stored@example.com"
        assert os.environ.get("EMAIL_PASSWORD") == "from-env"
        calls.append((args, kwargs))

    monkeypatch.setattr("pymail.cli.deliver", fake_deliver)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)
    pending = list(answers)
    prompts = []
    password_prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        if prompt == ADDRESS_PROMPT:
            if address is None:
                raise EOFError
            return address
        if not pending:
            raise AssertionError(f"input inesperado: {prompt}")
        return pending.pop(0)

    def fake_getpass(prompt=""):
        password_prompts.append(prompt)
        return password

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("pymail.cli.getpass.getpass", fake_getpass)
    return calls, prompts, pending, password_prompts


def _send(tmp_path: Path, csv_text: str, *extra: str) -> int:
    return main(
        [
            "send",
            str(CAMPAIGN),
            "--csv",
            str(_write_csv(tmp_path, csv_text)),
            "--ledger",
            str(tmp_path / "sends.db"),
            *extra,
        ]
    )


def test_to_send_confirms_that_message(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(monkeypatch, ["yes", "yes", "yes"])

    code = _send(tmp_path, SAMPLE_CSV, "--limit", "1", "--to", "tu@gmail.com")
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == TEST_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert "Asunto: Example message" in captured.out
    assert "Destinatario: tu@gmail.com" in captured.out
    assert "Destinatario: ana@example.com" not in captured.out
    assert "This is an example message" in captured.out
    assert "Ana\nFísica\nUES" in captured.out
    assert len(calls) == 1
    _args, kwargs = calls[0]
    assert kwargs["to_address"] == "tu@gmail.com"
    assert kwargs["limit"] == 1
    assert _args[1][0].email == "ana@example.com"
    assert _args[3] == "from@example.com"
    assert _args[4] == "secret"
    assert password_prompts == [PASSWORD_PROMPT]


def test_sheet_send_confirms_first_then_everyone(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(monkeypatch, ["yes", "yes", "yes", "yes"])

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert "Asunto: Example message" in captured.out
    assert "Destinatario: ana@example.com" in captured.out
    assert "beto@example.com" not in captured.out
    assert "Beto" not in captured.out
    assert "Ana\nFísica\nUES" in captured.out
    assert "Se enviarán 2 correos pendientes de la hoja." in captured.out
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs["to_address"] is None
    assert kwargs["limit"] is None
    assert [recipient.email for recipient in args[1]] == [
        "ana@example.com",
        "beto@example.com",
    ]
    assert args[3] == "from@example.com"
    assert args[4] == "secret"
    assert password_prompts == [PASSWORD_PROMPT]


def test_sheet_send_with_limit_names_the_limit(monkeypatch, tmp_path, capsys):
    calls, _prompts, pending, password_prompts = _prepare_send(monkeypatch, ["yes", "yes", "yes", "yes"])

    code = _send(tmp_path, TWO_CSV, "--limit", "1")
    captured = capsys.readouterr()

    assert code == 0
    assert pending == []
    assert "Destinatario: ana@example.com" in captured.out
    assert "beto@example.com" not in captured.out
    assert "Se enviará 1 correo pendiente de la hoja. Límite: 1." in captured.out
    assert calls[0][1]["limit"] == 1
    assert calls[0][1]["to_address"] is None
    assert calls[0][0][3] == "from@example.com"
    assert calls[0][0][4] == "secret"
    assert password_prompts == [PASSWORD_PROMPT]
    assert _prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]


def test_sheet_send_shows_cc_of_the_first_row(monkeypatch, tmp_path, capsys):
    campaign = tmp_path / "camp"
    campaign.mkdir()
    (campaign / "campaign.toml").write_text(
        """\
id = "camp"
subject = "Hola"
sheet_id = "x"
sheet_name = "Sheet1"
email_column = "Email"
cc_columns = ["Copia"]

[columns]
name = "Nombre"
position = "Carrera"
afiliacion = "Institucion"
""",
        encoding="utf-8",
    )
    (campaign / "body.txt").write_text("Carta\n$header_block\n", encoding="utf-8")
    csv_path = _write_csv(
        tmp_path,
        """\
Email,Nombre,Carrera,Institucion,Copia
ana@example.com,Ana,Física,UES,boss@example.com
beto@example.com,Beto,Bio,UCA,
""",
    )
    calls, prompts, _pending, password_prompts = _prepare_send(monkeypatch, ["yes", "yes", "yes", "yes"])

    code = main(
        ["send", str(campaign), "--csv", str(csv_path), "--ledger", str(tmp_path / "sends.db")]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert "Destinatario: ana@example.com | cc: boss@example.com" in captured.out
    assert "Beto" not in captured.out
    assert len(calls) == 1
    assert calls[0][0][3] == "from@example.com"
    assert calls[0][0][4] == "secret"
    assert password_prompts == [PASSWORD_PROMPT]


@pytest.mark.parametrize(
    "answers",
    [
        ["y"],
        ["Yes"],
        ["yes", "no"],
        ["yes", "yes", ""],
        ["yes", "yes", "yes", "y"],
    ],
)
def test_sheet_send_cancel_sends_nothing(monkeypatch, tmp_path, capsys, answers):
    calls, prompts, _pending, password_prompts = _prepare_send(monkeypatch, answers)

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert len(prompts) == len(answers)
    assert ADDRESS_PROMPT not in prompts
    assert password_prompts == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


@pytest.mark.parametrize(
    "answers",
    [
        ["no"],
        ["y"],
        ["yes", "x"],
        ["yes", "yes", "Y"],
    ],
)
def test_to_send_cancel_sends_nothing(monkeypatch, tmp_path, capsys, answers):
    calls, prompts, _pending, password_prompts = _prepare_send(monkeypatch, answers)

    code = _send(tmp_path, SAMPLE_CSV, "--to", "tu@gmail.com")
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == TEST_PROMPTS[: len(answers)]
    assert ADDRESS_PROMPT not in prompts
    assert password_prompts == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_eof_cancels_before_sending(monkeypatch, tmp_path, capsys):
    calls, _prompts, _pending, password_prompts = _prepare_send(monkeypatch, [])

    def fake_input(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert password_prompts == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_no_pending_recipients_asks_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EMAIL_ADDRESS", "stored@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "from-env")

    def fail_input(prompt=""):
        raise AssertionError(f"no debía preguntar: {prompt}")

    def fail_getpass(prompt=""):
        raise AssertionError(f"no debía pedir la contraseña: {prompt}")

    def fail_smtp():
        raise AssertionError("no debía abrir SMTP")

    monkeypatch.setattr("builtins.input", fail_input)
    monkeypatch.setattr("pymail.cli.getpass.getpass", fail_getpass)
    monkeypatch.setattr("pymail.smtp_sender.default_smtp_factory", fail_smtp)
    ledger_path = tmp_path / "sends.db"
    ledger = Ledger(ledger_path)
    ledger.record("example", "ana@example.com", "sent")
    ledger.close()

    code = main(
        [
            "send",
            str(CAMPAIGN),
            "--csv",
            str(_csv(tmp_path)),
            "--ledger",
            str(ledger_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "No hay correos pendientes. Los ya enviados están en el registro." in captured.out


def test_unfilled_placeholder_asks_nothing(monkeypatch, tmp_path, capsys):
    campaign = tmp_path / "camp"
    campaign.mkdir()
    (campaign / "campaign.toml").write_text(
        """\
id = "camp"
subject = "Hola"
sheet_id = "x"
sheet_name = "Sheet1"
email_column = "Email"

[columns]
name = "Nombre"
position = "Carrera"
afiliacion = "Institucion"
""",
        encoding="utf-8",
    )
    (campaign / "body.txt").write_text("Hola $nombre\n$header_block\n", encoding="utf-8")
    calls, _prompts, _pending, password_prompts = _prepare_send(monkeypatch, ["yes", "yes", "yes", "yes"])

    code = main(
        [
            "send",
            str(campaign),
            "--csv",
            str(_csv(tmp_path)),
            "--ledger",
            str(tmp_path / "sends.db"),
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert _pending == ["yes", "yes", "yes", "yes"]
    assert ADDRESS_PROMPT not in _prompts
    assert password_prompts == []
    assert "Falta el dato $nombre." in captured.err


def test_send_without_tty_does_not_send(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
        tty=False,
    )

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS
    assert ADDRESS_PROMPT not in prompts
    assert pending == []
    assert password_prompts == []
    assert "El correo y la contraseña solo se escriben en la terminal." in captured.err


def test_empty_password_cancels(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
        password="   ",
    )

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert password_prompts == [PASSWORD_PROMPT]
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_password_eof_cancels(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
    )

    def raise_eof(prompt=""):
        password_prompts.append(prompt)
        raise EOFError

    monkeypatch.setattr("pymail.cli.getpass.getpass", raise_eof)

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert password_prompts == [PASSWORD_PROMPT]
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_empty_address_cancels_before_password(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
        address="   ",
    )

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert password_prompts == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_invalid_address_cancels_before_password(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
        address="no-es-correo",
    )

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert password_prompts == []
    assert "La dirección no es válida: no-es-correo" in captured.err
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_address_eof_cancels_before_password(monkeypatch, tmp_path, capsys):
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch,
        ["yes", "yes", "yes", "yes"],
        address=None,
    )

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == SHEET_PROMPTS + [ADDRESS_PROMPT]
    assert pending == []
    assert password_prompts == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_example_fills_link1():
    campaign = load_campaign(CAMPAIGN)
    assert campaign.link_columns == ("link1", "link2")
    html, text = render_message(
        campaign,
        {"name": "Ana", "position": "Física", "afiliacion": "UES"},
        {"link1": "https://example.com/ana"},
    )
    assert 'href="https://example.com/ana"' in html
    assert "https://example.com/ana" in text
    assert "$link1" not in html
    assert "$link1" not in text
    assert "<em>Ana<br>" in html
    assert "Ana\nFísica\nUES" in text
    assert "$header_block" not in html
    assert "$header_block" not in text


def test_omitted_link_columns_defaults_empty(tmp_path):
    directory = _campaign_dir(tmp_path, body="Hola,\n\n$header_block\n\nAdiós\n")
    campaign = load_campaign(directory)
    assert campaign.link_columns == ()
    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    )
    assert "<p>Hola,</p>" in html
    assert "<em>Ana<br>" in html
    assert "<p>Adiós</p>" in html
    assert "Hola,\n\nAna\nFísica\nUES\n\nAdiós" in text


@pytest.mark.parametrize(
    ("link_columns", "cc_columns", "match"),
    [
        ('["link 1"]', None, "no es un nombre válido"),
        ('["año"]', None, "no es un nombre válido"),
        ('["header_block"]', None, "no puede usar header_block"),
        ('["link1", "link1"]', None, "nombre repetido"),
        ('["link1"]', '["link1"]', "columna de copia"),
        ('["name"]', None, "clave de columns"),
        ('"link1"', None, "lista de nombres"),
    ],
)
def test_link_columns_rejected(tmp_path, link_columns, cc_columns, match):
    directory = _campaign_dir(
        tmp_path,
        body="Hola\n",
        link_columns=link_columns,
        cc_columns=cc_columns,
    )
    with pytest.raises(ValueError, match=match):
        load_campaign(directory)


def test_missing_link_column(tmp_path):
    directory = _campaign_dir(
        tmp_path,
        body="Hola $link1\n",
        link_columns='["link1"]',
    )
    campaign = load_campaign(directory)
    with pytest.raises(ValueError, match="columna de enlace 'link1'"):
        parse_recipients(
            "Email,Nombre,Carrera,Institucion\nana@example.com,Ana,Física,UES\n",
            campaign,
        )


def test_links_do_not_become_cc(tmp_path):
    directory = _campaign_dir(
        tmp_path,
        body="Ver $link1\n",
        link_columns='["link1"]',
        cc_columns='["Copia"]',
    )
    campaign = load_campaign(directory)
    report = parse_recipients(
        """\
Email,Nombre,Carrera,Institucion,Copia,link1
ana@example.com,Ana,Física,UES,"boss@example.com, not-an-email",https://example.com/ana
""",
        campaign,
    )
    assert report.recipients[0].cc == ("boss@example.com",)
    assert report.invalid_cc == ["not-an-email"]
    assert report.recipients[0].links == {"link1": "https://example.com/ana"}


def test_txt_links_are_personalized(tmp_path):
    directory = _campaign_dir(
        tmp_path,
        body_format="txt",
        link_columns='[" link1 ", "link2"]',
        body=(
            "Hello,\n\n"
            "$header_block\n\n"
            "Your form: $link1\n"
            "Details: $link2\n"
        ),
    )
    campaign = load_campaign(directory)
    assert campaign.link_columns == ("link1", "link2")
    report = parse_recipients(
        """\
Email,Nombre,Carrera,Institucion,link1,link2
ana@example.com,Ana,Física,UES,https://forms.gle/aaa?x=1&y=2, https://example.com/ana 
beto@example.com,Beto,Bio,UCA,https://forms.gle/bbb,https://example.com/beto
""",
        campaign,
    )
    html, text = render_message(
        campaign, report.recipients[0].fields, report.recipients[0].links
    )
    assert report.recipients[0].links["link2"] == "https://example.com/ana"
    assert "https://forms.gle/aaa?x=1&y=2" in text
    assert "https://example.com/ana" in text
    assert "https://example.com/beto" not in text
    assert '<a href="https://forms.gle/aaa?x=1&amp;y=2">' in html
    assert "https://forms.gle/aaa?x=1&amp;y=2</a>" in html
    assert "&amp;amp;" not in html
    assert "Ana\nFísica\nUES" in text
    assert "<em>Ana<br>" in html
    assert "$header_block" not in html
    assert "$link1" not in text

    _html_b, text_b = render_message(
        campaign, report.recipients[1].fields, report.recipients[1].links
    )
    assert "https://forms.gle/bbb" in text_b
    assert "https://example.com/beto" in text_b
    assert "https://example.com/ana" not in text_b
    assert "Beto\nBio\nUCA" in text_b


def test_html_links_are_escaped():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="html",
        body=(
            "<p>Hello,</p>\n"
            "$header_block\n"
            '<p>Your form: <a href="$link1">$link1</a></p>\n'
            '<p>Details: <a href="${link2}">${link2}</a></p>\n'
        ),
        link_columns=("link1", "link2"),
    )
    html, text = render_message(
        campaign,
        {"name": "Ana", "position": "Física", "afiliacion": "UES"},
        {
            "link1": "https://forms.gle/aaa?x=1&y=2",
            "link2": 'https://example.com/a"b',
        },
    )
    assert 'href="https://forms.gle/aaa?x=1&amp;y=2"' in html
    assert 'href="https://example.com/a&quot;b"' in html
    assert "https://forms.gle/aaa?x=1&y=2" in text
    assert 'https://example.com/a"b' in text
    assert "&quot;" not in text
    assert "&amp;" not in text
    assert "Ana\nFísica\nUES" in text
    assert "<em>Ana<br>" in html
    assert "$link1" not in html
    assert "${link2}" not in text

    _html_b, text_b = render_message(
        campaign,
        {"name": "Beto", "position": "Bio", "afiliacion": "UCA"},
        {"link1": "https://forms.gle/bbb", "link2": "https://example.com/beto"},
    )
    assert "https://forms.gle/bbb" in text_b
    assert "https://example.com/beto" in text_b
    assert 'https://example.com/a"b' not in text_b


def test_link_values_keep_literal_dollars():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="txt",
        body="Precio $$5 y $link1\n\n$header_block\n",
        link_columns=("link1",),
    )
    html, text = render_message(
        campaign,
        {"name": "Ana", "position": "", "afiliacion": ""},
        {"link1": "https://example.com/$foo"},
    )
    assert "Precio $5 y https://example.com/$foo" in text
    assert "https://example.com/$foo" in html
    assert "$link1" not in text


def test_unused_link_column_may_be_blank():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="txt",
        body="Hola,\n\n$header_block\n\nAdiós\n",
        link_columns=("link2",),
    )
    html, text = render_message(
        campaign,
        {"name": "Ana", "position": "Física", "afiliacion": "UES"},
        {"link2": "  "},
    )
    assert "<p>Hola,</p>" in html
    assert "<em>Ana<br>" in html
    assert "<p>Adiós</p>" in html
    assert "Hola,\n\nAna\nFísica\nUES\n\nAdiós" in text


def test_unknown_placeholder_with_link_columns():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="txt",
        body="Hola $nombre\n$header_block\n",
        link_columns=("link1",),
    )
    with pytest.raises(UnfilledPlaceholder, match=r"Falta el dato \$nombre"):
        render_message(
            campaign,
            {"name": "Ana", "position": "", "afiliacion": ""},
            {"link1": "https://example.com"},
        )


def test_header_placeholder_still_refused_with_links():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="txt",
        body="Hola $link1\n\n$header_block\n",
        link_columns=("link1",),
    )
    with pytest.raises(UnfilledPlaceholder, match="sin llenar"):
        render_message(
            campaign,
            {"name": "Ana $extra", "position": "", "afiliacion": ""},
            {"link1": "https://example.com"},
        )


def test_blank_referenced_link_is_refused():
    campaign = replace(
        load_campaign(CAMPAIGN),
        body_format="html",
        body='<p><a href="$link1">$link1</a></p>\n$header_block\n',
        link_columns=("link1",),
    )
    with pytest.raises(UnfilledPlaceholder, match=r"El dato \$link1 está vacío"):
        render_message(
            campaign,
            {"name": "Ana", "position": "", "afiliacion": ""},
            {"link1": "  "},
        )


def test_personalized_links_reach_the_message(tmp_path):
    campaign = replace(
        load_campaign(CAMPAIGN),
        delay_seconds=0,
        body_format="txt",
        body="Formulario: $link1\n\n$header_block\n",
        link_columns=("link1",),
    )
    recipient = Recipient(
        "ana@example.com",
        {"name": "Ana", "position": "Física", "afiliacion": "UES"},
        links={"link1": "https://forms.gle/aaa?x=1&y=2"},
    )
    ledger = Ledger(tmp_path / "sends.db")
    opened: list[FakeSMTP] = []

    def factory():
        smtp = FakeSMTP()
        opened.append(smtp)
        return smtp

    deliver(
        campaign,
        [recipient],
        ledger,
        "from@example.com",
        "secret",
        smtp_factory=factory,
        sleeper=lambda _seconds: None,
    )
    parts = opened[0].sent[0].get_payload()
    assert "https://forms.gle/aaa?x=1&y=2" in parts[0].get_content()
    assert '<a href="https://forms.gle/aaa?x=1&amp;y=2">' in parts[1].get_content()
    assert "<em>Ana<br>" in parts[1].get_content()
    ledger.close()


def test_preview_shows_link_columns(monkeypatch, tmp_path, capsys):
    directory = _campaign_dir(
        tmp_path,
        body="Your form: $link1\n\n$header_block\n",
        link_columns='["link1", "link2"]',
    )
    csv_path = _write_csv(
        tmp_path,
        """\
Email,Nombre,Carrera,Institucion,link1,link2
ana@example.com,Ana,Física,UES,https://example.com/ana,https://example.com/extra
""",
    )

    def fail_deliver(*args, **kwargs):
        raise AssertionError("preview envió")

    monkeypatch.setattr("pymail.cli.deliver", fail_deliver)
    code = main(["preview", str(directory), "--csv", str(csv_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert (
        "1. ana@example.com | name: Ana | position: Física | afiliacion: UES"
        " | link1: https://example.com/ana | link2: https://example.com/extra"
        in captured.out
    )
    assert '<a href="https://example.com/ana">' in captured.out


def test_blank_link_stops_send(monkeypatch, tmp_path, capsys):
    directory = _campaign_dir(
        tmp_path,
        body="Ver $link1\n$header_block\n",
        link_columns='["link1"]',
    )
    csv_path = _write_csv(
        tmp_path,
        """\
Email,Nombre,Carrera,Institucion,link1
ana@example.com,Ana,Física,UES,
""",
    )
    calls, prompts, pending, password_prompts = _prepare_send(
        monkeypatch, ["yes", "yes", "yes", "yes"]
    )

    code = main(
        [
            "send",
            str(directory),
            "--csv",
            str(csv_path),
            "--ledger",
            str(tmp_path / "sends.db"),
        ]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == []
    assert pending == ["yes", "yes", "yes", "yes"]
    assert password_prompts == []
    assert "El dato $link1 está vacío." in captured.err
