from app.services.drive_source_service import DriveSourceService
from app.services.drive_sync import DownloadedDriveFile, DriveDownloadError
from app.services.openai_file_service import FileTooLargeError


class _FakeFileObj:
    def __init__(self, file_id: str):
        self.id = file_id


class _FakeFiles:
    def __init__(self):
        self.created: list[bytes] = []
        self.deleted: list[str] = []
        self._next_id = 1

    def create(self, *, file, purpose):
        _filename, content = file
        self.created.append(content)
        file_obj = _FakeFileObj(f"file-{self._next_id}")
        self._next_id += 1
        return file_obj

    def delete(self, file_id):
        self.deleted.append(file_id)


class _FakeClient:
    def __init__(self):
        self.files = _FakeFiles()


def _patch_client(monkeypatch, client):
    monkeypatch.setattr("app.services.drive_source_service.get_openai_client", lambda: client)


def test_create_uploads_file_and_sets_hash(db_session, monkeypatch):
    client = _FakeClient()
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(
        "app.services.drive_source_service.download_drive_file",
        lambda url: DownloadedDriveFile(content=b"hello", filename="tabla.xlsx", content_type="x"),
    )

    service = DriveSourceService(db_session)
    drive_source = service.create(
        name="Tabla de precios", drive_url="https://drive.google.com/file/d/abc/view"
    )

    assert drive_source.openai_file_id == "file-1"
    assert drive_source.content_hash is not None
    assert drive_source.last_sync_error is None
    assert client.files.created == [b"hello"]


def test_sync_is_a_noop_when_content_is_unchanged(db_session, monkeypatch):
    client = _FakeClient()
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(
        "app.services.drive_source_service.download_drive_file",
        lambda url: DownloadedDriveFile(content=b"same bytes", filename="tabla.xlsx", content_type="x"),
    )
    service = DriveSourceService(db_session)
    drive_source = service.create(name="Tabla", drive_url="https://drive.google.com/file/d/abc/view")
    assert len(client.files.created) == 1

    service.sync(drive_source)

    assert len(client.files.created) == 1  # no second upload


def test_sync_reuploads_and_deletes_stale_file_when_content_changed(db_session, monkeypatch):
    client = _FakeClient()
    _patch_client(monkeypatch, client)
    responses = iter(
        [
            DownloadedDriveFile(content=b"version one", filename="tabla.xlsx", content_type="x"),
            DownloadedDriveFile(content=b"version two", filename="tabla.xlsx", content_type="x"),
        ]
    )
    monkeypatch.setattr("app.services.drive_source_service.download_drive_file", lambda url: next(responses))
    service = DriveSourceService(db_session)
    drive_source = service.create(name="Tabla", drive_url="https://drive.google.com/file/d/abc/view")
    first_file_id = drive_source.openai_file_id

    service.sync(drive_source)

    assert drive_source.openai_file_id == "file-2"
    assert drive_source.openai_file_id != first_file_id
    assert client.files.deleted == [first_file_id]


def test_sync_stores_error_without_raising_when_download_fails(db_session, monkeypatch):
    _patch_client(monkeypatch, _FakeClient())

    def _raise(url):
        raise DriveDownloadError("El documento no es accesible.")

    monkeypatch.setattr("app.services.drive_source_service.download_drive_file", _raise)

    from app.models.drive_source import DriveSource

    drive_source = DriveSource(name="Tabla", drive_url="https://docs.google.com/document/d/x/edit")
    service = DriveSourceService(db_session)
    service.repo.add(drive_source)
    service.repo.commit()

    result = service.sync(drive_source)  # must not raise

    assert result.last_sync_error == "El documento no es accesible."
    assert result.openai_file_id is None


def test_sync_stores_error_without_raising_when_upload_fails(db_session, monkeypatch):
    class _FailingFiles(_FakeFiles):
        def create(self, *, file, purpose):
            raise FileTooLargeError("El archivo supera el tamaño máximo permitido (512MB).")

    client = _FakeClient()
    client.files = _FailingFiles()
    _patch_client(monkeypatch, client)
    monkeypatch.setattr(
        "app.services.drive_source_service.download_drive_file",
        lambda url: DownloadedDriveFile(content=b"hello", filename="tabla.xlsx", content_type="x"),
    )

    service = DriveSourceService(db_session)
    drive_source = service.create(name="Tabla", drive_url="https://drive.google.com/file/d/abc/view")

    assert drive_source.openai_file_id is None
    assert "tamaño máximo" in drive_source.last_sync_error
