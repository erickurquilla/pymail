"""Vista previa y envío. La vista previa es el comando por defecto del programa."""
"""Vista previa y envío. La vista previa es el comando por defecto del programa."""

from pathlib import Path
import argparse
import os
import sys

from dotenv import load_dotenv

from pymail.campaign import load_campaign, project_root_for
from pymail.ledger import Ledger
from pymail.recipients import is_valid_email, load_recipients
from pymail.render import UnfilledPlaceholder, render_message
from pymail.smtp_sender import deliver


def load_environment() -> None:
    load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymail",
        description="Envía una campaña de correo. preview no manda nada.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview", help="Muestra destinatarios y una carta de muestra.")
    _add_common(preview)

    send = sub.add_parser("send", help="Envía los correos que aún no están en el registro.")
    _add_common(send)
    send.add_argument("--limit", type=int, default=None, help="Máximo de correos en esta corrida.")
    send.add_argument(
        "--to",
        default=None,
        help="Manda una sola prueba a esta dirección, con los datos de la primera fila pendiente.",
    )
    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("campaign", help="Carpeta de la campaña.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="CSV local en lugar de descargar la hoja de Google.",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Ruta del registro SQLite. Por defecto: sends.db en la raíz del proyecto.",
    )


def credentials() -> tuple[str, str] | None:
    address = os.environ.get("EMAIL_ADDRESS", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()
    if not address or not password:
        print(
            "Faltan EMAIL_ADDRESS o EMAIL_PASSWORD. "
            "Copia .env.example a .env y completa los dos valores.",
            file=sys.stderr,
        )
        return None
    return address, password


PREVIEW_ROWS = 5


def print_preview_rows(campaign, recipients) -> None:
    shown = recipients[:PREVIEW_ROWS]
    print()
    print(f"Primeros {PREVIEW_ROWS}:")
    for index, recipient in enumerate(shown, start=1):
        fields = " | ".join(
            f"{key}: {recipient.fields.get(key, '')}" for key in campaign.columns
        )
        line = f"  {index}. {recipient.email}"
        if fields:
            line = f"{line} | {fields}"
        if recipient.cc:
            line = f"{line} | cc: {', '.join(recipient.cc)}"
        print(line)


def print_invalid_cc(report) -> None:
    if not report.invalid_cc:
        return
    print(f"Copias inválidas: {len(report.invalid_cc)}")
    for item in report.invalid_cc:
        print(f"  {item}")


def preview(campaign, report) -> int:
    print(f"Campaña: {campaign.id}")
    print(f"Destinatarios válidos: {len(report.recipients)}")
    print(f"Duplicados: {len(report.duplicates)}")
    for item in report.duplicates:
        print(f"  {item}")
    print(f"Inválidos: {len(report.invalid)}")
    for item in report.invalid:
        print(f"  {item}")
    print_invalid_cc(report)
    print(f"Correos vacíos omitidos: {report.blank_count}")
    if not report.recipients:
        print("No hay una muestra: ningún correo válido.")
        return 0

    print_preview_rows(campaign, report.recipients)
    sample = report.recipients[0]
    try:
        html, text = render_message(campaign, sample.fields)
    except UnfilledPlaceholder as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print()
    print(f"Muestra para {sample.email}")
    print("--- texto ---")
    print(text)
    print("--- html ---")
    print(html)
    return 0


def send(campaign, report, ledger, address, password, limit, to_address, smtp_factory=None) -> int:
    if limit is not None and limit < 1:
        print("--limit tiene que ser 1 o más.", file=sys.stderr)
        return 1
    if to_address is not None and not is_valid_email(to_address):
        print(f"La dirección de prueba no es válida: {to_address}", file=sys.stderr)
        return 1
    print_invalid_cc(report)
    try:
        deliver(
            campaign,
            report.recipients,
            ledger,
            address,
            password,
            limit=limit,
            to_address=to_address,
            smtp_factory=smtp_factory,
            sleeper=_sleep,
        )
    except UnfilledPlaceholder as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"No se pudo conectar con Gmail: {exc}", file=sys.stderr)
        return 1
    return 0


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_environment()
    try:
        campaign = load_campaign(args.campaign)
        report = load_recipients(campaign, csv_path=args.csv)
    except (OSError, ValueError) as exc:
        print(f"No se pudo leer la campaña o la hoja: {exc}", file=sys.stderr)
        return 1

    if args.command == "preview":
        return preview(campaign, report)

    found = credentials()
    if found is None:
        return 1
    address, password = found
    ledger_path = args.ledger or (project_root_for(campaign.directory) / "sends.db")
    ledger = Ledger(ledger_path)
    try:
        return send(campaign, report, ledger, address, password, args.limit, args.to)
    finally:
        ledger.close()


if __name__ == "__main__":
    raise SystemExit(main())
