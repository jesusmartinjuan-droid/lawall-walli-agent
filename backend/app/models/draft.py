from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import DraftStatus

if TYPE_CHECKING:
    from app.models.email_message import EmailMessage


class Draft(Base, TimestampMixin):
    """A generated reply draft for a given email, and whether it was written
    back into the mailbox's drafts folder."""

    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False)
    email_message_id: Mapped[int] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False
    )
    prompt_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )

    generated_body: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[DraftStatus] = mapped_column(
        Enum(
            DraftStatus,
            name="draft_status",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DraftStatus.GENERATED,
        nullable=False,
    )
    created_in_mailbox: Mapped[bool] = mapped_column(default=False, nullable=False)
    mailbox_draft_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    email_message: Mapped["EmailMessage"] = relationship(back_populates="drafts")

    def __repr__(self) -> str:
        return f"<Draft id={self.id} status={self.status}>"
