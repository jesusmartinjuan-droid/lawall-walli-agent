"""Idempotent seed script: creates the initial admin user and default prompt.

Run inside the backend container (or locally with the venv active and the
right DATABASE_URL/ENCRYPTION_KEY):

    python -m scripts.seed
    # also adds a mock mailbox + processed email for the history screen:
    python -m scripts.seed --with-demo-data
"""

import argparse
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.encryption import encrypt_value
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password

# See app/main.py for why this must be imported before any ORM usage.
from app.db import base_all  # noqa: F401
from app.db.session import SessionLocal
from app.models.draft import Draft
from app.models.email_message import EmailMessage
from app.models.enums import (
    DraftStatus,
    MailboxProvider,
    ProcessingLogStatus,
    ProcessingStep,
    UserRole,
)
from app.models.mailbox import Mailbox
from app.models.processing_log import ProcessingLog
from app.models.prompt import PromptTemplate
from app.models.user import User
from app.repositories.mailbox_repository import MailboxRepository
from app.repositories.prompt_repository import PromptRepository
from app.repositories.user_repository import UserRepository
from app.services.prompt_service import PromptService

configure_logging()
logger = get_logger(__name__)


def seed_admin_user(db) -> None:
    users = UserRepository(db)
    if users.get_by_email(settings.initial_admin_email.lower()):
        logger.info("seed_admin_user_already_exists email=%s", settings.initial_admin_email)
        return

    user = User(
        email=settings.initial_admin_email.lower(),
        full_name=settings.initial_admin_full_name,
        hashed_password=hash_password(settings.initial_admin_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    users.add(user)
    users.commit()
    logger.info("seed_admin_user_created email=%s", settings.initial_admin_email)


def seed_default_prompt(db) -> None:
    prompts = PromptRepository(db)
    if prompts.get_default():
        logger.info("seed_default_prompt_already_exists")
        return

    prompt = PromptTemplate(
        name="Prompt base de laWALL",
        description="Prompt inicial usado para generar borradores de respuesta a clientes.",
        content=PromptService.default_prompt_content(),
        is_active=True,
        is_default=True,
    )
    prompts.add(prompt)
    prompts.commit()
    logger.info("seed_default_prompt_created id=%s", prompt.id)


def seed_demo_data(db) -> None:
    """Optional mock mailbox + processed email so the history screens aren't empty
    on a fresh install. Never enabled by default."""
    mailboxes = MailboxRepository(db)
    if mailboxes.get_by_email_address("demo@lawall.local"):
        logger.info("seed_demo_data_already_exists")
        return

    mailbox = Mailbox(
        name="Buzón de demostración",
        email_address="demo@lawall.local",
        provider=MailboxProvider.NOMINALIA,
        imap_host="imap.example.invalid",
        imap_port=993,
        imap_username="demo@lawall.local",
        encrypted_imap_password=encrypt_value("placeholder-not-a-real-password"),
        imap_use_ssl=True,
        inbox_folder="INBOX",
        drafts_folder="Drafts",
        is_active=False,
    )
    mailboxes.add(mailbox)
    mailboxes.commit()

    received_at = datetime.now(UTC) - timedelta(hours=2)
    message = EmailMessage(
        mailbox_id=mailbox.id,
        thread_id=None,
        external_message_id="<demo-message-1@lawall.local>",
        imap_uid=1,
        sender="cliente.demo@example.com",
        recipients=mailbox.email_address,
        subject="Consulta sobre disponibilidad",
        body_text="Hola, quería saber si tienen disponibilidad para la próxima semana. Gracias.",
        body_html=None,
        received_at=received_at,
        processed_at=received_at + timedelta(minutes=1),
        created_at=received_at,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    prompt = PromptRepository(db).get_default()
    draft = Draft(
        mailbox_id=mailbox.id,
        email_message_id=message.id,
        prompt_template_id=prompt.id if prompt else None,
        generated_body=(
            "Hola,\n\nGracias por tu mensaje. Estamos consultando la disponibilidad para la "
            "semana solicitada y te confirmaremos en breve.\n\nUn saludo,\nEquipo laWALL"
        ),
        llm_provider="mock",
        llm_model="mock-1",
        input_tokens=42,
        output_tokens=38,
        estimated_cost=0.0,
        status=DraftStatus.GENERATED,
        created_in_mailbox=False,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)

    log = ProcessingLog(
        mailbox_id=mailbox.id,
        email_message_id=message.id,
        draft_id=draft.id,
        status=ProcessingLogStatus.SUCCESS,
        step=ProcessingStep.FINALIZE,
        retry_count=0,
        finished_at=message.processed_at,
    )
    db.add(log)
    db.commit()

    logger.info(
        "seed_demo_data_created mailbox_id=%s message_id=%s draft_id=%s",
        mailbox.id,
        message.id,
        draft.id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Walli's initial data.")
    parser.add_argument("--with-demo-data", action="store_true", help="Also insert mock processing history.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_admin_user(db)
        seed_default_prompt(db)
        if args.with_demo_data:
            seed_demo_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
