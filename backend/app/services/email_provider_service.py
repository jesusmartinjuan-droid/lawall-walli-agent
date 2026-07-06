"""Abstraction over "a mailbox we can read email from and write drafts to".

Reading uses IMAP, which is well standardised. Writing a draft is done by
APPENDing an RFC822 message with the \\Draft flag into the mailbox's drafts
folder — this is the closest thing to a standard "create draft" operation
over IMAP. Whether the resulting message shows up as a proper, editable draft
in the mail client depends entirely on the IMAP server's behavior; Nominalia's
exact support for this has not been verified, so `create_draft` reports
success/failure explicitly and callers must treat it as best-effort.

Concrete providers:
- `ImapEmailProvider`: generic IMAP implementation, works against any RFC
  3501-compliant server.
- `NominaliaEmailProvider` (see nominalia_email_provider.py): thin subclass
  reserved for Nominalia-specific quirks/workarounds as they're discovered.
"""

from __future__ import annotations

import email as email_lib
import html as html_lib
import imaplib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header
from email.message import EmailMessage as PyEmailMessage
from email.utils import make_msgid, parsedate_to_datetime

from app.core.logging import get_logger
from app.core.retry import with_retry

logger = get_logger(__name__)


@dataclass
class ImapCredentials:
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True
    inbox_folder: str = "INBOX"
    drafts_folder: str = "Drafts"


@dataclass
class FetchedEmail:
    imap_uid: int
    external_message_id: str
    external_thread_id: str | None
    sender: str
    recipients: str
    subject: str
    body_text: str | None
    body_html: str | None
    received_at: datetime
    raw_headers: dict[str, str] = field(default_factory=dict)
    # Message-IDs of every prior message in the thread, oldest first, ending
    # with `external_message_id` itself. Used to build a complete `References`
    # header (RFC 2822) instead of only pointing at the immediate parent, so
    # strict clients (Outlook/Thunderbird) can rebuild the full conversation
    # tree. Empty when there is no thread history.
    references_chain: list[str] = field(default_factory=list)


@dataclass
class DraftCreationResult:
    success: bool
    mailbox_draft_id: str | None
    message: str


class EmailProviderError(Exception):
    pass


class EmailProvider(ABC):
    """Interface every mailbox backend must implement."""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]: ...

    @abstractmethod
    def fetch_new_emails(self, known_uids: set[int], max_emails: int) -> list[FetchedEmail]:
        """Return up to `max_emails` messages from the inbox whose UID is not in `known_uids`."""

    @abstractmethod
    def create_draft(self, *, subject: str, body: str, in_reply_to: FetchedEmail) -> DraftCreationResult:
        """Best-effort creation of a draft reply in the mailbox's drafts folder."""


_NO_TEXT_BODY_PLACEHOLDER = "(Correo original sin contenido de texto.)"


def _build_reply_bodies(*, generated_reply: str, original: FetchedEmail) -> tuple[str, str]:
    """Returns (plain_text_body, html_body) with the original email quoted
    underneath the generated reply — matching the standard "On <date>, <sender>
    wrote:" + quoted-body convention every mail client (including Nominalia's
    webmail) uses when you hit Reply, so the draft looks the same either way."""
    attribution = f"El {original.received_at.strftime('%Y-%m-%d %H:%M')}, {original.sender} escribió:"

    quoted_text = "\n".join(f"> {line}" for line in (original.body_text or "").splitlines())
    plain_body = f"{generated_reply}\n\n{attribution}\n\n{quoted_text or '> ' + _NO_TEXT_BODY_PLACEHOLDER}"

    reply_html = html_lib.escape(generated_reply).replace("\n", "<br>")
    if original.body_html:
        quoted_html = original.body_html
    elif original.body_text:
        quoted_html = html_lib.escape(original.body_text).replace("\n", "<br>")
    else:
        quoted_html = html_lib.escape(_NO_TEXT_BODY_PLACEHOLDER)
    html_body = f"<p>{reply_html}</p><p>{html_lib.escape(attribution)}</p><blockquote>{quoted_html}</blockquote>"

    return plain_body, html_body


