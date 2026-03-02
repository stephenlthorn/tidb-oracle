from __future__ import annotations

from app.api.routes import admin


def test_sync_feishu_supports_multi_roots_and_recursion(client, monkeypatch):
    called: dict = {}

    class FakeIngestor:
        def __init__(self, db, **kwargs):
            called["init_kwargs"] = kwargs

        def sync_roots(self, roots, recursive=True):
            called["roots"] = roots
            called["recursive"] = recursive
            return {"files_seen": 3, "added": 2, "updated": 0, "skipped": 1, "errors": 0}

    monkeypatch.setattr(admin, "FeishuIngestor", FakeIngestor)

    cfg = {
        "feishu_enabled": True,
        "feishu_root_tokens": "root_a\nroot_b,root_c",
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
    }
    put_res = client.put("/admin/kb-config", json=cfg)
    assert put_res.status_code == 200

    res = client.post("/admin/sync/feishu")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "ok"
    assert called["roots"] == ["root_a", "root_b", "root_c"]
    assert called["recursive"] is True
    assert called["init_kwargs"]["app_id"] == "cli_test"
    assert called["init_kwargs"]["app_secret"] == "secret_test"


def test_sync_feishu_oauth_mode_requires_connected_user_token(client):
    cfg = {
        "feishu_enabled": True,
        "feishu_oauth_enabled": True,
        "feishu_root_tokens": "root_a",
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
    }
    put_res = client.put("/admin/kb-config", json=cfg)
    assert put_res.status_code == 200

    res = client.post("/admin/sync/feishu", headers={"X-User-Email": "rep@pingcap.com"})
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "error"
    assert "not connected" in data["message"].lower() or "missing" in data["message"].lower()


def test_sync_feishu_oauth_mode_uses_user_access_token(client, monkeypatch):
    called: dict = {}

    class FakeIngestor:
        def __init__(self, db, **kwargs):
            called["init_kwargs"] = kwargs

        def sync_roots(self, roots, recursive=True):
            called["roots"] = roots
            called["recursive"] = recursive
            return {"files_seen": 1, "added": 1, "updated": 0, "skipped": 0, "errors": 0}

    monkeypatch.setattr(admin, "FeishuIngestor", FakeIngestor)

    def fake_get_access_token(self, user_email, *, app_id, app_secret, base_url=None):
        called["token_args"] = {
            "user_email": user_email,
            "app_id": app_id,
            "app_secret": app_secret,
            "base_url": base_url,
        }
        return "user-token"

    def fake_update_last_synced(self, user_email):
        called["synced_user"] = user_email

    monkeypatch.setattr(admin.FeishuCredentialService, "get_access_token", fake_get_access_token)
    monkeypatch.setattr(admin.FeishuCredentialService, "update_last_synced", fake_update_last_synced)

    cfg = {
        "feishu_enabled": True,
        "feishu_oauth_enabled": True,
        "feishu_root_tokens": "root_a",
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
    }
    put_res = client.put("/admin/kb-config", json=cfg)
    assert put_res.status_code == 200

    res = client.post("/admin/sync/feishu", headers={"X-User-Email": "se@pingcap.com"})
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "ok"
    assert called["token_args"]["user_email"] == "se@pingcap.com"
    assert called["init_kwargs"]["access_token"] == "user-token"
    assert called["init_kwargs"]["user_email"] == "se@pingcap.com"
    assert called["roots"] == ["root_a"]
    assert called["synced_user"] == "se@pingcap.com"
