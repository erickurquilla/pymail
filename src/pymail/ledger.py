"""Registro local de envíos. Un reintento omite los correos ya marcados como enviados."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sends (
                campaign_id TEXT NOT NULL,
                email TEXT NOT NULL,
                status TEXT NOT NULL,
                sent_at TEXT,
                error TEXT,
                PRIMARY KEY (campaign_id, email)
            )
            """
        )
        self._conn.commit()

    def already_sent(self, campaign_id: str, email: str) -> bool:
        row = self._conn.execute(
            """
            SELECT status FROM sends
            WHERE campaign_id = ? AND email = ?
            """,
            (campaign_id, email),
        ).fetchone()
        return row is not None and row[0] == "sent"

    def record(self, campaign_id: str, email: str, status: str, error: str | None = None) -> None:
        sent_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO sends (campaign_id, email, status, sent_at, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(campaign_id, email) DO UPDATE SET
                status = excluded.status,
                sent_at = excluded.sent_at,
                error = excluded.error
            """,
            (campaign_id, email, status, sent_at, error),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
