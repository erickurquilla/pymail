"""Una sola sesión SMTP para todos los pendientes de una campaña."""

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import time

from pymail.campaign import Campaign
from pymail.ledger import Ledger
from pymail.recipients import Recipient
from pymail.render import render_message


ATTEMPTS = 3


@dataclass
class Outbound:
    email: str
    name: str
    html: str
    text: str


def default_smtp_factory():
    return smtplib.SMTP("smtp.gmail.com", 587, timeout=30)


def select_pending(
    campaign: Campaign,
    recipients: list[Recipient],
    ledger: Ledger,
    limit: int | None = None,
) -> list[Recipient]:
    pending: list[Recipient] = []
    for recipient in recipients:
        if ledger.already_sent(campaign.id, recipient.email):
            continue
        pending.append(recipient)
        if limit is not None and len(pending) >= limit:
            break
    return pending


def build_outbound(campaign: Campaign, recipient: Recipient, to_address: str | None = None) -> Outbound:
    html, text = render_message(campaign, recipient.fields)
    return Outbound(
        email=to_address or recipient.email,
        name=(recipient.fields.get("name") or "").strip(),
        html=html,
        text=text,
    )


def _message(
    campaign: Campaign,
    outbound: Outbound,
    from_address: str,
    include_cc: bool,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = campaign.subject
    message["From"] = from_address
    message["To"] = outbound.email
    if include_cc and campaign.cc:
        message["Cc"] = ", ".join(campaign.cc)
    message.set_content(outbound.text)
    message.add_alternative(outbound.html, subtype="html")
    return message


def _display(outbound: Outbound) -> str:
    name = outbound.name or "(sin nombre)"
    return f"{name} at {outbound.email}"


def deliver(
    campaign: Campaign,
    recipients: list[Recipient],
    ledger: Ledger,
    address: str,
    password: str,
    limit: int | None = None,
    to_address: str | None = None,
    smtp_factory=None,
    sleeper=time.sleep,
) -> None:
    """Render pending rows, then send them on one SMTP session.

    ``to_address`` replaces the recipient and records that address. The letter
    still uses the first pending row, and the campaign Cc list is left off.
    Rendering happens before any connection, so an unfilled placeholder never
    opens SMTP.
    """
    pending = select_pending(campaign, recipients, ledger, limit=limit)
    if to_address:
        pending = pending[:1]
    outbound = [
        build_outbound(campaign, recipient, to_address) for recipient in pending
    ]
    send_messages(
        campaign,
        outbound,
        address,
        password,
        ledger,
        smtp_factory=smtp_factory,
        sleeper=sleeper,
        include_cc=to_address is None,
    )


def send_messages(
    campaign: Campaign,
    outbound: list[Outbound],
    address: str,
    password: str,
    ledger: Ledger,
    smtp_factory=None,
    sleeper=time.sleep,
    include_cc: bool = True,
) -> None:
    if not outbound:
        print("No hay correos pendientes. Los ya enviados están en el registro.")
        return

    factory = smtp_factory or default_smtp_factory
    smtp = factory()
    try:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(address, password)
        for index, item in enumerate(outbound):
            _send_one(smtp, campaign, item, ledger, address, include_cc)
            if index < len(outbound) - 1 and campaign.delay_seconds:
                sleeper(campaign.delay_seconds)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass


def _send_one(
    smtp,
    campaign: Campaign,
    item: Outbound,
    ledger: Ledger,
    from_address: str,
    include_cc: bool,
) -> None:
    print(f"Sending to {_display(item)}")
    last_error: Exception | None = None
    for _attempt in range(ATTEMPTS):
        try:
            smtp.send_message(_message(campaign, item, from_address, include_cc))
            ledger.record(campaign.id, item.email, "sent")
            print(f"Sent to {_display(item)}")
            return
        except Exception as exc:
            last_error = exc
    error = str(last_error) if last_error else "error desconocido"
    ledger.record(campaign.id, item.email, "error", error=error)
    print(f"Error al enviar a {_display(item)}: {error}")
