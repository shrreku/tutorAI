from app.config import Settings
from app.services.llm.base import BaseLLMProvider
from app.services.llm.openai_provider import OpenAICompatibleProvider


def create_llm_provider(
    config: Settings,
    task: str = "default",
    *,
    model_override: str | None = None,
) -> BaseLLMProvider:
    """Create an LLM provider based on configuration.

    Args:
        config: Application settings.
        task: One of 'default', 'tutoring', 'evaluation', 'curriculum',
              'ontology', 'enrichment'. Selects the per-task model override
              from config (e.g. LLM_MODEL_TUTORING). Falls back to LLM_MODEL.
    """
    model_map = {
        "tutoring": config.LLM_MODEL_TUTORING,
        "evaluation": config.LLM_MODEL_EVALUATION,
        "curriculum": config.LLM_MODEL_CURRICULUM,
        "ontology": config.LLM_MODEL_ONTOLOGY,
        "enrichment": config.LLM_MODEL_ENRICHMENT,
    }
    model = model_override or model_map.get(task) or config.LLM_MODEL
    return OpenAICompatibleProvider(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_API_BASE_URL,
        model=model,
    )
