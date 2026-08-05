"""
All the settings in one place, read from environment variables.

Everything has a default that works with no credentials at all, so a fresh
clone runs straight after seeding. Real keys only matter if you want to point
StoreSense at a live Shopify store or a paid LLM.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- database ---
    # SQLite by default so there is nothing to install. Set DATABASE_URL to a
    # Postgres URL in production and everything else keeps working.
    database_url: str = "sqlite:///./storesense.db"

    # --- store identity ---
    store_name: str = "noszn"

    # --- shopify (optional) ---
    # If these are blank we just use the seeded synthetic data instead.
    shopify_store_domain: str = ""
    shopify_access_token: str = ""

    # --- llm gateway ---
    # Provider agnostic: anything speaking the OpenAI chat-completions shape
    # works. Defaults point at a local Ollama so the project costs nothing.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"  # Ollama ignores this but clients expect something
    # 8B is about the floor for this. Smaller models read the figures out of
    # the context correctly and then invent a comparison to wrap around them —
    # "up 25% on last year" when the context only ever mentioned last week.
    llm_model: str = "llama3.1"
    llm_vision_model: str = "llama3.2-vision"
    llm_embed_model: str = "nomic-embed-text"

    # --- voice ---
    # Runs locally through faster-whisper. "base" is the sweet spot: small
    # enough to download in seconds, good enough for a quiet room.
    whisper_model: str = "base"
    # Used only if faster-whisper isn't installed and the provider can do audio.
    whisper_remote_model: str = "whisper-1"

    # How long we wait on the model, and how many times we retry a failure.
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    # Simple rate limit so one browser tab cannot hammer the model.
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    # --- dashboard rules ---
    low_stock_threshold: int = 8

    class Config:
        env_file = ".env"


settings = Settings()
