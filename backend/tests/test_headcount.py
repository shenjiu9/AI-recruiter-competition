from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.kernel.types import DomainError
from app.modules.org.adapters.headcount import HeadcountRecord, ReservationRecord, SqlHeadcount
from app.modules.org.adapters.repository import DepartmentRecord
from app.modules.requisition.adapters.repository import SqlRepository
from app.platform.records import AuditRecord, EventRecord

ROOT = "/api/v1/hr/requisitions"
HC = "/api/v1/admin/headcount"
DEPT = "客服中心"


def plan(client, login, container):
    response = client.get(HC, params={"year": container.clock.now().year}, headers=login("hrbp"))
    assert response.status_code == 200, response.text
    return next(p for p in response.json()["items"] if p["dept"] == DEPT)


def maintain(client, login, container, **changes):
    row = plan(client, login, container)
    command = {key: row[key] for key in ("year", "planned", "used", "frozen", "effective_from")}
    command.update(expected_version=row["version"], **changes)
    return client.post(
        HC, params={"dept": DEPT}, json=command, headers=login("hrbp", f"plan-{row['version']}")
    )


def submit(client, login, fields, key):
    response = client.post(ROOT, json=fields, headers=login(key=key))
    assert response.status_code == 201, response.text
    return response.json()


def decide(client, login, req, key=None):
    node = req["chain"][req["currentNode"]]
    return client.post(
        f"{ROOT}/{req['id']}/approve",
        headers=login(node["approver_id"], key or f"{req['id']}-{req['version']}"),
        json={"node_id": node["id"], "expected_version": req["version"]},
    )


def to_final(client, login, fields, key):
    req = submit(client, login, fields, key)
    for _ in range(2):
        response = decide(client, login, req)
        assert response.status_code == 200, response.text
        req = response.json()
    return req


def test_maintenance_scope_idempotency_versions_and_audit(client, login, container):
    row = plan(client, login, container)
    assert row["available"] == 2
    command = {
        "year": row["year"],
        "expected_version": row["version"],
        "planned": 5,
        "used": 1,
        "frozen": False,
        "effective_from": row["effective_from"],
    }
    for actor in ("hr", "manager", "outsider"):
        assert (
            client.post(HC, params={"dept": DEPT}, json=command, headers=login(actor)).status_code
            == 403
        )
        assert client.get(HC, params={"year": row["year"]}, headers=login(actor)).status_code == 403
    assert (
        client.post(
            HC, params={"dept": "其他部门"}, json=command, headers=login("hrbp")
        ).status_code
        == 403
    )
    headers = login("hrbp", "change-plan")
    first = client.post(HC, params={"dept": DEPT}, json=command, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["available"] == 4
    assert (
        client.post(HC, params={"dept": DEPT}, json=command, headers=headers).json() == first.json()
    )
    assert (
        client.post(
            HC, params={"dept": DEPT}, json=command, headers=login("hrbp", "stale-plan")
        ).status_code
        == 409
    )
    assert (
        client.post(
            HC, params={"dept": DEPT}, json={**command, "reserved": 0}, headers=login("hrbp")
        ).status_code
        == 400
    )
    with container.db.sessions() as db:
        audit = db.scalars(
            select(AuditRecord).where(AuditRecord.action == "org.headcount_updated")
        ).one()
        assert audit.before["planned"] == 2 and audit.after["planned"] == 5


def test_final_shortage_adds_snapshot_approver_and_reserves_only_after_capacity_fixed(
    client, login, container, fields
):
    req = to_final(client, login, fields, "shortage")
    assert maintain(client, login, container, planned=1).status_code == 200
    with container.db.sessions.begin() as db:
        dept = db.get(DepartmentRecord, DEPT)
        dept.policy = {**dept.policy, "hc_owner_id": "outsider"}
    req = decide(client, login, req).json()
    assert req["status"] == "in_approval" and req["chain"][-1]["approver_id"] == "hrd"
    assert req["chain"][-1]["id"] == "hc_final"
    assert decide(client, login, req).status_code == 409
    assert plan(client, login, container)["reserved"] == 0
    with container.db.sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.type == "requisition.approved")
            )
            == 0
        )
    assert maintain(client, login, container, planned=3).status_code == 200
    approved = decide(client, login, req)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    # Retried success is replayed; a fresh key cannot decrement capacity twice.
    assert decide(client, login, req).json() == approved.json()
    assert decide(client, login, req, "retry-new-key").status_code == 409
    assert plan(client, login, container)["reserved"] == 2
    assert maintain(client, login, container, planned=1).status_code == 409


@pytest.mark.parametrize("employment", ["外包", "实习"])
def test_nonformal_does_not_reserve_frozen_capacity(client, login, container, fields, employment):
    assert maintain(client, login, container, frozen=True).status_code == 200
    req = to_final(client, login, {**fields, "employmentType": employment}, "nonformal")
    assert decide(client, login, req).json()["status"] == "approved"
    assert plan(client, login, container)["reserved"] == 0


