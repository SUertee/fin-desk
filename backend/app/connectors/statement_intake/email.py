"""Read-only IMAP adapter that emits supported statement attachments."""

from __future__ import annotations

import email
import imaplib
from email.header import decode_header, make_header
from email.utils import getaddresses

from app.config.settings import StatementIngestionSettings
from app.connectors.statement_intake.contracts import StatementCandidate

_SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".pdf")


class StatementEmailConnector:
    def __init__(self, settings: StatementIngestionSettings):
        self.settings = settings

    def test_connection(self, mailbox: str) -> dict[str, object]:
        with self._client() as client:
            status, _ = client.select(mailbox, readonly=True)
            if status != "OK":
                raise RuntimeError(f"Cannot open mailbox {mailbox}")
        return {"ok": True, "mailbox": mailbox, "host": self.settings.email_host}

    def fetch_candidates(
        self,
        *,
        user_id: str,
        mailbox: str,
        allowed_senders: list[str],
    ) -> list[StatementCandidate]:
        allowlist = {item.lower() for item in allowed_senders}
        if not allowlist:
            return []
        candidates: list[StatementCandidate] = []
        with self._client() as client:
            status, _ = client.select(mailbox, readonly=True)
            if status != "OK":
                raise RuntimeError(f"Cannot open mailbox {mailbox}")
            status, data = client.uid("search", None, "UNSEEN")
            if status != "OK" or not data:
                return []
            for uid in data[0].split()[-20:]:
                status, payload = client.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK" or not payload:
                    continue
                raw = next(
                    (item[1] for item in payload if isinstance(item, tuple)),
                    None,
                )
                if not raw:
                    continue
                message = email.message_from_bytes(raw)
                sender = _sender_address(message.get("From", ""))
                if sender not in allowlist:
                    continue
                message_id = message.get("Message-ID", "").strip() or uid.decode()
                subject = str(make_header(decode_header(message.get("Subject", ""))))
                for index, part in enumerate(message.walk()):
                    filename = part.get_filename()
                    if not filename:
                        continue
                    filename = str(make_header(decode_header(filename)))
                    if not filename.lower().endswith(_SUPPORTED_EXTENSIONS):
                        continue
                    content = part.get_payload(decode=True)
                    if not content:
                        continue
                    candidates.append(
                        StatementCandidate(
                            user_id=user_id,
                            filename=filename,
                            content=content,
                            channel="email",
                            origin_key=f"{message_id}:{index}:{filename}",
                            origin_metadata={
                                "sender": sender,
                                "subject": subject,
                                "message_id": message_id,
                            },
                        )
                    )
        return candidates

    def _client(self):
        if not self.settings.email_available:
            raise RuntimeError("Statement email credentials are not configured")
        client_class = imaplib.IMAP4_SSL if self.settings.email_use_ssl else imaplib.IMAP4
        client = client_class(
            self.settings.email_host,
            self.settings.email_port,
            timeout=15,
        )
        client.login(self.settings.email_username, self.settings.email_password)
        return client


def _sender_address(value: str) -> str:
    addresses = getaddresses([value])
    return addresses[0][1].strip().lower() if addresses else ""
