"""Pruebas sin red y sin SMTP real."""

from dataclasses import replace
from pathlib import Path

from pymail.campaign import load_campaign
from pymail.cli import main
from pymail.ledger import Ledger
from pymail.recipients import Recipient, parse_recipients
from pymail.render import UnfilledPlaceholder, render_message
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
    broken = replace(
        campaign,
        body_html="Hola $nombre\n$header_block",
        body_txt="Hola $nombre\n$header_block",
    )
    with pytest.raises(UnfilledPlaceholder):
        render_message(broken, {"name": "Ana", "position": "", "afiliacion": ""})


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
