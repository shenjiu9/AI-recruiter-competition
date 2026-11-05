from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import func, select

from app.modules.org.adapters.repository import UserRecord
from app.modules.requisition.adapters.orm import RequisitionRecord
from app.platform.records import AuditRecord, EventRecord, RequestRecord

ROOT = "/api/v1/hr/requisitions"


def create(client, login, fields, user="hr", key="create"):
    response = client.post(ROOT, json=fields, headers=login(user, key))
    assert response.status_code == 201, response.text
    return response.json()


def test_manual_request_approval_chain_and_event_journal(client, login, fields, container):
    req = create(client, login, fields)
    assert req["status"] == "in_approval" and req["version"] == 2
    assert req["chain"][0]["approver_id"] == "manager"
    assert req["mode"] == "proxy"
    for actor in ["manager", "director", "hrbp"]:
        inbox = client.get("/api/v1/biz/inbox", headers=login(actor)).json()
        assert any(row["id"] == req["id"] for row in inbox)
        node = req["chain"][req["currentNode"]]
        response = client.post(
            f"{ROOT}/{req['id']}/approve",
            headers=login(actor),
            json={"node_id": node["id"], "expected_version": req["version"]},
        )
        assert response.status_code == 200, response.text
        req = response.json()
    assert req["status"] == "approved"
    with container.db.sessions() as db:
        events = list(db.scalars(select(EventRecord).order_by(EventRecord.occurred_at)))
        assert events[-1].type == "requisition.approved"
        assert all(set(e.payload) == {"requisition_id", "version"} for e in events)
        assert db.scalar(select(func.count()).select_from(AuditRecord)) == 6
        encrypted = db.get(RequisitionRecord, req["id"]).data
        assert b"8-12" not in encrypted
        assert db.scalar(select(RequestRecord)).response is not None


def test_idempotency_replay_and_body_conflict(client, login, fields, container):
    first = create(client, login, fields)
    assert create(client, login, fields) == first
    changed = client.post(
        ROOT, headers=login("hr", "create"), json={**fields, "title": "另一个职位"}
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(RequisitionRecord)) == 1


def test_rejected_submission_rolls_back_everything(client, login, fields, container):
    response = client.post(ROOT, headers=login(), json={**fields, "headcount": "3"})
    assert response.status_code == 422
    with container.db.sessions() as db:
        for table in (RequisitionRecord, EventRecord, AuditRecord, RequestRecord):
            assert db.scalar(select(func.count()).select_from(table)) == 0
    # A failed request does not poison its key.
    assert client.post(ROOT, headers=login(), json=fields).status_code == 201


def test_draft_update_conflict_withdraw_resubmit(client, login, fields):
    draft = client.post(
        ROOT + "/drafts", headers=login(), json={"dept": "客服中心", "title": "半成品"}
    ).json()
    path = f"{ROOT}/{draft['id']}"
    updated = client.patch(path, headers=login(), json={"fields": fields, "expected_version": 1})
    assert updated.status_code == 200
    conflict = client.patch(
        path, headers=login(key="other"), json={"fields": {"title": "覆盖"}, "expected_version": 1}
    )
    assert conflict.status_code == 409
    req = client.post(path + "/submit", headers=login(), json={"expected_version": 2}).json()
    req = client.post(
        path + "/withdraw", headers=login(), json={"expected_version": req["version"]}
    ).json()
    assert req["status"] == "withdrawn"
    req = client.post(
        path + "/submit", headers=login(key="resubmit"), json={"expected_version": req["version"]}
    ).json()
    assert req["status"] == "in_approval" and req["currentNode"] == 0
    assert [item["action"] for item in req["history"]] == ["submitted", "withdrawn", "submitted"]


