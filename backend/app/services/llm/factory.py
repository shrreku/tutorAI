import logging

from app.config import Settings
from app.services.llm.base import BaseLLMProvider
from app.services.llm.openai_provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


def get_missing_platform_llm_config(config: Settings, *, task: str = "default") -> list[str]:
    """Return required platform LLM settings that are missing for a task."""
    model_map = {
        "tutoring": config.LLM_MODEL_TUTORING,
        "evaluation": config.LLM_MODEL_EVALUATION,
        "curriculum": config.LLM_MODEL_CURRICULUM,
        "ontology": config.LLM_MODEL_ONTOLOGY,
        "enrichment": config.LLM_MODEL_ENRICHMENT,
    }

    missing: list[str] = []
    if not (config.LLM_API_KEY or "").strip():
        missing.append("LLM_API_KEY")
    if not (config.LLM_API_BASE_URL or "").strip():
        missing.append("LLM_API_BASE_URL")

    task_model = model_map.get(task)
    if not ((task_model or config.LLM_MODEL or "").strip()):
        missing.append(f"LLM_MODEL[{task}]")

    return missing


def validate_platform_llm_config(config: Settings, *, task: str = "default") -> None:
    """Raise a clear error when hosted platform LLM configuration is incomplete."""
    missing = get_missing_platform_llm_config(config, task=task)
    if missing:
        fields = ", ".join(missing)
        raise ValueError(
            f"Hosted async LLM configuration is incomplete for {task}: missing {fields}. "
            "Configure platform-managed credentials for uploads and worker jobs."
        )


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
    if not byok_api_key:
        validate_platform_llm_config(config, task=task)

    if not api_key:
        raise ValueError(
            "No LLM API key is configured. Provide BYOK credentials or set LLM_API_KEY."
        )

    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
