from __future__ import annotations


def test_security_settings_endpoint_returns_safe_summary(client):
    res = client.get("/admin/security/settings")
    assert res.status_code == 200
    data = res.json()

    assert "enterprise_mode" in data
    assert "security_require_private_llm_endpoint" in data
    assert "security_allowed_llm_base_urls" in data
    assert "security_redact_before_llm" in data
    assert "security_redact_audit_logs" in data
    assert "internal_domain_allowlist" in data
    # Endpoint must not leak credential secrets.
    assert "openai_api_key" not in data
