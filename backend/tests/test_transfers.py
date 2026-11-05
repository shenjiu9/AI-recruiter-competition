from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.kernel.types import DomainError
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.modules.requisition.adapters.repository import SqlRepository
from app.modules.requisition.adapters.transfers import DirectoryChangeRecord, TransferNoticeRecord
from app.modules.requisition.contracts import DirectoryChange

ROOT = "/api/v1/hr/requisitions"


def create(client, login, fields, **extra):
    response = client.post(
        ROOT, headers=login(), json={**fields, "employmentType": "外包", "visibleTo": "hr", **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def transfer(client, login, req, user="manager", target="director", key="transfer", **extra):
    return client.post(
        f"{ROOT}/{req['id']}/transfer",
        headers=login(user, key),
        json={
            "expected_version": req["version"],
            "node_id": req["chain"][req["currentNode"]]["id"],
            "target_id": target,
            "reason": "请协助审批",
            **extra,
        },
    )


def approve(client, login, req, user):
    response = client.post(
        f"{ROOT}/{req['id']}/approve",
        headers=login(user, f"approve-{req['version']}"),
        json={
            "expected_version": req["version"],
            "node_id": req["chain"][req["currentNode"]]["id"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def imported_event(
    container, user="manager", supervisor="director", kind="left", event_id="left-1"
):
    with container.db.sessions.begin() as db:
        row = db.get(UserRecord, user)
        row.active = kind != "left"
        row.version += 1
        version = row.version
    return DirectoryChange(
        event_id=event_id, user_id=user, kind=kind, source_version=version, supervisor_id=supervisor
    )


def consume(container, event):
    with container.scope() as services:
        return services.requisition.consume_directory_change(event)


def test_transfer_keeps_node_snapshot_and_idempotent_history(client, login, fields):
    req = create(client, login, fields)
    changed = transfer(client, login, req)
    assert changed.status_code == 200, changed.text
    result = changed.json()
    assert result["version"] == 3 and result["currentNode"] == 0
    assert result["chain"][0]["approver_id"] == "director"
    assert result["history"][0]["chain"] == req["chain"]
    assert result["history"][-1]["comment"] == "请协助审批"
    assert transfer(client, login, req).json() == result
    assert transfer(client, login, req, key="stale").status_code == 409
    assert transfer(client, login, result, key="not-current").status_code == 403
    confirmed = approve(client, login, result, "director")
    assert confirmed["currentNode"] == 1
    assert confirmed["history"][-1]["action"] == "manager_confirmed"


@pytest.mark.parametrize(
    "target,status",
    [
        ("hr", 422),
        ("manager", 422),
        ("sales", 422),
        ("admin", 422),
        ("outsider", 422),
        ("missing", 404),
    ],
)
def test_invalid_transfer_target(client, login, fields, target, status):
    req = create(client, login, fields)
    assert transfer(client, login, req, target=target).status_code == status
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req


@pytest.mark.parametrize("reason", ["", "   ", "x" * 1001])
def test_transfer_reason_required_and_bounded(client, login, fields, reason):
    req = create(client, login, fields)
    assert transfer(client, login, req, reason=reason).status_code == (
        422 if reason == "   " else 400
    )


def test_candidates_scoped_and_current_approver_only(client, login, fields, container):
    req = create(client, login, fields, confidential="1")
    path = f"{ROOT}/{req['id']}/transfer-candidates"
    result = client.get(path, headers=login("manager")).json()
    assert result["items"] == [{"id": "director", "name": "部门负责人"}]
    assert client.get(path + "?q=nobody", headers=login("manager")).json()["total"] == 0
    assert client.get(path, headers=login("hr")).status_code == 403
    assert client.get(path, headers=login("outsider")).status_code == 404
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "director").active = False
    assert client.get(path, headers=login("manager")).json()["total"] == 0
    assert transfer(client, login, req).status_code == 404


def test_salary_transfer_requires_independent_hrd(client, login, fields, container):
    req = create(client, login, fields, salary="8-25K/月×13")
    for user in ("manager", "director", "hrbp"):
        req = approve(client, login, req, user)
    assert req["chain"][req["currentNode"]]["id"] == "salary"
    with container.db.sessions.begin() as db:
        for user in ("manager", "hr", "payroll"):
            row = db.get(UserRecord, user)
            row.roles = [*row.roles, "hrd"]
    for target in ("manager", "hr", "hrd"):
        assert transfer(client, login, req, "salary_hrd", target, key=target).status_code == 422
    changed = transfer(client, login, req, "salary_hrd", "payroll").json()
    assert approve(client, login, changed, "payroll")["status"] == "approved"


def test_notifications_recheck_current_visibility(client, login, fields, container):
    req = create(client, login, fields, confidential="1")
    transfer(client, login, req)
    path = "/api/v1/hr/requisition-notifications"
    assert client.get(path, headers=login()).json()[0]["requisition_id"] == req["id"]
    assert client.get(path, headers=login("outsider")).json() == []
    assert client.get(path, headers=login("admin")).json() == []
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "hr").roles = []
    assert client.get(path, headers=login()).json() == []


def test_departed_current_approver_and_future_node_reconciled(client, login, fields, container):
    req = create(client, login, fields)
    future = imported_event(container, "hrbp", "hrd", event_id="left-hrbp")
    assert consume(container, future)["changed"] == []
    event = imported_event(container)
    # The directory's current department custodian differs from the submitted director snapshot.
    with container.db.sessions.begin() as db:
        dept = db.get(DepartmentRecord, fields["dept"])
        dept.policy = {**dept.policy, "director_id": "hr"}
    first = consume(container, event)
    assert len(first["changed"]) == 1 and first["pending"] == []
    req = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert req["initiator"] == "何美玲" and req["chain"][0]["approver_id"] == "director"
    assert req["history"][-1]["action"] == "auto_transferred"
    assert consume(container, event)["changed"] == []
    req = approve(client, login, req, "director")
    req = approve(client, login, req, "director")
    assert req["chain"][req["currentNode"]]["approver_id"] == "hrd"
    assert approve(client, login, req, "hrd")["status"] == "approved"


def test_creator_departure_handover_preserves_original_author(client, login, fields, container):
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    req = create(client, login, fields, confidential="1")
    event = imported_event(container, "hr", "director")
    assert len(consume(container, event)["changed"]) == 2
    for item in (draft, req):
        data = client.get(f"{ROOT}/{item['id']}", headers=login("director")).json()
        assert data["creatorId"] == "hr" and data["ownerId"] == "director"
        assert data["proxyBy"] == "林悦"
    data = client.get(f"{ROOT}/{req['id']}", headers=login("director")).json()
    req = approve(client, login, data, "manager")
    conflict = client.post(
        f"{ROOT}/{req['id']}/approve",
        headers=login("director"),
        json={"node_id": "director", "expected_version": req["version"]},
    )
    assert conflict.status_code == 409
    withdrawn = client.post(
        f"{ROOT}/{req['id']}/withdraw",
        headers=login("director"),
        json={"expected_version": req["version"]},
    )
    assert withdrawn.status_code == 200


def test_missing_or_ineligible_supervisor_blocks_without_skipping_and_retry_recovers(
    client, login, fields, container
):
    req = create(client, login, fields)
    event = imported_event(container, supervisor="sales")
    result = consume(container, event)
    assert result["pending"] == [{"id": req["id"], "owner": False, "approval": True}]
    blocked = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert blocked["currentNode"] == 0 and blocked["chain"] == req["chain"]
    assert blocked["history"][-1]["action"] == "transfer_blocked"
    assert consume(container, event)["changed"] == []
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "sales").departments = [fields["dept"]]
    assert consume(container, event)["pending"] == []
    fixed = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert fixed["chain"][0]["approver_id"] == "sales"
    assert len(fixed["history"]) == 4


def test_event_rejects_unimported_or_changed_and_stale_payload(client, login, fields, container):
    create(client, login, fields)
    event = DirectoryChange(
        event_id="evt", user_id="manager", source_version=1, kind="left", supervisor_id="director"
    )
    with pytest.raises(DomainError, match="在职状态"):
        consume(container, event)
    event = imported_event(container)
    consume(container, event)
    with pytest.raises(DomainError, match="不能改变内容"):
        consume(container, event.model_copy(update={"supervisor_id": "hr"}))
    newer = imported_event(container, event_id="evt-new")
    consume(container, newer)
    with pytest.raises(DomainError, match="更新的目录事件"):
        consume(container, event)


def test_transfer_races_approval_only_one_wins(client, login, fields, container, monkeypatch):
    req = create(client, login, fields)
    if container.db.engine.dialect.name == "postgresql":
        barrier = Barrier(2, timeout=10)
        original = SqlRepository.save

        def simultaneous(self, *args):
            barrier.wait()
            return original(self, *args)

        monkeypatch.setattr(SqlRepository, "save", simultaneous)
    headers = [login("manager", "race-transfer"), login("manager", "race-approve")]

    def write(which):
        return client.post(
            f"{ROOT}/{req['id']}/{'approve' if which else 'transfer'}",
            headers=headers[which],
            json={
                "expected_version": req["version"],
                "node_id": "manager",
                **({} if which else {"target_id": "director", "reason": "并发转交"}),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, [0, 1]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    final = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert final["version"] == 3 and len(final["history"]) == 2


def test_directory_event_save_failure_rolls_back_receipt_and_notifications(
    client, login, fields, container, monkeypatch
):
    req = create(client, login, fields)
    event = imported_event(container)
    original = SqlRepository.save

    def fail(*args):
        raise DomainError("TEST", "transaction failed", 503)

    monkeypatch.setattr(SqlRepository, "save", fail)
    with pytest.raises(DomainError):
        consume(container, event)
    with container.db.sessions.begin() as db:
        assert db.scalar(select(func.count()).select_from(DirectoryChangeRecord)) == 0
        assert db.scalar(select(func.count()).select_from(TransferNoticeRecord)) == 0
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json()["version"] == 2
    monkeypatch.setattr(SqlRepository, "save", original)
    assert len(consume(container, event)["changed"]) == 1


def test_old_move_event_does_not_reassign_later_submissions(client, login, fields, container):
    event = imported_event(container, kind="moved")
    consume(container, event)
    req = create(client, login, fields)
    assert consume(container, event) == {"event_id": event.event_id, "changed": [], "pending": []}
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req


def test_move_event_transfers_current_node_and_later_manual_assignment_wins(
    client, login, fields, container
):
    req = create(client, login, fields)
    event = imported_event(container, kind="moved")
    assert len(consume(container, event)["changed"]) == 1
    req = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    assert req["ownerId"] == "hr" and req["chain"][0]["approver_id"] == "director"
    response = transfer(client, login, req, "director", "manager")
    assert response.status_code == 200, response.text
    assert consume(container, event) == {"event_id": event.event_id, "changed": [], "pending": []}
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == response.json()


def test_missing_supervisor_and_owner_remain_pending_without_repeated_notices(
    client, login, fields, container
):
    req = create(client, login, fields)
    event = imported_event(container, supervisor=None)
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "director").active = False
    result = consume(container, event)
    assert result["pending"] == [{"id": req["id"], "owner": True, "approval": True}]
    with container.db.sessions.begin() as db:
        count = db.scalar(select(func.count()).select_from(TransferNoticeRecord))
    assert consume(container, event)["changed"] == []
    with container.db.sessions.begin() as db:
        assert db.scalar(select(func.count()).select_from(TransferNoticeRecord)) == count


def test_transferred_confirmation_can_change_conditions_after_old_manager_left(
    client, login, fields, container
):
    req = create(client, login, fields)
    event = imported_event(container)
    consume(container, event)
    req = client.get(f"{ROOT}/{req['id']}", headers=login()).json()
    response = client.post(
        f"{ROOT}/{req['id']}/confirm",
        headers=login("director"),
        json={
            "expected_version": req["version"],
            "fields": {"salary": "8-25K/月×13", "hcRequest": "1"},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["chain"][0]["approver_id"] == "director"
    assert [node["id"] for node in data["chain"]] == ["manager", "director", "hrbp", "hc", "salary"]
    assert data["history"][0]["chain"][0]["approver_id"] == "manager"


def test_inherited_request_resubmission_routes_around_custodian(client, login, fields, container):
    req = create(client, login, fields)
    event = imported_event(container, "hr", "director")
    consume(container, event)
    req = client.get(f"{ROOT}/{req['id']}", headers=login("director")).json()
    withdrawn = client.post(
        f"{ROOT}/{req['id']}/withdraw",
        headers=login("director"),
        json={"expected_version": req["version"]},
    ).json()
    submitted = client.post(
        f"{ROOT}/{req['id']}/submit",
        headers=login("director"),
        json={"expected_version": withdrawn["version"]},
    )
    assert submitted.status_code == 200, submitted.text
    req = submitted.json()
    assert req["chain"][1]["approver_id"] == "hrd"
    for user in ("manager", "hrd", "hrbp"):
        req = approve(client, login, req, user)
    assert req["status"] == "approved"


def test_terminal_requests_not_changed_and_old_token_denied(client, login, fields, container):
    req = create(client, login, fields)
    old_token = login("hr")
    for user in ("manager", "director", "hrbp"):
        req = approve(client, login, req, user)
    event = imported_event(container, "hr", "director")
    assert consume(container, event)["changed"] == []
    assert client.get(f"{ROOT}/{req['id']}", headers=old_token).status_code == 401
    assert client.get(f"{ROOT}/{req['id']}", headers=login("manager")).json() == req


def test_transfer_revalidates_permissions_after_candidate_lookup(client, login, fields, container):
    req = create(client, login, fields)
    path = f"{ROOT}/{req['id']}/transfer-candidates"
    assert client.get(path, headers=login("manager")).json()["total"] == 1
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "director").directory_departments = []
    assert transfer(client, login, req).status_code == 422
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "manager").directory_roles = []
    assert transfer(client, login, req, key="revoked").status_code in {404, 422}


def test_duplicate_directory_deliveries_are_serialized(client, login, fields, container):
    create(client, login, fields)
    event = imported_event(container)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(container, event), [0, 1]))
    assert sorted(len(r["changed"]) for r in results) == [0, 1]
    with container.db.sessions.begin() as db:
        assert db.scalar(select(func.count()).select_from(DirectoryChangeRecord)) == 1
