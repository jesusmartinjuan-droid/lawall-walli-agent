"""Upload/manage lifecycle for images staff configure the agent to embed
inline in generated replies (a price table, an installation diagram, or
whatever comes up next) — each with a name (the exact identifier the LLM
is given to choose from) and a plain-language description of when it
applies. Adding a new use case is entirely a staff action from the admin
screen; no code change is ever needed for it.
"""

import io
import os
import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.agent_image import AgentImage
from app.repositories.agent_image_repository import AgentImageRepository

logger = get_logger(__name__)

_SUPPORTED_PIL_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
_MAX_WIDTH_PX = 1200
_STORAGE_SUBDIR = "agent_images"


class UnsupportedAgentImageError(Exception):
    pass


class DuplicateAgentImageNameError(Exception):
    pass


def _storage_dir() -> str:
    return os.path.join(settings.documents_storage_path, _STORAGE_SUBDIR)


def _process_image(file_bytes: bytes) -> tuple[bytes, str, str]:
    """Validates the upload is a real, decodable image, downsizes it if
    wider than `_MAX_WIDTH_PX`, and returns (processed_bytes, content_type,
    extension) derived from the image's own verified format — never from the
    browser-supplied filename/content-type, which aren't trustworthy."""
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise UnsupportedAgentImageError(
            f"El archivo supera el tamaño máximo permitido ({_MAX_UPLOAD_BYTES // (1024 * 1024)}MB)."
        )

    try:
        probe = Image.open(io.BytesIO(file_bytes))
        probe.verify()
        image = Image.open(io.BytesIO(file_bytes))
        image_format = image.format
    except Exception as exc:
        raise UnsupportedAgentImageError("El archivo no es una imagen válida.") from exc

    if image_format not in _SUPPORTED_PIL_FORMATS:
        raise UnsupportedAgentImageError(f"Formato de imagen no soportado ({image_format}). Usa PNG o JPEG.")

    if image.width > _MAX_WIDTH_PX:
        image.thumbnail((_MAX_WIDTH_PX, _MAX_WIDTH_PX * 100))

    if image_format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    extension = ".png" if image_format == "PNG" else ".jpg"
    return buffer.getvalue(), _SUPPORTED_PIL_FORMATS[image_format], extension


class AgentImageService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AgentImageRepository(db)

    def list_all(self) -> list[AgentImage]:
        return self.repo.list_all()

    def get(self, image_id: int) -> AgentImage | None:
        return self.repo.get(image_id)

    def get_by_name(self, name: str) -> AgentImage | None:
        return self.repo.get_by_name(name)

    def read_bytes(self, image: AgentImage) -> bytes:
        with open(image.storage_path, "rb") as fh:
            return fh.read()

    def create(self, *, name: str, description: str, original_filename: str, file_bytes: bytes) -> AgentImage:
        if self.repo.get_by_name(name) is not None:
            raise DuplicateAgentImageNameError(f"Ya existe una imagen con el nombre '{name}'.")

        processed_bytes, content_type, extension = _process_image(file_bytes)

        os.makedirs(_storage_dir(), exist_ok=True)
        stored_filename = f"{uuid.uuid4().hex}{extension}"
        storage_path = str(Path(_storage_dir()) / stored_filename)
        with open(storage_path, "wb") as fh:
            fh.write(processed_bytes)

        image = AgentImage(
            name=name,
            description=description,
            filename=stored_filename,
            original_filename=original_filename,
            content_type=content_type,
            storage_path=storage_path,
        )
        self.repo.add(image)
        self.repo.commit()
        logger.info("agent_image_created id=%s name=%s", image.id, name)
        return image

    def update_metadata(
        self, image_id: int, *, name: str | None = None, description: str | None = None
    ) -> AgentImage | None:
        image = self.repo.get(image_id)
        if image is None:
            return None
        if name is not None and name != image.name and self.repo.get_by_name(name) is not None:
            raise DuplicateAgentImageNameError(f"Ya existe una imagen con el nombre '{name}'.")
        if name is not None:
            image.name = name
        if description is not None:
            image.description = description
        self.repo.commit()
        self.repo.refresh(image)
        return image

    def delete(self, image_id: int) -> bool:
        image = self.repo.get(image_id)
        if not image:
            return False
        if os.path.exists(image.storage_path):
            try:
                os.remove(image.storage_path)
            except OSError as exc:
                logger.warning("agent_image_file_delete_failed path=%s error=%s", image.storage_path, exc)
        self.repo.delete(image)
        self.repo.commit()
        logger.info("agent_image_deleted id=%s", image_id)
        return True
