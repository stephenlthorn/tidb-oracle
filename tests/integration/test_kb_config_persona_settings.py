from __future__ import annotations


def test_kb_config_exposes_persona_fields_with_defaults(client):
    res = client.get("/admin/kb-config")
    assert res.status_code == 200
    data = res.json()

    assert data["persona_name"] == "sales_representative"
    assert "persona_prompt" in data
    assert "se_poc_kit_url" in data
    assert isinstance(data.get("feature_flags_json"), dict)


def test_kb_config_normalizes_persona_and_saves_prompt(client):
    update_payload = {
        "persona_name": "SE",
        "persona_prompt": "Focus on architecture fit and POC design for technical validation.",
    }
    put_res = client.put("/admin/kb-config", json=update_payload)
    assert put_res.status_code == 200
    updated = put_res.json()

    assert updated["persona_name"] == "se"
    assert updated["persona_prompt"] == update_payload["persona_prompt"]

    get_res = client.get("/admin/kb-config")
    assert get_res.status_code == 200
    current = get_res.json()
    assert current["persona_name"] == "se"
    assert current["persona_prompt"] == update_payload["persona_prompt"]


def test_kb_config_updates_gtm_fields(client):
    payload = {
        "se_poc_kit_url": "https://internal.pingcap.com/poc-kit",
        "feature_flags_json": {
            "rep_account_brief": True,
            "se_competitor_coach": False,
        },
    }
    put_res = client.put("/admin/kb-config", json=payload)
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["se_poc_kit_url"] == payload["se_poc_kit_url"]
    assert data["feature_flags_json"] == payload["feature_flags_json"]
