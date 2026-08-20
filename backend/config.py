"""Settings shim for crawler/smart_crawl.py (reads .env; does not modify smart_crawl)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        env_path = root / ".env"
        if env_path.is_file():
            load_dotenv(env_path, override=False)
    except ImportError:
        pass


@dataclass(frozen=True)
class CrawlerSettings:
    openai_api_key: str
    model_extract: str


def sync_opencode_to_openai_env() -> None:
    """Use one API key: OPENCODE_* → OPENAI_* for smart_crawl (OpenAI-compatible Zen API).

    OPENCODE_API_KEY is an OpenCode/Zen key, not a real OpenAI key — it only works
    against the OpenCode Zen base URL. Previously the key got copied to OPENAI_API_KEY
    unconditionally, but OPENAI_BASE_URL only got set when LLM_PROVIDER=="opencode" —
    so on any other provider (e.g. LLM_PROVIDER=deepseek with OPENCODE_API_KEY set as a
    fallback key), AsyncOpenAI defaulted to the real OpenAI API with an OpenCode key,
    which OpenAI correctly rejects ("Incorrect API key provided"), silently breaking
    smart-crawl's LLM metadata extraction on every call. Only sync the key when an
    OpenCode base URL is actually resolvable, so the key and base URL move together.
    """
    _load_dotenv()
    oc_base = (os.getenv("OPENCODE_BASE_URL") or "").strip()
    if not oc_base and (
        (os.getenv("LLM_PROVIDER") or "").lower() == "opencode"
        or (os.getenv("OPENCODE_API_KEY") or "").strip()
    ):
        oc_base = "https://opencode.ai/zen/v1"
    if oc_base:
        if not (os.getenv("OPENAI_API_KEY") or "").strip():
            oc = (os.getenv("OPENCODE_API_KEY") or "").strip()
            if oc:
                os.environ["OPENAI_API_KEY"] = oc
        if not (os.getenv("OPENAI_BASE_URL") or "").strip():
            os.environ["OPENAI_BASE_URL"] = oc_base.rstrip("/")
    if not (os.getenv("OPENAI_MODEL") or "").strip():
        om = (os.getenv("OPENCODE_MODEL") or os.getenv("MODEL_EXTRACT") or "").strip()
        if om:
            os.environ["OPENAI_MODEL"] = om


@lru_cache(maxsize=1)
def get_settings() -> CrawlerSettings:
    sync_opencode_to_openai_env()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or os.getenv("MODEL_EXTRACT") or "gpt-4o-mini").strip()
    return CrawlerSettings(openai_api_key=key, model_extract=model)
