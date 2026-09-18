"""`ImapEmailProvider.create_draft` threading headers, verified without any
real network access by faking the `imaplib.IMAP4_SSL` connection and
inspecting the exact bytes it would have APPENDed to the mailbox."""

import email as email_lib
import io
from datetime import UTC, datetime

from PIL import Image

from app.services.email_provider_service import (
    FetchedEmail,
    ImapCredentials,
    ImapEmailProvider,
    InlineImage,
    _extract_bodies,
)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


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


def _raw_email_bytes_with_folded_subject(uid: int) -> bytes:
    """A Subject header wrapped across two physical lines, the way a real
    sending server folds long headers (RFC 2822 line-continuation: the
    continuation line starts with whitespace). The legacy `compat32` email
    policy leaves the internal "\\r\\n" in the parsed value instead of fully
    unfolding it — this is the exact shape that used to crash `create_draft`
    with "Header values may not contain linefeed or carriage return
    characters" for any reply built from this message."""
    return (
        f"From: cliente@example.com\r\n"
        f"To: soporte@lawall.local\r\n"
        f"Subject: Consulta {uid} sobre un pedido con un asunto muy largo que el\r\n"
        f" servidor decide partir en dos lineas\r\n"
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


def test_create_draft_with_inline_image_embeds_it_as_cid_not_attachment(monkeypatch):
    """Mandatory smoke test for the add_related()/cid: mechanics — no prior
    usage of this exists anywhere in the codebase, so this proves the
    resulting MIME structure is what a mail client would actually render
    (an inline image, not a file attachment) before anything downstream is
    wired to depend on it."""
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)
    image_bytes = _png_bytes()
    inline_image = InlineImage(content=image_bytes, content_type="image/png", filename="tabla.png")

    result = provider.create_draft(
        subject="Consulta",
        body="Aquí tienes la tabla.",
        in_reply_to=_fetched_email(),
        inline_image=inline_image,
    )

    assert result.success
    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    assert parsed.is_multipart()

    image_parts = [part for part in parsed.walk() if part.get_content_type() == "image/png"]
    assert len(image_parts) == 1
    image_part = image_parts[0]

    # Embedded inline (Content-ID reference), never as a file attachment.
    assert "attachment" not in str(image_part.get("Content-Disposition") or "")
    assert image_part.get_payload(decode=True) == image_bytes

    content_id = image_part.get("Content-ID")
    assert content_id is not None
    bare_cid = content_id.strip("<>")

    html_parts = [part for part in parsed.walk() if part.get_content_type() == "text/html"]
    assert len(html_parts) == 1
    html_text = html_parts[0].get_payload(decode=True).decode("utf-8")
    assert f"cid:{bare_cid}" in html_text

    plain_parts = [part for part in parsed.walk() if part.get_content_type() == "text/plain"]
    assert len(plain_parts) == 1
    plain_text = plain_parts[0].get_payload(decode=True).decode("utf-8")
    assert "cid:" not in plain_text


def test_create_draft_without_inline_image_attaches_nothing(monkeypatch):
    fake_connection = _FakeImapConnection()
    provider = _make_provider(monkeypatch, fake_connection)

    provider.create_draft(subject="Consulta", body="Respuesta", in_reply_to=_fetched_email())

    parsed = email_lib.message_from_bytes(fake_connection.appended_message)
    image_parts = [part for part in parsed.walk() if part.get_content_maintype() == "image"]
    assert image_parts == []


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


def test_fetch_new_emails_unfolds_a_subject_wrapped_across_two_lines(monkeypatch):
    fake_connection = _FakeImapConnection(
        search_uids=[1], messages={1: _raw_email_bytes_with_folded_subject(1)}
    )
    provider = _make_provider(monkeypatch, fake_connection)

    [fetched] = provider.fetch_new_emails(known_uids=set(), max_emails=20)

    assert "\r" not in fetched.subject
    assert "\n" not in fetched.subject
    assert fetched.subject == (
        "Consulta 1 sobre un pedido con un asunto muy largo que el servidor decide partir en dos lineas"
    )


def test_create_draft_succeeds_when_original_subject_was_folded_across_lines(monkeypatch):
    """Regression test for the production bug: replying to an email whose
    Subject the sending server wrapped across two lines used to raise
    ValueError("Header values may not contain linefeed or carriage return
    characters") when APPENDing the draft, because the folded "\\r\\n" was
    still embedded in `in_reply_to.subject`."""
    fetch_connection = _FakeImapConnection(
        search_uids=[1], messages={1: _raw_email_bytes_with_folded_subject(1)}
    )
    fetch_provider = _make_provider(monkeypatch, fetch_connection)
    [fetched] = fetch_provider.fetch_new_emails(known_uids=set(), max_emails=20)

    draft_connection = _FakeImapConnection()
    draft_provider = _make_provider(monkeypatch, draft_connection)

    result = draft_provider.create_draft(subject=fetched.subject, body="Respuesta", in_reply_to=fetched)

    assert result.success
    parsed = email_lib.message_from_bytes(draft_connection.appended_message)
    # `email`'s generator may re-fold a long header on output (valid, RFC 2822
    # behavior) — normalize whitespace the same way the References tests
    # above do, since the fix is about the crash, not the exact fold points.
    assert " ".join(parsed["Subject"].split()) == (
        "Re: Consulta 1 sobre un pedido con un asunto muy largo que el servidor decide partir en dos lineas"
    )
