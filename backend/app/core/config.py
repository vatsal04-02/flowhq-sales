from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://flowhq:flowhq@localhost:5432/flowhq"
    secret_key: str = "dev-only-change-me"  # signs session cookies; MUST be overridden in prod
    fernet_key: str = ""  # encrypts integration credentials (Phase 4+)
    session_ttl_hours: int = 12
    cookie_secure: bool = False

    max_upload_bytes: int = 10 * 1024 * 1024
    max_import_rows: int = 50_000
    import_chunk_size: int = 500

    job_lease_seconds: int = 300
    job_poll_seconds: float = 2.0

    # Local/open-source model via an OpenAI-compatible endpoint (Ollama).
    # llm_provider: ollama | fake | none.  "none" = templates only (instant, no model needed).
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:3b-instruct"  # use qwen2.5:1.5b-instruct for more speed
    llm_timeout_seconds: int = 60

    # Voice dictation. stt_provider: none (off) | fake (tests) | openai_compat (any server exposing POST {base}/audio/transcriptions:
    # a local faster-whisper / whisper.cpp server, or an authorised hosted provider). Audio is deleted as soon as it is processed.
    stt_provider: str = "none"
    stt_base_url: str = "http://localhost:8001/v1"
    stt_model: str = "Systran/faster-whisper-small"
    stt_api_key: str = ""  # only for hosted providers; never returned to the browser or logged
    stt_timeout_seconds: int = 60
    stt_processing: str = ""  # "local" | "cloud" to override what is inferred from stt_base_url
    voice_max_bytes: int = 10 * 1024 * 1024
    voice_max_seconds: int = 120
    voice_max_per_hour: int = 60  # per user
    voice_retention_hours: int = 24  # transcripts are kept this long for "recent dictations", then deleted

    public_base_url: str = "http://localhost:3000"  # used in unsubscribe links
    allow_private_fetch: bool = False  # tests only: lets the research fetcher reach localhost
    imap_poll_seconds: int = 60
    imap_lookback_days: int = 7  # first sync only looks this far back
    imap_max_per_sync: int = 100
    research_max_pages: int = 4
    research_ttl_days: int = 30
    fetch_user_agent: str = "FlowHQBot/0.1 (+sales research; respects robots.txt)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
