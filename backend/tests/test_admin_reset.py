"""Guard against accidentally exposing the destructive demo reset route."""
from fastapi.testclient import TestClient

from app.main import app, settings


def test_admin_reset_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "enable_demo_reset", False)
    response = TestClient(app).post("/admin/reset")
    assert response.status_code == 404


def test_admin_reset_rejects_non_loopback_even_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_demo_reset", True)
    response = TestClient(app).post("/admin/reset")
    assert response.status_code == 403
