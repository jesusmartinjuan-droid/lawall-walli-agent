"""Nominalia-specific email provider.

Nominalia mailboxes are standard IMAP/SMTP mailboxes, so today this is a thin
subclass of `ImapEmailProvider`. It exists as its own class/module so that any
Nominalia-specific behaviour discovered later (custom folder naming, quirky
APPEND handling, rate limits, etc.) has an obvious place to live without
touching the generic IMAP implementation used by other providers.
"""

from app.services.email_provider_service import ImapEmailProvider


class NominaliaEmailProvider(ImapEmailProvider):
    """IMAP provider for Nominalia-hosted mailboxes.

    IMPORTANT: whether Nominalia's IMAP server actually persists APPENDed
    messages as editable drafts (vs. silently accepting and discarding them,
    or rejecting the \\Draft flag) has not been verified against a real
    Nominalia mailbox. Treat `create_draft` results as best-effort; always
    keep `Draft.status` visible in the UI so staff can fall back to writing
    the reply manually if `failed_to_create_in_mailbox` is reported.
    """
