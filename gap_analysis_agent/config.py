from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_file(env_path: str | Path | None = None) -> None:
    path = Path(env_path) if env_path else Path(__file__).resolve().parents[1] / ".env"
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_wrapping_quotes(value.strip())
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    llm_model: str | None = None
    llm_deployment: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    api_version: str | None = None
    api_type: str | None = None
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        return cls(
            llm_model=(
                os.getenv("GAP_ANALYSIS_LLM_MODEL")
                or os.getenv("OPENAI_MODEL_NAME")
                or os.getenv("AZURE_OPENAI_MODEL")
                or None
            ),
            llm_deployment=(
                os.getenv("GAP_ANALYSIS_LLM_DEPLOYMENT")
                or os.getenv("AZURE_OPENAI_DEPLOYMENT")
                or os.getenv("AZURE_DEPLOYMENT_NAME")
                or os.getenv("OPENAI_DEPLOYMENT_NAME_4TURBO")
                or os.getenv("OPENAI_DEPLOYMENT_NAME_4O")
                or os.getenv("OPENAI_DEPLOYMENT_NAME")
                or None
            ),
            api_key=(
                os.getenv("GAP_ANALYSIS_API_KEY")
                or os.getenv("AZURE_OPENAI_API_KEY")
                or os.getenv("AZURE_API_KEY")
                or os.getenv("OPENAI_API_KEY")
                or None
            ),
            api_base=(
                os.getenv("GAP_ANALYSIS_API_BASE")
                or os.getenv("AZURE_OPENAI_ENDPOINT")
                or os.getenv("AZURE_API_BASE")
                or os.getenv("OPENAI_API_BASE")
                or None
            ),
            api_version=(
                os.getenv("GAP_ANALYSIS_API_VERSION")
                or os.getenv("AZURE_API_VERSION")
                or os.getenv("OPENAI_API_VERSION")
                or None
            ),
            api_type=(os.getenv("OPENAI_API_TYPE") or os.getenv("GAP_ANALYSIS_API_TYPE") or None),
            verbose=_as_bool(os.getenv("GAP_ANALYSIS_VERBOSE")),
        )

    def resolved_model(self) -> str | None:
        provider = (self.api_type or "").strip().lower()
        if provider == "azure":
            deployment = self.llm_deployment or self.llm_model
            if not deployment:
                return None
            return deployment if deployment.startswith("azure/") else f"azure/{deployment}"
        return self.llm_model or self.llm_deployment

    def prepare_runtime_environment(self) -> None:
        if self.api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.api_key)

        provider = (self.api_type or "").strip().lower()
        if provider == "azure":
            if self.api_key:
                os.environ.setdefault("AZURE_OPENAI_API_KEY", self.api_key)
                os.environ.setdefault("AZURE_API_KEY", self.api_key)
            if self.api_base:
                os.environ.setdefault("AZURE_OPENAI_ENDPOINT", self.api_base)
                os.environ.setdefault("AZURE_API_BASE", self.api_base)
                os.environ.setdefault("OPENAI_API_BASE", self.api_base)
            if self.api_version:
                os.environ.setdefault("AZURE_API_VERSION", self.api_version)
                os.environ.setdefault("OPENAI_API_VERSION", self.api_version)
            os.environ.setdefault("OPENAI_API_TYPE", "azure")
        else:
            if self.api_base:
                os.environ.setdefault("OPENAI_API_BASE", self.api_base)