def _decode_mime_words(raw: str | None) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = ""
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded += text.decode(charset or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


class ImapEmailProvider(EmailProvider):
    def __init__(self, credentials: ImapCredentials):
        self.credentials = credentials

    def _connect(self) -> imaplib.IMAP4:
        creds = self.credentials
        conn: imaplib.IMAP4
        if creds.use_ssl:
            conn = imaplib.IMAP4_SSL(creds.host, creds.port)
        else:
            conn = imaplib.IMAP4(creds.host, creds.port)
        conn.login(creds.username, creds.password)
        return conn

    def test_connection(self) -> tuple[bool, str]:
        try:
            conn = with_retry(self._connect, exceptions=(OSError, imaplib.IMAP4.error), max_attempts=2)
            try:
                conn.select(self.credentials.inbox_folder, readonly=True)
                conn.logout()
            except Exception:
                pass
            return True, "Connection successful."
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a message
            logger.warning("imap_test_connection_failed host=%s error=%s", self.credentials.host, exc)
            return False, f"Could not connect: {exc}"

    def fetch_new_emails(self, known_uids: set[int], max_emails: int) -> list[FetchedEmail]:
        conn = with_retry(self._connect, exceptions=(OSError, imaplib.IMAP4.error))
        try:
            conn.select(self.credentials.inbox_folder, readonly=True)
            status, data = conn.uid("search", None, "ALL")
            if status != "OK":
                raise EmailProviderError(f"IMAP search failed: {status}")

            all_uids = [int(uid) for uid in data[0].split()] if data and data[0] else []
            new_uids = [uid for uid in all_uids if uid not in known_uids]
            new_uids.sort()
            new_uids = new_uids[:max_emails]

            results: list[FetchedEmail] = []
            for uid in new_uids:
                fetched = self._fetch_one(conn, uid)
                if fetched:
                    results.append(fetched)
            return results
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _fetch_one(self, conn: imaplib.IMAP4, uid: int) -> FetchedEmail | None:
        status, msg_data = conn.uid("fetch", str(uid), "(RFC822)")
        if status != "OK" or not msg_data or msg_data[0] is None:
            logger.warning("imap_fetch_uid_failed uid=%s status=%s", uid, status)
            return None

        raw_bytes = msg_data[0][1]
        parsed = email_lib.message_from_bytes(raw_bytes)

        subject = _decode_mime_words(parsed.get("Subject"))
        sender = _decode_mime_words(parsed.get("From"))
        recipients = _decode_mime_words(parsed.get("To"))
        message_id = parsed.get("Message-ID") or f"<no-message-id-{uid}@unknown>"
        in_reply_thread = parsed.get("References") or parsed.get("In-Reply-To")

        date_header = parsed.get("Date")
        try:
            received_at = parsedate_to_datetime(date_header) if date_header else datetime.utcnow()
        except (TypeError, ValueError):
            received_at = datetime.utcnow()

        body_text, body_html = _extract_bodies(parsed)

        return FetchedEmail(
            imap_uid=uid,
            external_message_id=message_id,
            external_thread_id=in_reply_thread.split()[0] if in_reply_thread else message_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            raw_headers=dict(parsed.items()),
        )

    def create_draft(self, *, subject: str, body: str, in_reply_to: FetchedEmail) -> DraftCreationResult:
        """Append an RFC822 draft message into the mailbox's drafts folder.

        NOTE: Real-world support for this varies by IMAP server. Some servers
        (Nominalia included, unverified at the time of writing) may reject
        APPEND to the drafts folder, ignore the \\Draft flag, or require a
        specific mailbox path. Failures here are expected and handled by the
        caller as `failed_to_create_in_mailbox`, not treated as fatal errors
        for the overall processing pipeline.
        """
        try:
            references = " ".join(in_reply_to.references_chain) or in_reply_to.external_message_id
            domain = self.credentials.username.rsplit("@", 1)[-1]

            message = PyEmailMessage()
            message["Subject"] = f"Re: {in_reply_to.subject}" if not subject.startswith("Re:") else subject
            message["From"] = self.credentials.username
            message["To"] = in_reply_to.sender
            message["Message-ID"] = make_msgid(domain=domain)
            message["In-Reply-To"] = in_reply_to.external_message_id
            message["References"] = references
            plain_body, html_body = _build_reply_bodies(generated_reply=body, original=in_reply_to)
            message.set_content(plain_body)
            message.add_alternative(html_body, subtype="html")

            def _append() -> str:
                conn = self._connect()
                try:
                    status, response = conn.append(
                        self.credentials.drafts_folder,
                        r"(\Draft)",
                        imaplib.Time2Internaldate(datetime.utcnow().timestamp()),
                        message.as_bytes(),
                    )
                    if status != "OK":
                        raise EmailProviderError(f"IMAP APPEND failed: {status} {response}")
                    return str(response)
                finally:
                    try:
                        conn.logout()
                    except Exception:
                        pass

            response = with_retry(_append, exceptions=(OSError, imaplib.IMAP4.error, EmailProviderError))
            return DraftCreationResult(success=True, mailbox_draft_id=response, message="Draft created.")
        except Exception as exc:  # noqa: BLE001 - reported back as a structured failure
            logger.error("create_draft_failed mailbox=%s error=%s", self.credentials.username, exc)
            return DraftCreationResult(success=False, mailbox_draft_id=None, message=str(exc))


def _extract_bodies(parsed: email_lib.message.Message) -> tuple[str | None, str | None]:
    body_text: str | None = None
    body_html: str | None = None

    if parsed.is_multipart():
        for part in parsed.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain" and body_text is None:
                body_text = decoded
            elif content_type == "text/html" and body_html is None:
                body_html = decoded
    else:
        try:
            payload = parsed.get_payload(decode=True)
        except Exception:
            payload = None
        if payload is not None:
            charset = parsed.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if parsed.get_content_type() == "text/html":
                body_html = decoded
            else:
                body_text = decoded

    return body_text, body_html
