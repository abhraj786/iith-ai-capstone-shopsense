"""Configuration loaded from environment variables / .env, resolved from the project root."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Export .env into the process environment so LiteLLM finds provider keys (GEMINI_API_KEY, ...).
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_prefix="CAPSTONE_", extra="ignore"
    )

    domain: str = "shopsense"
    data_root: Path = Path("data")
    runtime_root: Path = Path("runtime")

    # LiteLLM model string; provider API keys (e.g. GEMINI_API_KEY) are read by LiteLLM itself.
    llm_model: str = "gemini/gemini-flash-lite-latest"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2  # re-asks after schema-invalid output
    llm_rate_limit_retries: int = 4
    llm_rate_limit_backoff_s: float = 8.0  # doubles on each retry

    # M7 tracing/reliability. LangFuse forwarding is enabled only when keys are present.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    tool_retry_attempts: int = 2
    tool_circuit_failure_threshold: int = 2
    tool_circuit_cooldown_s: float = 30.0

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def seed_dir(self) -> Path:
        return self._resolve(self.data_root) / self.domain / "mock_api"

    @property
    def state_dir(self) -> Path:
        return self._resolve(self.runtime_root) / self.domain / "mock_api"


@lru_cache
def get_settings() -> Settings:
    return Settings()