def test_wrong_actor_cannot_approve_and_rejection_requires_reason(client, login, fields):
    req = create(client, login, fields)
    path = f"{ROOT}/{req['id']}"
    body = {"node_id": "manager", "expected_version": 2}
    assert client.post(path + "/approve", headers=login("hr"), json=body).status_code == 403
    assert (
        client.post(
            path + "/reject", headers=login("manager"), json={**body, "reason": "   "}
        ).status_code
        == 422
    )
    response = client.post(
        path + "/reject", headers=login("manager"), json={**body, "reason": "调整人数"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert (
        client.post(path + "/approve", headers=login("manager", "another"), json=body).status_code
        == 409
    )


def test_data_scope_and_confidential_visibility(client, login, fields):
    req = create(client, login, {**fields, "confidential": "1", "visibleTo": "hrbp"})
    assert client.get(f"{ROOT}/{req['id']}", headers=login("outsider")).status_code == 404
    assert client.get(ROOT, headers=login("outsider")).json()["items"] == []
    assert client.get(f"{ROOT}/{req['id']}", headers=login("sales")).status_code == 404
    assert client.post(ROOT, headers=login("outsider"), json=fields).status_code == 403


def test_pagination(client, login, fields):
    for index in range(3):
        create(client, login, fields, key=f"create-{index}")
    first = client.get(ROOT + "?page=1&size=2", headers=login()).json()
    second = client.get(ROOT + "?page=2&size=2", headers=login()).json()
    assert first["total"] == 3
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert {r["id"] for r in first["items"]}.isdisjoint(r["id"] for r in second["items"])


@pytest.mark.parametrize(
    "patch",
    [
        {"headcount": "0"},
        {"headcount": "1.5"},
        {"headcount": "1000"},
        {"salary": "12-8K"},
        {"expectedOnboard": "下个月"},
        {"title": "男性优先"},
        {"reqType": "替补"},
        {"reqType": "追加", "positionId": "fake"},
        {"reportTo": "不存在的负责人"},
        {"series": ""},
        {"confidential": "1"},
    ],
)
def test_precheck_enforced_server_side(client, login, fields, patch):
    response = client.post(ROOT, headers=login(), json={**fields, **patch})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQ_PENDING_DECISIONS"


def test_headcount_request_and_salary_add_signoff(client, login, fields):
    req = create(client, login, {**fields, "headcount": "3", "hcRequest": "1", "salary": "20-25K"})
    assert [(n["id"], n["approver_id"]) for n in req["chain"][-2:]] == [
        ("hc", "hrd"),
        ("salary", "salary_hrd"),
    ]
    req = create(client, login, fields, user="manager", key="self")
    assert req["mode"] == "self" and req["chain"][0]["approver_id"] == "director"


def test_auth_errors_validation_trace_and_dev_gate(client, login, fields, container):
    assert client.get(ROOT).status_code == 401
    assert client.get(ROOT, headers={"Authorization": "Bearer demo"}).status_code == 401
    response = client.post(ROOT, json=fields, headers={"Authorization": login()["Authorization"]})
    assert response.status_code == 400
    assert response.json()["error"]["trace_id"] == response.headers["X-Trace-ID"]
    response = client.post(ROOT, headers=login(), json={"headcount": 2})
    assert response.status_code == 400 and "input" not in response.text
    container.settings.dev_auth_enabled = False
    assert (
        client.post(
            "/api/v1/auth/dev-login", json={"user_id": "hr", "password": "test-password"}
        ).status_code
        == 404
    )


def test_expired_token_and_disabled_user(client, login, container):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "hr",
            "iat": now - timedelta(hours=9),
            "exp": now - timedelta(hours=1),
            "aud": "recruiter",
            "iss": "recruiter-api",
        },
        container.settings.signing_key,
        algorithm="HS256",
    )
    assert client.get(ROOT, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    headers = login()
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "hr").active = False
    assert client.get(ROOT, headers=headers).status_code == 401


def test_ai_is_explicitly_unavailable(client, login):
    response = client.post(ROOT + "/ai-fill", json={"text": "招人"}, headers=login())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_DEGRADED"


def test_update_and_submit_is_one_transaction(client, login, fields):
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    path = f"{ROOT}/{draft['id']}"
    result = client.post(
        path + "/submit",
        headers=login(),
        json={
            "fields": {**fields, "headcount": "4"},
            "expected_version": 1,
        },
    )
    assert result.status_code == 422
    fresh = client.get(path, headers=login()).json()
    assert fresh["version"] == 1 and fresh["fields"]["headcount"] == "2"
    result = client.post(
        path + "/submit",
        headers=login(),
        json={
            "fields": {**fields, "title": "重新填写后提交"},
            "expected_version": 1,
        },
    )
    assert result.status_code == 200
    assert result.json()["status"] == "in_approval"


def test_sensitive_scope_is_rechecked_on_replay(client, login, fields, container):
    headers = login(key="cached-create")
    create(client, login, fields, key="cached-create")
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "hr").active = False
    assert client.post(ROOT, headers=headers, json=fields).status_code == 401


def test_concurrent_stale_updates_only_one_wins(client, login, fields):
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    headers = [login(key=f"parallel-{n}") for n in range(2)]

    def update(n):
        return client.patch(
            f"{ROOT}/{draft['id']}",
            headers=headers[n],
            json={
                "fields": {"title": f"新名称{n}"},
                "expected_version": 1,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(update, range(2))) == [200, 409]
