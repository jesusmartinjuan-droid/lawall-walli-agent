from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AgentImage(Base, TimestampMixin):
    """An image staff can configure the agent to embed inline in a generated
    reply. `name` is what the LLM is given as the exact identifier to choose
    when deciding whether to attach an image; `description` tells it (in
    plain language, written by staff) when this particular image applies —
    e.g. "Tabla de precios en español. Usar cuando el cliente pregunte por
    precios y el correo esté en español." New use cases (a different image
    for a different topic) are added entirely from the admin screen, with no
    code change."""

    __tablename__ = "agent_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    def __repr__(self) -> str:
        return f"<AgentImage id={self.id} name={self.name!r}>"
