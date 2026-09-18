import io
import os

import pytest
from PIL import Image

from app.services.agent_image_service import (
    AgentImageService,
    DuplicateAgentImageNameError,
    UnsupportedAgentImageError,
)


def _png_bytes(width: int = 10, height: int = 10) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_create_stores_a_new_row_and_file(db_session):
    service = AgentImageService(db_session)

    image = service.create(
        name="Tabla de precios (Español)",
        description="Usar cuando el cliente pregunte por precios y el correo esté en español.",
        original_filename="tabla.png",
        file_bytes=_png_bytes(),
    )

    assert image.name == "Tabla de precios (Español)"
    assert image.content_type == "image/png"
    assert os.path.exists(image.storage_path)
    assert service.get_by_name("Tabla de precios (Español)").id == image.id


def test_create_rejects_a_duplicate_name(db_session):
    service = AgentImageService(db_session)
    service.create(
        name="Tabla de precios (Español)",
        description="...",
        original_filename="a.png",
        file_bytes=_png_bytes(),
    )

    with pytest.raises(DuplicateAgentImageNameError):
        service.create(
            name="Tabla de precios (Español)",
            description="otra descripción",
            original_filename="b.png",
            file_bytes=_png_bytes(),
        )


def test_create_rejects_non_image_bytes(db_session):
    service = AgentImageService(db_session)

    with pytest.raises(UnsupportedAgentImageError):
        service.create(
            name="Fake", description="...", original_filename="fake.png", file_bytes=b"not an image"
        )

    assert service.list_all() == []


def test_create_rejects_oversized_files(db_session):
    service = AgentImageService(db_session)
    huge = _png_bytes() + b"\x00" * (3 * 1024 * 1024)

    with pytest.raises(UnsupportedAgentImageError):
        service.create(name="Huge", description="...", original_filename="huge.png", file_bytes=huge)


def test_create_downsizes_images_wider_than_the_max_width(db_session):
    service = AgentImageService(db_session)

    image = service.create(
        name="Wide", description="...", original_filename="wide.png", file_bytes=_png_bytes(2000, 1000)
    )

    stored = Image.open(io.BytesIO(service.read_bytes(image)))
    assert stored.width == 1200
    assert stored.height == 600


def test_update_metadata_renames_and_redescribes(db_session):
    service = AgentImageService(db_session)
    image = service.create(
        name="Old name", description="old description", original_filename="a.png", file_bytes=_png_bytes()
    )

    updated = service.update_metadata(image.id, name="New name", description="new description")

    assert updated.name == "New name"
    assert updated.description == "new description"
    assert service.get_by_name("Old name") is None
    assert service.get_by_name("New name").id == image.id


def test_update_metadata_rejects_renaming_to_an_existing_name(db_session):
    service = AgentImageService(db_session)
    service.create(name="A", description="...", original_filename="a.png", file_bytes=_png_bytes())
    image_b = service.create(name="B", description="...", original_filename="b.png", file_bytes=_png_bytes())

    with pytest.raises(DuplicateAgentImageNameError):
        service.update_metadata(image_b.id, name="A")


def test_update_metadata_returns_none_when_image_missing(db_session):
    service = AgentImageService(db_session)
    assert service.update_metadata(999, name="X") is None


def test_delete_removes_row_and_file(db_session):
    service = AgentImageService(db_session)
    image = service.create(name="A", description="...", original_filename="a.png", file_bytes=_png_bytes())
    path = image.storage_path

    assert service.delete(image.id) is True
    assert service.get(image.id) is None
    assert not os.path.exists(path)


def test_delete_returns_false_when_nothing_to_delete(db_session):
    service = AgentImageService(db_session)
    assert service.delete(999) is False
