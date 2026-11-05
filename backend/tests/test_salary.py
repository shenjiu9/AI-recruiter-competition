import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.modules.org.adapters.salary import SalaryBandRecord, SalaryRevisionRecord, SqlSalary
from app.platform.records import AuditRecord

ROOT = "/api/v1/hr/requisitions"
SALARY = "/api/v1/admin/salary-bands"


def command(container, **changes):
    return {
        "series": "客服",
        "grade": "P3",
        "city": "深圳",
        "lower": 5,
        "upper": 20,
        "months": 13,
        "effective_from": container.clock.now().date().isoformat(),
        "expected_version": 1,
        **changes,
    }


def save(client, login, container, key="salary-save", **changes):
    return client.post(SALARY, json=command(container, **changes), headers=login("hr", key))


def submit(client, login, fields, key="submit"):
    return client.post(ROOT, json=fields, headers=login("hr", key))


def approve(client, login, req):
    node = req["chain"][req["currentNode"]]
    response = client.post(
        f"{ROOT}/{req['id']}/approve",
        headers=login(node["approver_id"], f"approve-{req['version']}"),
        json={"node_id": node["id"], "expected_version": req["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "patch",
    [
        {"series": "不存在"},
        {"level": "P4"},
        {"city": "北京"},
        {"level": "P5-P3"},
        {"level": "P1-M3"},
        {"level": "P1-P99"},
    ],
)
def test_missing_salary_dimension_blocks_submit_but_allows_draft(client, login, fields, patch):
    response = submit(client, login, {**fields, **patch})
    assert response.status_code == 422 and "salary_config" in response.text
    assert (
        client.post(ROOT + "/drafts", json={**fields, **patch}, headers=login()).status_code == 201
    )


@pytest.mark.parametrize("salary", ["4-12K/月×13", "8-21K/月×13", "8-20K/月×14", "5-12K/月×12"])
def test_lower_upper_and_annual_bounds_add_independent_hrd(client, login, fields, salary):
    response = submit(client, login, {**fields, "salary": salary})
    assert response.status_code == 201, response.text
    req = response.json()
    assert [(n["id"], n["approver_id"]) for n in req["chain"]] == [
        ("manager", "manager"),
        ("director", "director"),
        ("hrbp", "hrbp"),
        ("salary", "salary_hrd"),
    ]
    for _ in range(3):
        req = approve(client, login, req)
    assert req["status"] == "in_approval"
    assert req["waitingFor"] == "薪酬审批负责人"
    assert approve(client, login, req)["status"] == "approved"


def test_grade_range_requires_all_rows_and_uses_combined_bounds(client, login, container, fields):
    fields = {**fields, "level": "p3–P4", "salary": "5-30K/月×13"}
    assert submit(client, login, fields).status_code == 422
    assert (
        save(
            client, login, container, grade="P4", lower=10, upper=30, expected_version=0
        ).status_code
        == 200
    )
    req = submit(client, login, fields).json()
    assert [n["id"] for n in req["chain"]] == ["manager", "director", "hrbp"]
    assert len(req["history"][-1]["salary_rules"]) == 2
    assert submit(client, login, {**fields, "level": "P3-P5"}, "missing-middle").status_code == 422


def test_config_authorization_history_encryption_idempotency_and_conflicts(
    client, login, container
):
    row = save(client, login, container, upper=321.23)
    assert row.status_code == 200, row.text
    row = row.json()
    assert row["version"] == 2 and row["active"]["upper"] == 321.23
    assert save(client, login, container, upper=321.23).json() == row
    assert save(client, login, container, key="new-stale-key", upper=321.23).status_code == 409
    history_url = f"{SALARY}/{row['id']}/history"
    history = client.get(history_url, headers=login("payroll")).json()
    assert [r["version"] for r in history] == [2, 1]
    assert history[1]["upper"] == 20
    for user in ["manager", "hrbp", "outsider", "salary_hrd"]:
        assert client.get(SALARY, headers=login(user)).status_code == 403
        assert client.get(history_url, headers=login(user)).status_code == 403
        assert client.post(SALARY, json=command(container), headers=login(user)).status_code == 403
    assert client.get(SALARY).status_code == 401
    with container.db.sessions() as db:
        revision = db.get(SalaryRevisionRecord, (row["id"], 2))
        assert b"321.23" not in revision.data
        audit = db.scalars(
            select(AuditRecord).where(AuditRecord.action == "org.salary_updated")
        ).one()
        assert "321.23" not in json.dumps(audit.after) and "upper" not in audit.after
    payroll = client.post(
        SALARY, json=command(container, expected_version=2, upper=22), headers=login("payroll")
    )
    assert payroll.status_code == 200


def test_future_versions_do_not_apply_early_and_can_be_superseded(client, login, container, fields):
    future = (container.clock.now().date() + timedelta(days=10)).isoformat()
    row = save(client, login, container, upper=10, effective_from=future).json()
    assert row["active"]["version"] == 1 and row["latest"]["version"] == 2
    assert [n["id"] for n in submit(client, login, fields).json()["chain"]] == [
        "manager",
        "director",
        "hrbp",
    ]
    # Once the effective date is reached, the future revision participates.
    with container.db.sessions() as db:
        active = SqlSalary(db, container.crypto).get(
            row["id"], container.clock.now().date() + timedelta(days=10)
        )
        assert active["active"]["version"] == 2
    row = save(client, login, container, key="immediate", expected_version=2, upper=25).json()
    with container.db.sessions() as db:
        active = SqlSalary(db, container.crypto).get(
            row["id"], container.clock.now().date() + timedelta(days=10)
        )
        assert active["active"]["version"] == 3
    # A newly introduced dimension that is future-only is not usable yet.
    assert (
        save(
            client,
            login,
            container,
            key="future-city",
            city="北京",
            expected_version=0,
            effective_from=future,
        ).status_code
        == 200
    )
    assert submit(client, login, {**fields, "city": "北京"}, "future-only").status_code == 422


def test_submitted_chain_and_salary_refs_survive_rule_changes(client, login, container, fields):
    req = submit(client, login, fields).json()
    refs = req["history"][-1]["salary_rules"]
    assert refs[0]["version"] == 1
    assert save(client, login, container, upper=10).status_code == 200
    assert submit(client, login, fields, "new-policy").json()["chain"][-1]["id"] == "salary"
    for _ in range(3):
        req = approve(client, login, req)
    assert req["status"] == "approved"
    assert req["history"][0]["salary_rules"] == refs


@pytest.mark.parametrize("broken", ["missing", "inactive", "wrong-role", "self", "manager-self"])
def test_missing_inactive_or_self_hrd_cannot_bypass_signoff(
    client, login, container, fields, broken
):
    with container.db.sessions.begin() as db:
        policy = db.get(DepartmentRecord, fields["dept"])
        if broken == "missing":
            policy.policy = {**policy.policy, "hrd_id": None}
        elif broken == "inactive":
            db.get(UserRecord, "salary_hrd").active = False
        elif broken == "wrong-role":
            policy.policy = {**policy.policy, "hrd_id": "hrbp"}
        elif broken == "manager-self":
            policy.policy = {**policy.policy, "hrd_id": "manager"}
            db.get(UserRecord, "manager").roles = ["hiring_manager", "hrd"]
        else:
            policy.policy = {**policy.policy, "hrd_id": "hr"}
            db.get(UserRecord, "hr").roles = ["recruiting_lead", "hrd"]
    response = submit(client, login, {**fields, "salary": "10-25K/月×13"})
    assert response.status_code == 422
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuditRecord)) == 0


