import pytest
from src import config


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Fresh DB per test, frozen 'today', no real API keys -> tests are deterministic and offline."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "AS_OF_DATE", "2026-10-10")
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL"):
        monkeypatch.setattr(config, k, "")
