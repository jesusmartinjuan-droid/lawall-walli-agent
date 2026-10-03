from types import SimpleNamespace

from app.services.llm_service import (
    LLMService,
    MockLLMProvider,
    OpenAILLMProvider,
    _extract_generated_images,
)


def test_mock_provider_generates_non_empty_draft():
    provider = MockLLMProvider()
    response = provider.generate(instructions="system", input_text="Hola, necesito ayuda.")
    assert response.content
    assert response.provider == "mock"
    assert response.code_interpreter_snippets == []


def test_mock_provider_ignores_file_ids():
    provider = MockLLMProvider()
    response = provider.generate(instructions="system", input_text="Hola", file_ids=["file-abc"])
    assert response.content


def test_llm_service_generate_draft_without_langfuse_configured():
    service = LLMService(provider=MockLLMProvider())
    response = service.generate_draft(instructions="system", input_text="Hola", trace_name="test-trace")
    assert response.content
    assert response.langfuse_trace_id is None


def test_openai_provider_extracts_code_interpreter_snippets_and_web_search_queries(monkeypatch):
    fake_response = SimpleNamespace(
        output_text="Aquí tienes la respuesta.",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        output=[
            SimpleNamespace(
                type="code_interpreter_call", code="import pandas as pd\npd.read_excel('tabla.xlsx')"
            ),
            SimpleNamespace(
                type="web_search_call", action=SimpleNamespace(query="la-wall.com plazos de entrega")
            ),
            SimpleNamespace(type="message"),  # an item type we don't care about, must be ignored safely
        ],
    )

    provider = OpenAILLMProvider(api_key="sk-test", model="gpt-5.6-sol", max_tokens=1000)
    monkeypatch.setattr(
        provider,
        "_client",
        lambda: SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: fake_response)),
    )

    response = provider.generate(instructions="system", input_text="¿Qué precio tiene?", file_ids=["file-1"])

    assert response.content == "Aquí tienes la respuesta."
    assert response.code_interpreter_snippets == ["import pandas as pd\npd.read_excel('tabla.xlsx')"]
    assert response.web_search_queries == ["la-wall.com plazos de entrega"]
    assert response.input_tokens == 10
    assert response.output_tokens == 5


class _FakeContainerFile:
    def __init__(self, id_, path):
        self.id = id_
        self.path = path


class _FakeFilesContent:
    def __init__(self, bytes_by_file_id):
        self._bytes_by_file_id = bytes_by_file_id

    def retrieve(self, *, file_id, container_id):
        class _Resp:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return _Resp(self._bytes_by_file_id[file_id])


class _FakeContainerFiles:
    def __init__(self, files, bytes_by_file_id):
        self._files = files
        self.content = _FakeFilesContent(bytes_by_file_id)

    def list(self, container_id):
        return SimpleNamespace(data=self._files)


class _FakeContainers:
    def __init__(self, files_api):
        self.files = files_api


def test_extract_generated_images_downloads_new_image_and_skips_input_file():
    files = [
        _FakeContainerFile("cfile-1", "/mnt/data/file-abc-tabla.xlsx"),  # our own input, must be skipped
        _FakeContainerFile("cfile-2", "/mnt/data/grafico_precios.png"),  # genuine output
    ]
    client = SimpleNamespace(
        containers=_FakeContainers(_FakeContainerFiles(files, {"cfile-2": b"\x89PNGfakebytes"}))
    )

    images = _extract_generated_images(client, {"cntr-1"}, input_file_ids=["file-abc"])

    assert len(images) == 1
    assert images[0].filename == "grafico_precios.png"
    assert images[0].content_type == "image/png"
    assert images[0].content == b"\x89PNGfakebytes"


def test_extract_generated_images_ignores_non_image_files():
    files = [_FakeContainerFile("cfile-1", "/mnt/data/datos.json")]
    client = SimpleNamespace(containers=_FakeContainers(_FakeContainerFiles(files, {})))

    images = _extract_generated_images(client, {"cntr-1"}, input_file_ids=[])

    assert images == []


def test_extract_generated_images_never_raises_on_download_failure():
    files = [_FakeContainerFile("cfile-1", "/mnt/data/grafico.png")]

    class _BrokenFilesContent:
        def retrieve(self, *, file_id, container_id):
            raise RuntimeError("network error")

    files_api = _FakeContainerFiles(files, {})
    files_api.content = _BrokenFilesContent()
    client = SimpleNamespace(containers=_FakeContainers(files_api))

    images = _extract_generated_images(client, {"cntr-1"}, input_file_ids=[])  # must not raise

    assert images == []
