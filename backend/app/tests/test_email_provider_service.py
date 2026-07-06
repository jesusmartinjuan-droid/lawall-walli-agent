"""`ImapEmailProvider.create_draft` threading headers, verified without any
real network access by faking the `imaplib.IMAP4_SSL` connection and
inspecting the exact bytes it would have APPENDed to the mailbox."""

import email as email_lib
from datetime import UTC, datetime

from app.services.email_provider_service import (
    FetchedEmail,
    ImapCredentials,
    ImapEmailProvider,
    _extract_bodies,
)


class _FakeImapConnection:
    def __init__(self, *args, **kwargs):
        self.appended_message: bytes | None = None

    def login(self, username, password):
        return "OK", [b"Logged in"]

    def append(self, folder, flags, date, message_bytes):
        self.appended_message = message_bytes
        return "OK", [b"[APPENDUID 1 1] Append completed."]

    def logout(self):
        return "BYE", [b"Logging out"]


def _make_provider(monkeypatch, fake_connection: _FakeImapConnection) -> ImapEmailProvider:
    monkeypatch.setattr(
        "app.services.email_provider_service.imaplib.IMAP4_SSL",
        lambda host, port: fake_connection,
    )
    credentials = ImapCredentials(
        host="imap.example.com", port=993, username="soporte@lawall.local", password="secret"
    )
    return ImapEmailProvider(credentials)


def _fetched_email(**overrides) -> FetchedEmail:
    defaults = dict(
        imap_uid=1,
        external_message_id="<parent@example.com>",
        external_thread_id=None,
        sender="cliente@example.com",
        recipients="soporte@lawall.local",
        subject="Consulta",
        body_text="Hola",
        body_html=None,
        received_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return FetchedEmail(**defaults)


def test_create_draft_sets_own_message_id(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    result = provider.create_draft(subject="Consulta", body="Respuesta", in_reply_to=_fetched_email())

    assert result.success
    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert parsed["Message-ID"] is not None
    assert parsed["Message-ID"].endswith("@lawall.local>")


def test_create_draft_references_falls_back_to_single_parent_when_no_history(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    provider.create_draft(subject="Consulta", body="Respuesta", in_reply_to=_fetched_email())

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert parsed["In-Reply-To"] == "<parent@example.com>"
    assert " ".join(parsed["References"].split()) == "<parent@example.com>"


def test_create_draft_references_includes_full_chain(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    chain = ["<msg1@example.com>", "<msg2@example.com>", "<parent@example.com>"]
    provider.create_draft(
        subject="Consulta",
        body="Respuesta",
        in_reply_to=_fetched_email(references_chain=chain),
    )

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert " ".join(parsed["References"].split()) == " ".join(chain)
    assert parsed["In-Reply-To"] == "<parent@example.com>"


def test_create_draft_replies_to_sender_with_re_subject(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    provider.create_draft(subject="Consulta", body="Respuesta", in_reply_to=_fetched_email())

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert parsed["To"] == "cliente@example.com"
    assert parsed["Subject"] == "Re: Consulta"


def test_create_draft_quotes_original_email_in_plain_text_and_html(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    original = _fetched_email(
        sender="cliente@example.com",
        body_text="Hola,\n¿cuál es el precio?",
        body_html="<p>Hola,</p><p>¿cuál es el precio?</p>",
        received_at=datetime(2026, 7, 2, 17, 33, tzinfo=UTC),
    )
    provider.create_draft(subject="Consulta", body="Aquí tienes el precio.", in_reply_to=original)

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert parsed.is_multipart()
    body_text, body_html = _extract_bodies(parsed)

    assert "Aquí tienes el precio." in body_text
    assert "El 2026-07-02 17:33, cliente@example.com escribió:" in body_text
    assert "> Hola," in body_text
    assert "> ¿cuál es el precio?" in body_text

    assert "Aquí tienes el precio." in body_html
    assert "<blockquote>" in body_html
    assert "<p>Hola,</p><p>¿cuál es el precio?</p>" in body_html


def test_create_draft_uses_placeholder_when_original_has_no_text_body(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    original = _fetched_email(body_text=None, body_html=None)
    provider.create_draft(subject="Consulta", body="Respuesta", in_reply_to=original)

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    body_text, body_html = _extract_bodies(parsed)

    assert "Correo original sin contenido de texto" in body_text
    assert "Correo original sin contenido de texto" in body_html
