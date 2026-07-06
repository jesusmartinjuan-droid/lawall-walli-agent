from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.prompt import PromptTemplate
from app.repositories.prompt_repository import PromptRepository

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_DEFAULT_PROMPT_PATH = _PROMPTS_DIR / "default_email_response_prompt.txt"


class PromptService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PromptRepository(db)

    def list_prompts(self) -> list[PromptTemplate]:
        return self.repo.list(limit=500)

    def get(self, prompt_id: int) -> PromptTemplate | None:
        return self.repo.get(prompt_id)

    def get_active_prompt(self) -> PromptTemplate | None:
        return self.repo.get_default()

    def create(self, *, name: str, description: str | None, content: str, is_active: bool) -> PromptTemplate:
        prompt = PromptTemplate(name=name, description=description, content=content, is_active=is_active)
        self.repo.add(prompt)
        self.repo.commit()
        return prompt

    def update(self, prompt: PromptTemplate, **fields) -> PromptTemplate:
        for key, value in fields.items():
            if value is not None:
                setattr(prompt, key, value)
        self.repo.commit()
        self.repo.refresh(prompt)
        return prompt

    def delete(self, prompt: PromptTemplate) -> None:
        self.repo.delete(prompt)
        self.repo.commit()

    def set_active(self, prompt: PromptTemplate) -> PromptTemplate:
        """Marks this prompt as THE prompt used for draft generation."""
        self.repo.clear_default_flag()
        prompt.is_default = True
        prompt.is_active = True
        self.repo.commit()
        self.repo.refresh(prompt)
        logger.info("prompt_set_active id=%s name=%s", prompt.id, prompt.name)
        return prompt

    @staticmethod
    def default_prompt_content() -> str:
        return _DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")
