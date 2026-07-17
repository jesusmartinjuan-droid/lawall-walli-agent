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
    def __init__(
        self,
        *args,
        uidnext: int = 1,
        search_uids: list[int] | None = None,
        messages: dict[int, bytes] | None = None,
        **kwargs,
    ):
        self.appended_message: bytes | None = None
        self.uidnext = uidnext
        self.search_uids = search_uids or []
        self.messages = messages or {}
        self.search_calls: list[tuple] = []

    def login(self, username, password):
        return "OK", [b"Logged in"]

    def select(self, folder, readonly=False):
        return "OK", [b"1"]

    def status(self, folder, what):
        return "OK", [f'"{folder}" (UIDNEXT {self.uidnext})'.encode()]

    def uid(self, command, *args):
        if command == "search":
            self.search_calls.append(args)
            return "OK", [" ".join(str(uid) for uid in self.search_uids).encode()]
        if command == "fetch":
            uid = int(args[0])
            return "OK", [(b"1 (RFC822 {0}", self.messages[uid])]
        raise AssertionError(f"unexpected uid command: {command}")

    def append(self, folder, flags, date, message_bytes):
        self.appended_message = message_bytes
        return "OK", [b"[APPENDUID 1 1] Append completed."]

    def logout(self):
        return "BYE", [b"Logging out"]


def _raw_email_bytes(uid: int) -> bytes:
    return (
        f"From: cliente@example.com\r\n"
        f"To: soporte@lawall.local\r\n"
        f"Subject: Consulta {uid}\r\n"
        f"Message-ID: <msg-{uid}@example.com>\r\n"
        f"Date: Mon, 1 Jan 2026 10:00:00 +0000\r\n"
        f"\r\n"
        f"Hola\r\n"
    ).encode()


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


def test_get_latest_uid_returns_uidnext_minus_one(monkeypatch):
    fake_connection = _FakeImapConnection(uidnext=43)
    provider = _make_provider(monkeypatch, fake_connection)

    assert provider.get_latest_uid() == 42


def test_get_latest_uid_returns_zero_for_empty_mailbox(monkeypatch):
    fake_connection = _FakeImapConnection(uidnext=1)
    provider = _make_provider(monkeypatch, fake_connection)

    assert provider.get_latest_uid() == 0


def test_fetch_new_emails_without_min_uid_searches_all(monkeypatch):
    fake_connection = _FakeImapConnection(
        search_uids=[1, 2], messages={1: _raw_email_bytes(1), 2: _raw_email_bytes(2)}
    )
    provider = _make_provider(monkeypatch, fake_connection)

    results = provider.fetch_new_emails(known_uids=set(), max_emails=20)

    assert [r.imap_uid for r in results] == [1, 2]
    assert fake_connection.search_calls == [(None, "ALL")]


def test_fetch_new_emails_with_min_uid_searches_uid_range(monkeypatch):
    fake_connection = _FakeImapConnection(search_uids=[43], messages={43: _raw_email_bytes(43)})
    provider = _make_provider(monkeypatch, fake_connection)

    results = provider.fetch_new_emails(known_uids=set(), max_emails=20, min_uid=43)

    assert [r.imap_uid for r in results] == [43]
    assert fake_connection.search_calls == [(None, "UID", "43:*")]