def test_frozen_and_missing_plans_block_formal_submission(client, login, container, fields):
    assert maintain(client, login, container, frozen=True).status_code == 200
    assert client.post(ROOT, json={**fields, "hcRequest": "2"}, headers=login()).status_code == 422
    with container.db.sessions.begin() as db:
        db.delete(db.get(HeadcountRecord, (DEPT, container.clock.now().year)))
    response = client.post(ROOT, json={**fields, "hcRequest": "2"}, headers=login())
    assert response.status_code == 422 and "hc_plan" in response.text


def test_stale_warning_future_effective_date_and_reservation_does_not_refresh_data(
    client, login, container, fields
):
    with container.db.sessions.begin() as db:
        db.get(HeadcountRecord, (DEPT, container.clock.now().year)).updated_on = (
            container.clock.now().date() - timedelta(days=31)
        )
    assert plan(client, login, container)["stale"]
    response = client.post(ROOT + "/precheck", headers=login(), json=fields)
    assert any(c["key"] == "hc_stale" and c["status"] == "warn" for c in response.json())
    req = to_final(client, login, fields, "stale")
    assert decide(client, login, req).json()["status"] == "approved"
    assert plan(client, login, container)["stale"]


def synchronize_postgres(container, monkeypatch):
    if container.db.engine.dialect.name == "postgresql":
        barrier = Barrier(2, timeout=10)
        original = SqlHeadcount.reserve

        def simultaneous(self, *args):
            barrier.wait()
            return original(self, *args)

        monkeypatch.setattr(SqlHeadcount, "reserve", simultaneous)


def test_concurrent_final_approvals_cannot_oversubscribe(
    client, login, container, fields, monkeypatch
):
    requests = [to_final(client, login, fields, f"competing-{i}") for i in range(2)]
    headers = [login("hrbp", f"final-{i}") for i in range(2)]
    synchronize_postgres(container, monkeypatch)

    def finish(index):
        req = requests[index]
        return client.post(
            f"{ROOT}/{req['id']}/approve",
            headers=headers[index],
            json={"node_id": "hrbp", "expected_version": req["version"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(finish, range(2)))
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert sorted(r.json()["status"] for r in responses) == ["approved", "in_approval"]
    assert plan(client, login, container)["reserved"] == 2
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ReservationRecord)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.type == "requisition.approved")
            )
            == 1
        )


def test_racing_same_final_decision_rolls_back_extra_reservation(
    client, login, container, fields, monkeypatch
):
    assert maintain(client, login, container, planned=10).status_code == 200
    req = to_final(client, login, fields, "same-final")
    headers = [login("hrbp", f"race-final-{i}") for i in range(2)]
    synchronize_postgres(container, monkeypatch)

    def finish(index):
        return client.post(
            f"{ROOT}/{req['id']}/approve",
            headers=headers[index],
            json={"node_id": "hrbp", "expected_version": req["version"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(finish, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    assert plan(client, login, container)["reserved"] == 2
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ReservationRecord)) == 1


def test_freeze_after_submission_redirects_and_withdraw_does_not_leak_capacity(
    client, login, container, fields
):
    req = to_final(client, login, fields, "freeze-in-flight")
    assert maintain(client, login, container, frozen=True).status_code == 200
    req = decide(client, login, req).json()
    assert req["chain"][-1]["id"] == "hc_final"
    response = client.post(
        f"{ROOT}/{req['id']}/withdraw", headers=login(), json={"expected_version": req["version"]}
    )
    assert response.status_code == 200
    assert plan(client, login, container)["reserved"] == 0


def test_reservation_rolls_back_if_request_save_fails(
    client, login, container, fields, monkeypatch
):
    req = to_final(client, login, fields, "save-failure")
    original_save = SqlRepository.save

    def fail_save(self, req, expected):
        if req.status == "approved":
            raise DomainError("VERSION_CONFLICT", "injected concurrent modification", 409)
        return original_save(self, req, expected)

    monkeypatch.setattr(SqlRepository, "save", fail_save)
    assert decide(client, login, req).status_code == 409
    assert plan(client, login, container)["reserved"] == 0
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ReservationRecord)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "org.headcount_reserved")
            )
            == 0
        )
    monkeypatch.setattr(SqlRepository, "save", original_save)
    assert decide(client, login, req).json()["status"] == "approved"


def test_future_plan_creation_and_duplicate_create(client, login, container):
    year = container.clock.now().year + 1
    command = {
        "year": year,
        "expected_version": 0,
        "planned": 10,
        "used": 3,
        "frozen": False,
        "effective_from": f"{year}-01-01",
    }
    result = client.post(HC, params={"dept": DEPT}, json=command, headers=login("hrbp", "future"))
    assert result.status_code == 200 and result.json()["available"] == 7
    assert (
        client.post(
            HC, params={"dept": DEPT}, json=command, headers=login("hrbp", "duplicate-future")
        ).status_code
        == 409
    )
    # Planning next year must not change this year's availability.
    assert plan(client, login, container)["available"] == 2
