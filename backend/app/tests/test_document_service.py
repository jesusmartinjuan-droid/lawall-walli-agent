import pytest

from app.services.document_service import DocumentService
from app.services.openai_file_service import UnsupportedFileTypeError


class _FakeFileObj:
    id = "file-abc"


class _FakeFiles:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.deleted: list[str] = []

    def create(self, *, file, purpose):
        if self.fail:
            raise RuntimeError("openai is down")
        return _FakeFileObj()

    def delete(self, file_id):
        self.deleted.append(file_id)


class _FakeClient:
    def __init__(self, *, fail: bool = False):
        self.files = _FakeFiles(fail=fail)


def test_upload_persists_size_and_openai_file_id(db_session, monkeypatch):
    monkeypatch.setattr("app.services.document_service.get_openai_client", lambda: _FakeClient())
    service = DocumentService(db_session)

    document = service.upload(
        original_filename="manual.docx", content_type="application/octet-stream", file_bytes=b"hello world"
    )

    assert document.size_bytes == len(b"hello world")
    assert document.openai_file_id == "file-abc"
    assert document.openai_upload_error is None


def test_upload_records_error_when_openai_upload_fails(db_session, monkeypatch):
    monkeypatch.setattr("app.services.document_service.get_openai_client", lambda: _FakeClient(fail=True))
    service = DocumentService(db_session)

    document = service.upload(
        original_filename="manual.docx", content_type="application/octet-stream", file_bytes=b"hello"
    )

    assert document.openai_file_id is None
    assert "openai is down" in document.openai_upload_error


def test_upload_rejects_unsupported_file_type(db_session):
    service = DocumentService(db_session)
    with pytest.raises(UnsupportedFileTypeError):
        service.upload(original_filename="video.mp4", content_type="video/mp4", file_bytes=b"hello")


def test_delete_calls_openai_delete_with_stored_file_id(db_session, monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr("app.services.document_service.get_openai_client", lambda: client)
    service = DocumentService(db_session)
    document = service.upload(
        original_filename="manual.docx", content_type="application/octet-stream", file_bytes=b"hello"
    )

    assert service.delete(document.id) is True
    assert client.files.deleted == ["file-abc"]
