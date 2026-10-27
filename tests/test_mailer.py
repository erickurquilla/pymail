"""Pruebas sin red y sin SMTP real."""

from dataclasses import replace
from pathlib import Path

from pymail.campaign import load_campaign
from pymail.cli import main
from pymail.ledger import Ledger
from pymail.recipients import Recipient, parse_recipients
from pymail.render import UnfilledPlaceholder, render_message, text_to_html
from pymail.smtp_sender import deliver

import pytest


CAMPAIGN = Path("campaigns/example")

SAMPLE_CSV = """\
Email,Nombre,Carrera,Institucion
ana@example.com,Ana,Física,UES
ana@example.com,Ana Otra,Química,UCA
bad-email,Beto,Bio,UES
,Sin correo,Mate,UES
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
    html, text = render_message(
        campaign, {"name": "", "position": " ", "afiliacion": None}
    )
    assert "<em>" not in html
    assert "$header_block" not in html
    assert "$header_block" not in text
    assert "https://example.com" in html

    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    )
    assert "<em>Ana<br>" in html
    assert "Ana\nFísica\nUES" in text


def test_unfilled_placeholder_refused():
    campaign = load_campaign(CAMPAIGN)
    broken = replace(campaign, body_txt="Hola $nombre\n$header_block")
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
        body_txt="Hola,\n\n$header_block\n\nAdiós\n",
    )
    html, text = render_message(
        campaign, {"name": "Ana", "position": "Física", "afiliacion": "UES"}
    )

    assert "<p>Hola,</p>" in html
    assert "<em>Ana<br>" in html
    assert "<p>Adiós</p>" in html
    assert "$header_block" not in html
    assert "Hola,\n\nAna\nFísica\nUES\n\nAdiós" in text


def test_cc_comes_from_the_row(tmp_path):
    campaign = replace(load_campaign(CAMPAIGN), delay_seconds=0, cc_columns=("Copia",))
    report = parse_recipients(
        """\
Email,Nombre,Carrera,Institucion,Copia
ana@example.com,Ana,Física,UES,"boss@example.com, not-an-email"
beto@example.com,Beto,Bio,UCA,
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


def test_send_without_env_does_not_send(monkeypatch, tmp_path):
    monkeypatch.setattr("pymail.cli.load_environment", lambda: None)
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    calls = []
    monkeypatch.setattr(
        "pymail.cli.deliver",
        lambda *args, **kwargs: calls.append("deliver"),
    )

    code = main(
        [
            "send",
            str(CAMPAIGN),
            "--csv",
            str(_csv(tmp_path)),
            "--ledger",
            str(tmp_path / "sends.db"),
        ]
    )

    assert code == 1
    assert calls == []


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
    assert "1. ana@example.com | name: Ana | position: Física | afiliacion: UES" in captured.out
    assert "Muestra para ana@example.com" in captured.out
    assert "https://example.com" in captured.out


TWO_CSV = """\
Email,Nombre,Carrera,Institucion
ana@example.com,Ana,Física,UES
beto@example.com,Beto,Bio,UCA
"""

SUBJECT_PROMPT = "Escribe y para confirmar el asunto: "
RECIPIENT_PROMPT = "Escribe y para confirmar el destinatario: "
TEXT_PROMPT = "Escribe y para confirmar el texto: "
ALL_PROMPT = "Escribe y para enviarlos todos: "
TEST_PROMPTS = [SUBJECT_PROMPT, RECIPIENT_PROMPT, TEXT_PROMPT]
SHEET_PROMPTS = TEST_PROMPTS + [ALL_PROMPT]


def _write_csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "people.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _prepare_send(monkeypatch, answers):
    monkeypatch.setattr("pymail.cli.load_environment", lambda: None)
    monkeypatch.setenv("EMAIL_ADDRESS", "from@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")
    calls = []

    def fake_deliver(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("pymail.cli.deliver", fake_deliver)
    pending = list(answers)
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        if not pending:
            raise AssertionError(f"input inesperado: {prompt}")
        return pending.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    return calls, prompts, pending


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
    calls, prompts, pending = _prepare_send(monkeypatch, ["y", "y", "y"])

    code = _send(tmp_path, SAMPLE_CSV, "--limit", "1", "--to", "tu@gmail.com")
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == TEST_PROMPTS
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


def test_sheet_send_confirms_first_then_everyone(monkeypatch, tmp_path, capsys):
    calls, prompts, pending = _prepare_send(monkeypatch, ["y", "y", "y", "y"])

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == SHEET_PROMPTS
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


def test_sheet_send_with_limit_names_the_limit(monkeypatch, tmp_path, capsys):
    calls, _prompts, pending = _prepare_send(monkeypatch, ["y", "y", "y", "y"])

    code = _send(tmp_path, TWO_CSV, "--limit", "1")
    captured = capsys.readouterr()

    assert code == 0
    assert pending == []
    assert "Destinatario: ana@example.com" in captured.out
    assert "beto@example.com" not in captured.out
    assert "Se enviará 1 correo pendiente de la hoja. Límite: 1." in captured.out
    assert calls[0][1]["limit"] == 1
    assert calls[0][1]["to_address"] is None


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
    calls, prompts, _pending = _prepare_send(monkeypatch, ["y", "y", "y", "y"])

    code = main(
        ["send", str(campaign), "--csv", str(csv_path), "--ledger", str(tmp_path / "sends.db")]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert prompts == SHEET_PROMPTS
    assert "Destinatario: ana@example.com | cc: boss@example.com" in captured.out
    assert "Beto" not in captured.out
    assert len(calls) == 1


@pytest.mark.parametrize(
    "answers",
    [
        ["Y"],
        ["y", "n"],
        ["y", "y", ""],
        ["y", "y", "y", "yes"],
    ],
)
def test_sheet_send_cancel_sends_nothing(monkeypatch, tmp_path, capsys, answers):
    calls, prompts, _pending = _prepare_send(monkeypatch, answers)

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert len(prompts) == len(answers)
    assert "Envío cancelado. No se envió ningún correo." in captured.err


@pytest.mark.parametrize(
    "answers",
    [
        ["n"],
        ["y", "x"],
        ["y", "y", "Y"],
    ],
)
def test_to_send_cancel_sends_nothing(monkeypatch, tmp_path, capsys, answers):
    calls, prompts, _pending = _prepare_send(monkeypatch, answers)

    code = _send(tmp_path, SAMPLE_CSV, "--to", "tu@gmail.com")
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert prompts == TEST_PROMPTS[: len(answers)]
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_eof_cancels_before_sending(monkeypatch, tmp_path, capsys):
    calls, _prompts, _pending = _prepare_send(monkeypatch, [])

    def fake_input(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    code = _send(tmp_path, TWO_CSV)
    captured = capsys.readouterr()

    assert code == 1
    assert calls == []
    assert "Envío cancelado. No se envió ningún correo." in captured.err


def test_no_pending_recipients_asks_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("pymail.cli.load_environment", lambda: None)
    monkeypatch.setenv("EMAIL_ADDRESS", "from@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")

    def fail_input(prompt=""):
        raise AssertionError(f"no debía preguntar: {prompt}")

    def fail_smtp():
        raise AssertionError("no debía abrir SMTP")

    monkeypatch.setattr("builtins.input", fail_input)
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
    calls, _prompts, _pending = _prepare_send(monkeypatch, ["y", "y", "y", "y"])

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
    assert _pending == ["y", "y", "y", "y"]
    assert "Falta el dato $nombre." in captured.err
