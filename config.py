"""Shared provider configuration. Keys never become model input or log fields."""
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.2
    timeout: float = 60.0

    @classmethod
    def load(cls, *, model=None, base_url=None, api_key=None, temperature=0.2, timeout=60.0):
        settings = cls(model or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
                       base_url or os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
                       api_key if api_key is not None else os.getenv("LLM_API_KEY", ""),
                       temperature, timeout)
        url = urlsplit(settings.base_url)
        local = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or not (url.scheme == "https" or local)):
            raise ValueError("Use a plain HTTPS API base URL (HTTP only for localhost).")
        if not settings.api_key:
            raise ValueError("Set LLM_API_KEY before calling the provider.")
        if timeout <= 0 or not 0 <= temperature <= 2:
            raise ValueError("Choose a positive timeout and a temperature between 0 and 2.")
        return settings
