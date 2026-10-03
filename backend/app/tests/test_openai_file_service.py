import pytest

from app.services.openai_file_service import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    delete_file,
    upload_bytes,
    validate_file_type,
    validate_upload_size,
)


class _FakeFiles:
    def __init__(self):
        self.created: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []

    def create(self, *, file, purpose):
        filename, content = file
        self.created.append((filename, content))
        assert purpose == "assistants"

        class _FileObj:
            id = "file-123"

        return _FileObj()

    def delete(self, file_id):
        self.deleted.append(file_id)


class _FakeClient:
    def __init__(self):
        self.files = _FakeFiles()


def test_validate_upload_size_accepts_file_under_the_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_file_bytes", 1000)
    validate_upload_size(999)  # must not raise


def test_validate_upload_size_rejects_file_over_the_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_file_bytes", 1000)
    with pytest.raises(FileTooLargeError):
        validate_upload_size(1001)


def test_validate_file_type_accepts_supported_extension():
    validate_file_type("tabla.xlsx")  # must not raise


def test_validate_file_type_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileTypeError):
        validate_file_type("video.mp4")


def test_upload_bytes_calls_files_create_and_returns_file_id():
    client = _FakeClient()
    result = upload_bytes(client=client, filename="manual.docx", content=b"hello")
    assert result.file_id == "file-123"
    assert client.files.created == [("manual.docx", b"hello")]


def test_delete_file_calls_files_delete():
    client = _FakeClient()
    delete_file(client=client, file_id="file-123")
    assert client.files.deleted == ["file-123"]


def test_delete_file_does_nothing_when_file_id_is_none():
    client = _FakeClient()
    delete_file(client=client, file_id=None)
    assert client.files.deleted == []


def test_delete_file_swallows_errors():
    class _FailingFiles(_FakeFiles):
        def delete(self, file_id):
            raise RuntimeError("boom")

    client = _FakeClient()
    client.files = _FailingFiles()
    delete_file(client=client, file_id="file-123")  # must not raise
