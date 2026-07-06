from app.services.prompt_service import PromptService


def test_set_active_clears_previous_default(db_session):
    service = PromptService(db_session)
    first = service.create(name="Prompt A", description=None, content="contenido A", is_active=True)
    second = service.create(name="Prompt B", description=None, content="contenido B", is_active=True)

    service.set_active(first)
    assert service.get_active_prompt().id == first.id

    service.set_active(second)
    db_session.refresh(first)
    assert first.is_default is False
    assert service.get_active_prompt().id == second.id


def test_default_prompt_content_loads_from_file():
    content = PromptService.default_prompt_content()
    assert "Walli" in content
    assert "{{company_documents_context}}" in content
