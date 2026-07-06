from app.models.llm_trace import LLMTrace
from app.repositories.base_repository import BaseRepository


class LLMTraceRepository(BaseRepository[LLMTrace]):
    model = LLMTrace
