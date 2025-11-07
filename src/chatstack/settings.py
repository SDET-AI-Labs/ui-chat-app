from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    backend: str = "openai_like"  # or "ollama" or "gemini"

    # OpenAI-like
    openai_api_key: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_verify_ssl: bool = True

    # Ollama
    ollama_base: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Hugging Face
    hf_api_key: str | None = None
    hf_model: str = "microsoft/Phi-3-mini-4k-instruct"
    hf_api_base: str = "https://api-inference.huggingface.co/models"

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"

    # Database
    db_kind: str = "sqlite"
    db_string: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

settings = Settings()
