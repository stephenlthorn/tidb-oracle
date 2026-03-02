from __future__ import annotations


def _seed_calls(client):
    client.post("/admin/sync/chorus")


def test_rep_module_endpoints_return_structured_outputs(client):
    _seed_calls(client)

    brief = client.post(
        "/rep/account-brief",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
        },
    )
    assert brief.status_code == 200
    brief_data = brief.json()
    assert isinstance(brief_data.get("summary"), str)
    assert isinstance(brief_data.get("decision_criteria"), list)

    questions = client.post(
        "/rep/discovery-questions",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
            "count": 5,
        },
    )
    assert questions.status_code == 200
    q_data = questions.json()
    assert isinstance(q_data.get("questions"), list)
    assert len(q_data["questions"]) >= 3

    risk = client.post(
        "/rep/deal-risk",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
        },
    )
    assert risk.status_code == 200
    risk_data = risk.json()
    assert risk_data.get("risk_level") in {"low", "medium", "high"}
    assert isinstance(risk_data.get("risks"), list)

    draft = client.post(
        "/rep/follow-up-draft",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
            "to": ["estyn.c@pingcap.com"],
            "cc": ["se.demo@pingcap.com"],
            "mode": "draft",
            "tone": "crisp",
        },
    )
    assert draft.status_code == 200
    draft_data = draft.json()
    assert draft_data.get("mode") in {"draft", "sent"}
    assert isinstance(draft_data.get("subject"), str)
    assert isinstance(draft_data.get("body"), str)


def test_rep_follow_up_blocks_external_recipient(client):
    _seed_calls(client)

    draft = client.post(
        "/rep/follow-up-draft",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
            "to": ["customer@gmail.com"],
            "mode": "send",
        },
    )
    assert draft.status_code == 200
    data = draft.json()
    assert data["mode"] == "blocked"
    assert "restricted" in (data.get("reason_blocked") or "").lower()


def test_se_module_endpoints_return_structured_outputs(client):
    _seed_calls(client)

    poc_plan = client.post(
        "/se/poc-plan",
        json={
            "user": "se.demo@pingcap.com",
            "account": "Evernorth",
            "target_offering": "TiDB Cloud Dedicated",
        },
    )
    assert poc_plan.status_code == 200
    plan_data = poc_plan.json()
    assert isinstance(plan_data.get("readiness_score"), int)
    assert isinstance(plan_data.get("workplan"), list)

    readiness = client.post(
        "/se/poc-readiness",
        json={
            "user": "se.demo@pingcap.com",
            "account": "Evernorth",
        },
    )
    assert readiness.status_code == 200
    readiness_data = readiness.json()
    assert isinstance(readiness_data.get("required_inputs"), list)

    fit = client.post(
        "/se/architecture-fit",
        json={
            "user": "se.demo@pingcap.com",
            "account": "Evernorth",
        },
    )
    assert fit.status_code == 200
    fit_data = fit.json()
    assert isinstance(fit_data.get("fit_summary"), str)

    coach = client.post(
        "/se/competitor-coach",
        json={
            "user": "se.demo@pingcap.com",
            "account": "Evernorth",
            "competitor": "SingleStore",
        },
    )
    assert coach.status_code == 200
    coach_data = coach.json()
    assert coach_data.get("competitor")
    assert isinstance(coach_data.get("positioning"), list)


def test_marketing_intelligence_endpoint(client):
    _seed_calls(client)

    res = client.post(
        "/marketing/intelligence",
        json={
            "user": "marketing@pingcap.com",
            "regions": ["East", "Central"],
            "verticals": ["Healthcare", "Retail"],
            "lookback_days": 60,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data.get("summary"), str)
    assert isinstance(data.get("top_signals"), list)
    assert isinstance(data.get("next_actions"), list)


def test_feature_flag_can_disable_rep_module(client):
    put = client.put(
        "/admin/kb-config",
        json={
            "feature_flags_json": {
                "rep_account_brief": False,
            }
        },
    )
    assert put.status_code == 200

    res = client.post(
        "/rep/account-brief",
        json={
            "user": "estyn.c@pingcap.com",
            "account": "Evernorth",
        },
    )
    assert res.status_code == 403
