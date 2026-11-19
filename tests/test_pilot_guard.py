import importlib.util
from pathlib import Path

import pytest

from app.config import settings

spec = importlib.util.spec_from_file_location("pilot_benchmark", Path(__file__).resolve().parents[1] / "scripts/benchmark_library.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


@pytest.mark.parametrize("change", [
    {"database_url": "postgresql+psycopg://synthetic@localhost/teleiosis"},
    {"app_env": "staging"}, {"app_env": "prod"},
    {"push_enabled": True}, {"email_backend": "smtp"}, {"email_backend": "capture"},
])
def test_benchmark_refuses_live_target_before_connect(monkeypatch, change):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://synthetic@localhost/teleiosis_pilot_test_guard")
    monkeypatch.setattr(settings, "app_env", "dev")
    monkeypatch.setattr(settings, "push_enabled", False)
    monkeypatch.setattr(settings, "email_backend", "console")
    for key, value in change.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(pilot, "SessionLocal", lambda: pytest.fail("must reject before opening a database session"))
    with pytest.raises(SystemExit, match="Refusing target"):
        pilot.check_target()