def test_stale_warning_tracks_active_revision_and_new_revision_is_audited(
    client, login, container, fields
):
    with container.db.sessions.begin() as db:
        band = db.scalar(select(SalaryBandRecord).where(SalaryBandRecord.series == "客服"))
        db.get(SalaryRevisionRecord, (band.id, 1)).updated_on = (
            container.clock.now().date() - timedelta(days=31)
        )
    response = client.post(ROOT + "/precheck", json=fields, headers=login()).json()
    assert any(c["key"] == "salary_stale" and c["status"] == "warn" for c in response)
    future = (container.clock.now().date() + timedelta(days=1)).isoformat()
    assert save(client, login, container, effective_from=future).json()["stale"]


@pytest.mark.parametrize(
    "patch",
    [
        {"lower": 21},
        {"upper": 0},
        {"months": 0},
        {"months": 25},
        {"months": 12.5},
        {"grade": "P3-P5"},
        {"series": " "},
        {"city": " "},
    ],
)
def test_invalid_config_is_rejected(client, login, container, patch):
    assert save(client, login, container, **patch).status_code == 400


def test_backdating_rejected(client, login, container):
    assert (
        save(
            client,
            login,
            container,
            effective_from=(container.clock.now().date() - timedelta(days=1)).isoformat(),
        ).status_code
        == 422
    )


def test_concurrent_updates_keep_one_revision(client, login, container, monkeypatch):
    headers = [login("hr", f"competing-salary-{i}") for i in range(2)]
    if container.db.engine.dialect.name == "postgresql":
        gate = Barrier(2, timeout=10)
        original = SqlSalary.save

        def concurrent(self, *args):
            gate.wait()
            return original(self, *args)

        monkeypatch.setattr(SqlSalary, "save", concurrent)

    def update(index):
        return client.post(
            SALARY, json=command(container, upper=21 + index), headers=headers[index]
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(update, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    winner = next(r.json() for r in responses if r.status_code == 200)
    history = client.get(f"{SALARY}/{winner['id']}/history", headers=login()).json()
    assert len(history) == 2 and history[0]["version"] == 2


def test_read_cannot_mix_head_and_rules_from_different_versions(container, monkeypatch):
    from app.modules.org.contracts import SalaryBandCommand

    today = container.clock.now().date()
    with container.db.sessions() as db:
        band_id = db.scalar(select(SalaryBandRecord.id).where(SalaryBandRecord.series == "客服"))
        original = db.get
        published = False

        def publish_between_reads(model, *args, **kwargs):
            nonlocal published
            record = original(model, *args, **kwargs)
            if model is SalaryBandRecord and not published:
                published = True
                with container.db.sessions.begin() as writer:
                    SqlSalary(writer, container.crypto).save(
                        SalaryBandCommand(**command(container, upper=25)), today
                    )
            return record

        monkeypatch.setattr(db, "get", publish_between_reads)
        row = SqlSalary(db, container.crypto).get(band_id, today)
        assert row["version"] == row["latest"]["version"] == row["active"]["version"] == 1
        assert row["active"]["upper"] == 20
