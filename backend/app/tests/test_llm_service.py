from app.services.llm_service import LLMService, MockLLMProvider


def test_mock_provider_generates_non_empty_draft():
    provider = MockLLMProvider()
    response = provider.generate(system_prompt="system", user_prompt="Hola, necesito ayuda.")
    assert response.content
    assert response.provider == "mock"


def test_llm_service_generate_draft_without_langfuse_configured():
    service = LLMService(provider=MockLLMProvider())
    response = service.generate_draft(system_prompt="system", user_prompt="Hola", trace_name="test-trace")
    assert response.content
    assert response.langfuse_trace_id is None
