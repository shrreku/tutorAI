import logging

from app.config import Settings
from app.services.llm.base import BaseLLMProvider
from app.services.llm.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


def create_llm_provider(
    config: Settings,
    task: str = "default",
    *,
    model_override: str | None = None,
    byok_api_key: str | None = None,
    byok_api_base_url: str | None = None,
) -> BaseLLMProvider:
    """Create an LLM provider based on configuration.

    Args:
        config: Application settings.
        task: One of 'default', 'tutoring', 'evaluation', 'curriculum',
              'ontology', 'enrichment'. Selects the per-task model override
              from config (e.g. LLM_MODEL_TUTORING). Falls back to LLM_MODEL.
        model_override: Explicit model name that takes precedence over task map.
        byok_api_key: User-supplied API key (BYOK).  When provided, this key
                      is used instead of the server-side ``LLM_API_KEY``.
                      The key is **never** persisted or logged.
        byok_api_base_url: Optional user-supplied base URL for the LLM API.
    """
    model_map = {
        "tutoring": config.LLM_MODEL_TUTORING,
        "evaluation": config.LLM_MODEL_EVALUATION,
        "curriculum": config.LLM_MODEL_CURRICULUM,
        "ontology": config.LLM_MODEL_ONTOLOGY,
        "enrichment": config.LLM_MODEL_ENRICHMENT,
    }
    model = model_override or model_map.get(task) or config.LLM_MODEL

    # Resolve API key: prefer BYOK, fall back to server config.
    api_key = byok_api_key or config.LLM_API_KEY
    base_url = byok_api_base_url or config.LLM_API_BASE_URL

    if config.BYOK_ENABLED and not byok_api_key and not config.LLM_API_KEY:
        logger.warning("BYOK is enabled but no API key was provided (user or server).")

    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
