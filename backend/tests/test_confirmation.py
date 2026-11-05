import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from test_requisition_api import ROOT, create
from test_salary import approve, save

from app.kernel.types import DomainError
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.modules.requisition.adapters.orm import RequisitionRecord
from app.modules.requisition.adapters.repository import SqlRepository
from app.platform.records import AuditRecord, EventRecord, RequestRecord


def test_legacy_payload_remains_readable_but_amendment_requires_resubmit(
    client, login, fields, container
):
    req = create(client, login, fields)
    with container.db.sessions.begin() as db:
        record = db.get(RequisitionRecord, req["id"])
        payload = container.crypto.decrypt(record.data, record.id)
        for key in ("approval_policy", "salary_review", "submitted_fields"):
            payload.pop(key)
        record.data = container.crypto.encrypt(payload, record.id)
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).status_code == 200
    response = confirm(client, login, req, {"title": "修改旧需求"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REQ_RESUBMIT_REQUIRED"
    assert confirm(client, login, req).status_code == 200


def test_removing_extra_hc_removes_only_conditional_node(client, login, fields):
    req = create(client, login, {**fields, "headcount": "3", "hcRequest": "1"})
    response = confirm(client, login, req, {"headcount": "2", "hcRequest": "0"})
    assert response.status_code == 200, response.text
    assert [n["id"] for n in response.json()["chain"]] == ["manager", "director", "hrbp"]


def confirm(client, login, req, patch=None, user="manager", key="confirm", endpoint="confirm"):
    return client.post(
        f"{ROOT}/{req['id']}/{endpoint}",
        headers=login(user, key),
        json={"expected_version": req["version"], "fields": patch or {}},
    )


def test_preview_is_read_only_confirm_records_encrypted_diff_and_replays(
    client, login, fields, container
):
    req = create(client, login, fields)
    patch = {"headcount": "1", "duties": "  独立处理升级投诉  ", "salary": "8-25K/月×13"}
    preview = confirm(client, login, req, patch, endpoint="confirmation-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["changes"]["duties"] == {
        "before": fields["duties"],
        "after": "独立处理升级投诉",
    }
    assert preview.json()["chain"][-1]["id"] == "salary"
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req
    result = confirm(client, login, req, patch)
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated["currentNode"] == 1 and updated["version"] == req["version"] + 1
    assert updated["history"][-1]["changes"] == preview.json()["changes"]
    assert updated["history"][-1]["action"] == "manager_confirmed"
    assert confirm(client, login, req, patch).json() == updated
    assert confirm(client, login, req, {"title": "different"}).status_code == 409
    with container.db.sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "requisition.manager_confirmed")
            )
            == 1
        )
        record = db.get(RequisitionRecord, req["id"])
        assert b"8-25" not in record.data and "独立处理".encode() not in record.data
        logs = list(db.scalars(select(AuditRecord)))
        assert "8-25" not in json.dumps([(x.before, x.after) for x in logs])
    # The added HRD really gates final approval, and the updated count is reserved.
    updated = approve(client, login, updated)
    updated = approve(client, login, updated)
    assert (
        updated["status"] == "in_approval"
        and updated["chain"][updated["currentNode"]]["id"] == "salary"
    )
    assert approve(client, login, updated)["status"] == "approved"
    with container.scope() as services:
        assert services.org.headcount(fields["dept"])["reserved"] == 1


@pytest.mark.parametrize(
    "user,status", [("hr", 403), ("director", 403), ("hrbp", 403), ("outsider", 404)]
)
def test_only_current_manager_can_preview_or_confirm(client, login, fields, user, status):
    req = create(client, login, fields)
    for endpoint in ["confirmation-preview", "confirm"]:
        assert (
            confirm(
                client, login, req, {"title": "非法修改"}, user=user, endpoint=endpoint
            ).status_code
            == status
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"dept": "财务部"},
        {"confidential": "1"},
        {"visibleTo": "outsider"},
        {"recruiterId": "manager"},
        {"custom_override": "yes"},
    ],
)
def test_identity_and_visibility_fields_locked(client, login, fields, patch):
    req = create(client, login, fields)
    response = confirm(client, login, req, patch)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "REQ_CONFIRM_FIELD_LOCKED"
    )
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req


@pytest.mark.parametrize(
    "patch",
    [
        {"headcount": "3"},
        {"headcount": "0"},
        {"salary": "bad"},
        {"series": "未配置"},
        {"title": "仅限男性客服"},
        {"expectedOnboard": "2000-01-01"},
        {"requirements": ""},
    ],
)
def test_invalid_changes_block_and_leave_no_partial_writes(client, login, fields, container, patch):
    req = create(client, login, fields)
    with container.db.sessions() as db:
        before = [
            db.scalar(select(func.count()).select_from(t))
            for t in (AuditRecord, EventRecord, RequestRecord)
        ]
    response = confirm(client, login, req, patch)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "REQ_PENDING_DECISIONS"
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req
    with container.db.sessions() as db:
        assert before == [
            db.scalar(select(func.count()).select_from(t))
            for t in (AuditRecord, EventRecord, RequestRecord)
        ]
    assert confirm(client, login, req, {"title": "合法客服"}).status_code == 200


