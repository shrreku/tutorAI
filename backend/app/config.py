from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/studyagent"
    
    # LLM Configuration
    LLM_API_KEY: str = ""
    LLM_API_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o"
    LLM_MAX_TOKENS_PER_CALL: int = 8000
    LLM_MAX_TOKENS_PER_TURN: int = 24000
    LLM_MAX_TOKENS_PER_SESSION: int = 100000
    LLM_RATE_LIMIT_RPM: int = 60
    LLM_COST_TRACKING_ENABLED: bool = True
    
    # Per-task LLM model overrides (empty string = fall back to LLM_MODEL)
    LLM_MODEL_ONTOLOGY: str = "google/gemini-3-flash-preview"          # Full-content ontology extraction
    LLM_MODEL_ENRICHMENT: str = "google/gemini-2.5-flash-lite"        # Per-chunk/batch enrichment
    LLM_MODEL_TUTORING: str = "google/gemini-3-flash-preview"          # Interactive tutoring
    LLM_MODEL_EVALUATION: str = "google/gemini-3-flash-preview"        # Evaluator + safety critic
    LLM_MODEL_CURRICULUM: str = "google/gemini-3-flash-preview"        # Curriculum planning
    
    # Per-task token limits
    ONTOLOGY_MAX_INPUT_TOKENS: int = 100_000
    ONTOLOGY_MAX_OUTPUT_TOKENS: int = 16_384
    ENRICHMENT_MAX_INPUT_TOKENS: int = 30_000
    ENRICHMENT_MAX_OUTPUT_TOKENS: int = 4_096
    ENRICHMENT_MAX_CHUNKS_PER_BATCH: int = 8
    
    # Embedding Configuration
    EMBEDDING_MODEL_ID: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_API_BASE_URL: Optional[str] = None
    EMBEDDING_API_KEY: Optional[str] = None

    # Ingestion: Docling configuration
    INGESTION_DOCLING_PROFILE: str = "balanced"  # balanced | fast | high_fidelity
    INGESTION_DOCLING_ARTIFACTS_PATH: Optional[str] = None
    INGESTION_DOCLING_DEVICE: str = "auto"
    INGESTION_DOCLING_NUM_THREADS: int = 4
    INGESTION_DOCLING_TIMEOUT_S: int = 120
    INGESTION_DOCLING_OCR_ENGINE: str = "auto"  # auto | easyocr | tesseract | tesseract_cli | rapidocr | ocrmac
    INGESTION_DOCLING_OCR_LANGS: str = "eng"
    INGESTION_DOCLING_TABLE_MODE: str = "accurate"  # accurate | fast
    INGESTION_DOCLING_TABLE_CELL_MATCHING: bool = True
    INGESTION_DOCLING_FORMULA_ENRICHMENT: Optional[bool] = None
    INGESTION_DOCLING_CODE_ENRICHMENT: Optional[bool] = None
    INGESTION_DOCLING_PICTURE_IMAGES: Optional[bool] = None
    INGESTION_DOCLING_PICTURE_CLASSIFICATION: Optional[bool] = None
    INGESTION_DOCLING_PICTURE_DESCRIPTION: Optional[bool] = None
    INGESTION_DOCLING_CHART_EXTRACTION: Optional[bool] = None
    
    # Authentication
    AUTH_ENABLED: bool = False
    AUTH_SECRET_KEY: str = "your-secret-key-change-in-production"
    AUTH_ALGORITHM: str = "HS256"
    AUTH_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    
    # Storage Configuration
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_DIR: str = "./storage"
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: Optional[str] = None
    MINIO_ENDPOINT: Optional[str] = None
    MINIO_ACCESS_KEY: Optional[str] = None
    MINIO_SECRET_KEY: Optional[str] = None
    
    # Optional Services
    REDIS_URL: Optional[str] = None
    NEO4J_ENABLED: bool = True
    NEO4J_URI: Optional[str] = "bolt://localhost:7687"
    NEO4J_USER: Optional[str] = "neo4j"
    NEO4J_PASSWORD: Optional[str] = "password"
    
    # Observability (Langfuse v3 SDK)
    LANGFUSE_PUBLIC_KEY: Optional[str] = None
    LANGFUSE_SECRET_KEY: Optional[str] = None
    LANGFUSE_BASE_URL: Optional[str] = None
    LANGFUSE_TRACE_MODE: str = "simple"  # simple | detailed
    
    # Feature Flags
    POLICY_MODE: str = "llm_only"
    LLM_RERANKER_ENABLED: bool = False
    ADAPTIVE_DELEGATION_ENABLED: bool = True
    TUTOR_SERVICE_V2_ENABLED: bool = True

    # Development / eval tooling
    # When enabled, the tutoring turn endpoint will accept model overrides via
    # headers (e.g. X-LLM-Model-Tutoring). Keep disabled in production.
    ALLOW_LLM_MODEL_OVERRIDE_HEADERS: bool = False
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
