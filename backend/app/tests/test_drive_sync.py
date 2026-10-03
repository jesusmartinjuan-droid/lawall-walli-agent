import httpx
import pytest

from app.services.drive_sync import DriveDownloadError, detect_drive_file_id, download_drive_file


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://drive.google.com/file/d/abc123/view?usp=sharing", ("binary", "abc123")),
        ("https://docs.google.com/document/d/doc123/edit", ("document", "doc123")),
        ("https://docs.google.com/spreadsheets/d/sheet123/edit#gid=0", ("spreadsheets", "sheet123")),
        ("https://docs.google.com/presentation/d/slide123/edit", ("presentation", "slide123")),
        ("https://example.com/not-drive-at-all", None),
    ],
)
def test_detect_drive_file_id(url, expected):
    assert detect_drive_file_id(url) == expected


def _client_with_response(status_code: int, content: bytes, headers: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content, headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_binary_file_happy_path():
    client = _client_with_response(
        200,
        b"PNGDATA",
        {"content-type": "image/png", "content-disposition": 'attachment; filename="tabla.png"'},
    )
    result = download_drive_file("https://drive.google.com/file/d/abc123/view", client=client)
    assert result.content == b"PNGDATA"
    assert result.filename == "tabla.png"


def test_download_binary_file_not_public_raises_clear_error():
    client = _client_with_response(200, b"<html>sign in</html>", {"content-type": "text/html"})
    with pytest.raises(DriveDownloadError, match="Cualquiera con el enlace"):
        download_drive_file("https://drive.google.com/file/d/abc123/view", client=client)


def test_export_google_doc_as_docx_happy_path():
    client = _client_with_response(
        200,
        b"DOCXDATA",
        {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    )
    result = download_drive_file("https://docs.google.com/document/d/doc123/edit", client=client)
    assert result.content == b"DOCXDATA"
    assert result.filename == "doc123.docx"


def test_export_google_sheet_as_xlsx_happy_path():
    client = _client_with_response(
        200,
        b"XLSXDATA",
        {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    )
    result = download_drive_file("https://docs.google.com/spreadsheets/d/sheet123/edit", client=client)
    assert result.content == b"XLSXDATA"
    assert result.filename == "sheet123.xlsx"


def test_export_native_file_not_public_raises_clear_error():
    client = _client_with_response(200, b"<html>sign in</html>", {"content-type": "text/html"})
    with pytest.raises(DriveDownloadError, match="Cualquiera con el enlace"):
        download_drive_file("https://docs.google.com/document/d/doc123/edit", client=client)


def test_unrecognized_url_raises_clear_error():
    with pytest.raises(DriveDownloadError, match="enlace no es un documento de Drive"):
        download_drive_file("https://example.com/not-drive-at-all")
