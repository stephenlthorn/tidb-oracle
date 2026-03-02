from __future__ import annotations

from app.api.routes import admin


def test_drive_oauth_exchange_returns_400_on_invalid_state(client, monkeypatch):
    class _Settings:
        google_drive_client_id = "client-id"
        google_drive_client_secret = "client-secret"

    def fake_settings():
        return _Settings()

    def fake_consume(*, state, user_email, redirect_uri):
        raise RuntimeError("OAuth state is invalid or expired.")

    def fail_httpx_post(*args, **kwargs):  # pragma: no cover - defensive: should not be called
        raise AssertionError("Token exchange should not run when state validation fails.")

    monkeypatch.setattr(admin, "get_settings", fake_settings)
    monkeypatch.setattr(admin.google_drive_oauth_state_store, "consume", fake_consume)
    monkeypatch.setattr(admin.httpx, "post", fail_httpx_post)

    res = client.post(
        "/admin/drive/oauth/exchange",
        headers={"X-User-Email": "rep@pingcap.com"},
        json={
            "code": "abc123",
            "state": "invalid-state",
            "redirect_uri": "http://localhost:1455/auth/callback",
        },
    )

    assert res.status_code == 400
    assert "state" in (res.json().get("detail") or "").lower()
