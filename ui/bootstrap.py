"""Project paths and settings bootstrap for the Streamlit app."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _apply_streamlit_secrets() -> None:
    """Copy Streamlit Cloud secrets into os.environ (Settings / auth read env vars).

    Secrets win over .env when both exist (typical on Community Cloud).
    No-op when secrets.toml is absent (Docker / local .env-only).
    """
    try:
        import streamlit as st
        from streamlit.runtime.secrets import StreamlitSecretNotFoundError
    except ImportError:
        return

    local_secrets = ROOT / ".streamlit" / "secrets.toml"
    home_secrets = Path.home() / ".streamlit" / "secrets.toml"
    # Community Cloud injects secrets without a file on disk.
    on_streamlit_cloud = bool(
        os.getenv("STREAMLIT_SHARING_MODE")
        or os.getenv("STREAMLIT_CLOUD")
        or os.getenv("runtime", "").startswith("streamlit")
    )
    if not local_secrets.is_file() and not home_secrets.is_file() and not on_streamlit_cloud:
        return

    def _set(key: str, val: object) -> None:
        if isinstance(val, (str, int, float, bool)):
            os.environ[str(key)] = str(val)

    try:
        secrets = st.secrets
        for key in secrets:
            try:
                val = secrets[key]
            except Exception:
                continue
            if isinstance(val, dict):
                for nested_key, nested_val in val.items():
                    _set(str(nested_key), nested_val)
            else:
                _set(str(key), val)
    except StreamlitSecretNotFoundError:
        return
    except Exception:
        return


def init_env() -> None:
    from vendor_intel.placeholders.load_keys import apply_env_overrides
    from vendor_intel.utils.output_filter import install_stderr_filter

    install_stderr_filter()
    # Secrets after a plain dotenv load so Cloud values win; then wire placeholders.
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    _apply_streamlit_secrets()
    apply_env_overrides()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def output_dir() -> Path:
    from vendor_intel.pipeline.output_paths import market_query_output_dir

    return market_query_output_dir(ROOT)


def phase1_debug_dir() -> Path:
    path = ROOT / "output" / "phase1_debug"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings(profile: str = "quality"):
    from vendor_intel.config import Settings

    init_env()
    settings = Settings.load()
    return settings.model_copy(
        update={
            "use_mock_data": False,
            "mock_mode": False,
            "pipeline_profile": profile,
            "pipeline_recall_mode": profile == "recall",
            "pipeline_use_ssc": True,
            "pipeline_min_export_confidence": 0.50,
        }
    )


def pipeline_caps(settings, *, country: str = "global") -> tuple[int, int]:
    from vendor_intel.pipeline.geo_limits import pipeline_limits

    recall = settings.pipeline_profile == "recall"
    lim = pipeline_limits(settings, recall=recall, country=country)
    return int(lim["discover"]), int(lim["enrich"])


def env_warnings() -> list[str]:
    warnings: list[str] = []
    mock = os.getenv("USE_MOCK_DATA", "true").strip().lower()
    if mock not in ("false", "0", "no", "off"):
        warnings.append("USE_MOCK_DATA is not false — results will be empty or fake.")
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    key_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    key_var = key_map.get(provider)
    if key_var and not os.getenv(key_var, "").strip():
        warnings.append(f"LLM_PROVIDER={provider} but {key_var} is not set.")
    return warnings


def live_validation_warnings(settings) -> list[str]:
    from vendor_intel.live_checks import validate_live_settings

    try:
        return validate_live_settings(settings)
    except Exception as exc:
        return [str(exc)]