def test_hc_addition_and_salary_removal_use_original_routing(client, login, fields, container):
    req = create(client, login, {**fields, "salary": "8-25K/月×13"})
    with container.db.sessions.begin() as db:
        dept = db.get(DepartmentRecord, fields["dept"])
        dept.policy = {
            **dept.policy,
            "director_id": "hr",
            "hc_owner_id": "hrbp",
            "hrd_id": "manager",
        }
    response = confirm(
        client, login, req, {"salary": "8-12K/月×13", "headcount": "3", "hcRequest": "1"}
    )
    assert response.status_code == 200, response.text
    chain = response.json()["chain"]
    assert [(n["id"], n["approver_id"]) for n in chain] == [
        ("manager", "manager"),
        ("director", "director"),
        ("hrbp", "hrbp"),
        ("hc", "hrd"),
    ]


def test_salary_change_uses_current_band_with_snapshotted_hrd(client, login, fields, container):
    req = create(client, login, fields)
    assert save(client, login, container, upper=10).status_code == 200
    with container.db.sessions.begin() as db:
        dept = db.get(DepartmentRecord, fields["dept"])
        dept.policy = {**dept.policy, "hrd_id": "manager"}
    changed = confirm(client, login, req, {"salary": "8-15K/月×13"}).json()
    assert changed["chain"][-1]["approver_id"] == "salary_hrd"
    assert changed["history"][-1]["salary_rules"][0]["version"] == 2


def test_unrelated_change_keeps_submitted_salary_rules(client, login, fields, container):
    req = create(client, login, fields)
    assert save(client, login, container, upper=10).status_code == 200
    changed = confirm(client, login, req, {"reason": "补充背景"}).json()
    assert changed["chain"] == req["chain"]
    assert changed["history"][-1]["salary_rules"] == req["history"][-1]["salary_rules"]


@pytest.mark.parametrize("hrd", [None, "manager", "hr"])
def test_cannot_add_missing_or_self_hrd(client, login, fields, container, hrd):
    with container.db.sessions.begin() as db:
        dept = db.get(DepartmentRecord, fields["dept"])
        dept.policy = {**dept.policy, "hrd_id": hrd}
        if hrd:
            user = db.get(UserRecord, hrd)
            user.roles = [*user.roles, "hrd"]
    req = create(client, login, fields)
    response = confirm(client, login, req, {"salary": "8-25K/月×13"})
    assert response.status_code == 422
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req


def test_manager_submitting_proxy_draft_cannot_skip_confirmation(client, login, fields):
    req = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    response = client.post(
        f"{ROOT}/{req['id']}/submit", headers=login("manager"), json={"expected_version": 1}
    )
    assert response.status_code == 200, response.text
    assert response.json()["chain"][0]["approver_id"] == "manager"
    assert response.json()["mode"] == "proxy"


def test_no_edit_confirmation_and_later_node_cannot_amend(client, login, fields):
    req = create(client, login, fields)
    updated = confirm(client, login, req).json()
    assert updated["fields"] == req["fields"] and updated["history"][-1]["changes"] == {}
    assert confirm(client, login, updated, {"title": "迟到修改"}, key="again").status_code == 409
    assert confirm(client, login, req, key="stale").status_code == 409


def test_concurrent_confirmation_and_withdraw_have_one_winner(
    client, login, fields, container, monkeypatch
):
    req = create(client, login, fields)
    if container.db.engine.dialect.name == "postgresql":
        gate = Barrier(2, timeout=10)
        original = SqlRepository.save

        def simultaneous(self, *args):
            gate.wait()
            return original(self, *args)

        monkeypatch.setattr(SqlRepository, "save", simultaneous)
    manager, hr = login("manager", "race-confirm"), login("hr", "race-withdraw")

    def action(which):
        return client.post(
            f"{ROOT}/{req['id']}/{'confirm' if which else 'withdraw'}",
            headers=manager if which else hr,
            json={
                "expected_version": req["version"],
                **({"fields": {"title": "并发确认"}} if which else {}),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(action, [True, False]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    final = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert final["version"] == 3 and len(final["history"]) == 2
    assert final["fields"]["title"] == (
        "并发确认" if final["status"] == "in_approval" else fields["title"]
    )


def test_save_failure_rolls_back_changes_and_allows_same_key_retry(
    client, login, fields, monkeypatch
):
    req = create(client, login, fields)
    original = SqlRepository.save

    def fail(*args):
        raise DomainError("VERSION_CONFLICT", "injected failure", 409)

    monkeypatch.setattr(SqlRepository, "save", fail)
    assert confirm(client, login, req, {"title": "确认保存"}).status_code == 409
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req
    monkeypatch.setattr(SqlRepository, "save", original)
    assert confirm(client, login, req, {"title": "确认保存"}).status_code == 200


def test_resubmission_records_difference_from_previous_submission(client, login, fields):
    req = create(client, login, fields)
    path = f"{ROOT}/{req['id']}"
    rejected = client.post(
        path + "/reject",
        headers=login("manager"),
        json={"expected_version": 2, "node_id": "manager", "reason": "补充职责"},
    ).json()
    response = client.post(
        path + "/submit",
        headers=login(),
        json={"expected_version": rejected["version"], "fields": {"duties": "处理咨询并跟进投诉"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["history"][-1]["changes"] == {
        "duties": {"before": fields["duties"], "after": "处理咨询并跟进投诉"}
    }
    assert response.json()["currentNode"] == 0
