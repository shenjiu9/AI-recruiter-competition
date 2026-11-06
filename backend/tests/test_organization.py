from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from test_requisition_api import ROOT, create
from test_salary import approve

from app.kernel.types import Ctx, DomainError, Principal
from app.modules.org.adapters.configuration import ConfigurationRevision, SqlConfiguration
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.modules.org.contracts import PermissionCommand
from app.platform.records import AuditRecord, EventRecord, RequestRecord, SqlJournal

ORG = "/api/v1/admin/organization"
DEPT = "客服中心"


def permission(
    client, login, target, roles, departments=None, version=1, actor="admin", key="grant"
):
    return client.post(
        f"{ORG}/users/{target}/permissions",
        headers=login(actor, key),
        json={"roles": roles, "departments": departments or [], "expected_version": version},
    )


def policy(client, login, version=1, key="policy", **values):
    return client.post(
        ORG + "/approval",
        params={"dept": DEPT},
        headers=login("admin", key),
        json={
            "expected_version": version,
            "director_id": "director",
            "hrbp_id": "hrbp",
            "hc_owner_id": "hrd",
            "hrd_id": "salary_hrd",
            **values,
        },
    )


def test_admin_reads_directory_without_business_or_salary(client, login, fields):
    req = create(client, login, fields)
    rows = client.get(ORG + "/departments", headers=login("admin")).json()
    assert len(rows) == 4
    assert all("salary_max" not in r["policy"] and "available_hc" not in r["policy"] for r in rows)
    assert client.get(ROOT, headers=login("admin")).json()["total"] == 0
    assert client.get(f"{ROOT}/{req['id']}", headers=login("admin")).status_code == 404
    assert client.post(ROOT, headers=login("admin"), json=fields).status_code == 403
    assert client.get("/api/v1/admin/salary-bands", headers=login("admin")).status_code == 403
    users = client.get(
        ORG + "/users", params={"q": "薪酬", "size": 1}, headers=login("admin")
    ).json()
    assert users["total"] == 2 and len(users["items"]) == 1


@pytest.mark.parametrize("actor", ["manager", "hrbp", "salary_hrd", "payroll", "outsider"])
def test_non_administrators_cannot_manage_organization(client, login, actor):
    assert client.get(ORG + "/users", headers=login(actor)).status_code == 403
    assert client.get(ORG + "/departments", headers=login(actor)).status_code == 403
    assert permission(client, login, actor, ["admin"], actor=actor).status_code == 403


def test_leader_read_only_scope_and_history_isolation(client, login):
    assert permission(client, login, "outsider", ["recruiting_lead"], [DEPT]).status_code == 200
    depts = client.get(ORG + "/departments", headers=login("outsider")).json()
    assert [d["id"] for d in depts] == [DEPT]
    users = client.get(ORG + "/users", headers=login("outsider")).json()["items"]
    assert users and all(
        set(u["departments"] + u["directory_departments"]) <= {DEPT} for u in users
    )
    assert not any(u["id"] == "sales" for u in users)
    assert permission(client, login, "hr", ["admin"], actor="hr").status_code == 403
    assert (
        client.get(
            ORG + "/history", params={"kind": "permissions", "object_id": "hr"}, headers=login("hr")
        ).status_code
        == 403
    )
    assert (
        client.get(
            ORG + "/history",
            params={"kind": "approval", "object_id": "财务部"},
            headers=login("outsider"),
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"roles": ["hiring_manager"]},
        {"roles": ["candidate"]},
        {"roles": ["super_admin"]},
        {"active": False},
        {"name": "伪造姓名"},
        {"directory_roles": ["admin"]},
    ],
)
def test_directory_fields_and_derived_roles_cannot_be_edited(client, login, body):
    response = client.post(
        f"{ORG}/users/hr/permissions",
        headers=login("admin"),
        json={"expected_version": 1, "roles": [], "departments": [], **body},
    )
    assert response.status_code == 400


def test_permissions_history_idempotency_conflict_and_derived_scope_preserved(
    client, login, container
):
    result = permission(client, login, "manager", ["hrbp"], [])
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    assert permission(client, login, "manager", ["hrbp"], []).json() == result.json()
    assert permission(client, login, "manager", [], [], key="stale").status_code == 409
    with container.scope() as services:
        user = services.org.get_user("manager")
        assert set(user.roles) == {"hiring_manager", "hrbp"}
        assert user.departments == (DEPT,)
    history = client.get(
        ORG + "/history",
        params={"kind": "permissions", "object_id": "manager"},
        headers=login("admin"),
    ).json()
    assert [r["version"] for r in history["items"]] == [2, 1]
    assert history["items"][1]["actor_id"] is None
    with container.db.sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "org.permissions_updated")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(EventRecord)) == 0


def test_invalid_scope_inactive_and_unknown_users_rejected(client, login, container):
    assert permission(client, login, "hr", [], ["客服中心假的下级"]).status_code == 422
    assert permission(client, login, "missing", [], []).status_code == 404
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "payroll").active = False
    assert permission(client, login, "payroll", ["admin"]).status_code == 422


def test_scope_descendants_use_relationship_not_text_prefix_and_token_refresh(
    client, login, fields, container
):
    with container.db.sessions.begin() as db:
        baseline = db.get(DepartmentRecord, DEPT).policy
        db.add(DepartmentRecord(id="客服一组", parent_id=DEPT, policy=baseline))
        db.add(DepartmentRecord(id="客服中心外部部门", policy=baseline))
    token = login("outsider")
    assert permission(client, login, "outsider", ["recruiting_lead"], [DEPT]).status_code == 200
    visible = client.get(ORG + "/departments", headers=token).json()
    assert {r["id"] for r in visible} == {DEPT, "客服一组"}
    with container.scope() as services:
        assert "客服一组" in services.auth.current_principal(token["Authorization"][7:]).departments
    assert permission(client, login, "outsider", [], [], version=2, key="revoke").status_code == 200
    assert client.get(ORG + "/departments", headers=token).status_code == 403


def test_permission_change_blocks_cached_business_response_without_duplicate(
    client, login, fields, container
):
    headers = login("hr", "cached-business")
    req = client.post(ROOT, headers=headers, json=fields).json()
    assert permission(client, login, "hr", [], []).status_code == 200
    assert client.get(f"{ROOT}/{req['id']}", headers=headers).status_code == 404
    response = client.post(ROOT, headers=headers, json=fields)
    assert response.status_code == 409 and "fields" not in response.json()
    with container.db.sessions() as db:
        from app.modules.requisition.adapters.orm import RequisitionRecord

        assert db.scalar(select(func.count()).select_from(RequisitionRecord)) == 1


def test_ordinary_recruiter_only_sees_explicitly_related_requests(client, login, fields):
    req = create(client, login, fields)
    assert permission(client, login, "outsider", ["recruiter"], [DEPT]).status_code == 200
    assert client.get(ROOT, headers=login("outsider")).json()["total"] == 0
    assert client.get(f"{ROOT}/{req['id']}", headers=login("outsider")).status_code == 404
    confidential = create(
        client, login, {**fields, "confidential": "1", "visibleTo": "outsider"}, key="shared"
    )
    assert client.get(f"{ROOT}/{confidential['id']}", headers=login("outsider")).status_code == 200


def test_policy_update_trial_history_and_inflight_snapshot(client, login, fields):
    old = create(client, login, fields)
    response = policy(client, login, hrbp_id="hrd", hc_owner_id="hrbp")
    assert response.status_code == 200, response.text
    assert policy(client, login, hrbp_id="hrd", hc_owner_id="hrbp").json() == response.json()
    assert policy(client, login, key="stale").status_code == 409
    fresh = create(client, login, fields, key="new-rule")
    assert fresh["chain"][2]["approver_id"] == "hrd"
    assert (
        client.get(f"{ROOT}/{old['id']}", headers=login()).json()["chain"][2]["approver_id"]
        == "hrbp"
    )
    trial = client.post(
        ORG + "/trial",
        params={"dept": DEPT},
        headers=login("admin"),
        json={"actor_id": "hr", "hc_request": True, "salary_over": True},
    ).json()
    assert trial["version"] == 2
    assert [(n["id"], n["approver_id"]) for n in trial["chain"]][-3:] == [
        ("hrbp", "hrd"),
        ("hc", "hrbp"),
        ("salary", "salary_hrd"),
    ]
    history = client.get(
        ORG + "/history", params={"kind": "approval", "object_id": DEPT}, headers=login("hr")
    ).json()
    assert [r["version"] for r in history["items"]] == [2, 1]
    # Restore an old snapshot by publishing a new version, never mutate history.
    assert policy(client, login, version=2, key="restore").json()["version"] == 3


@pytest.mark.parametrize(
    "values,status",
    [
        ({"hrbp_id": "manager"}, 422),
        ({"hrd_id": "missing"}, 404),
        ({"manager_id": "director"}, 400),
        ({"director_id": "manager"}, 422),
        ({"hrd_id": "payroll"}, 422),
    ],
)
def test_invalid_approval_configuration_rejected(client, login, values, status):
    assert policy(client, login, **values).status_code == status
    rows = client.get(ORG + "/departments", headers=login("admin")).json()
    assert next(d for d in rows if d["id"] == DEPT)["version"] == 1


def test_revoked_approver_scope_cannot_sign_existing_request(client, login, fields):
    req = create(client, login, fields)
    req = approve(client, login, approve(client, login, req))
    headers = login("hrbp", "sign-after-revoke")
    assert permission(client, login, "hrbp", ["hrbp"], []).status_code == 200
    response = client.post(
        f"{ROOT}/{req['id']}/approve",
        headers=headers,
        json={"expected_version": req["version"], "node_id": "hrbp"},
    )
    assert (
        response.status_code == 422 and response.json()["error"]["code"] == "ORG_APPROVER_INVALID"
    )


def synchronize_before_lock(container, monkeypatch):
    if container.db.engine.dialect.name == "postgresql":
        gate = Barrier(2, timeout=15)
        original = SqlConfiguration.lock

        def simultaneous(self):
            gate.wait()
            return original(self)

        monkeypatch.setattr(SqlConfiguration, "lock", simultaneous)


def test_concurrent_policy_edits_have_one_winner(client, login, container, monkeypatch):
    synchronize_before_lock(container, monkeypatch)
    headers = [login("admin", f"parallel-{n}") for n in range(2)]

    def save(n):
        return client.post(
            ORG + "/approval",
            params={"dept": DEPT},
            headers=headers[n],
            json={
                "expected_version": 1,
                "director_id": "director",
                "hrbp_id": ["hrbp", "hrd"][n],
                "hc_owner_id": "hrd",
                "hrd_id": "salary_hrd",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, [0, 1])) == [200, 409]
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ConfigurationRevision)) == 2


@pytest.mark.parametrize("self_removal", [False, True])
def test_two_admins_cannot_concurrently_remove_all_admins(
    client, login, container, monkeypatch, self_removal
):
    assert permission(client, login, "payroll", ["admin"]).status_code == 200
    synchronize_before_lock(container, monkeypatch)
    headers = [login("admin", "remove-other"), login("payroll", "remove-other")]

    def remove(n):
        target = (["admin", "payroll"] if self_removal else ["payroll", "admin"])[n]
        version = ([1, 2] if self_removal else [2, 1])[n]
        return client.post(
            f"{ORG}/users/{target}/permissions",
            headers=headers[n],
            json={"roles": [], "departments": [], "expected_version": version},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(remove, [0, 1]))
    assert results == ([200, 409] if self_removal else [200, 403])
    with container.db.sessions() as db:
        assert sum("admin" in u.roles for u in db.scalars(select(UserRecord))) == 1


def test_last_admin_guard_and_stale_context_revalidation(client, login, container):
    assert permission(client, login, "admin", []).json()["error"]["code"] == "ORG_LAST_ADMIN"
    assert permission(client, login, "payroll", ["admin"], key="second").status_code == 200
    ctx = Ctx(Principal("payroll", "old", ("admin",), ()), "stale-context")
    assert permission(client, login, "payroll", [], version=2, key="revoke").status_code == 200
    with pytest.raises(DomainError, match="仅系统管理员"):
        with container.scope() as services:
            services.org.configuration.save_permissions(
                ctx, "hr", PermissionCommand(expected_version=1, roles=["admin"], departments=[])
            )


def test_history_and_permission_roll_back_on_audit_failure(client, login, container, monkeypatch):
    original = SqlJournal.record

    def fail(self, ctx, action, *args, **kwargs):
        if action == "org.permissions_updated":
            raise DomainError("INJECTED", "audit failure", 503)
        return original(self, ctx, action, *args, **kwargs)

    monkeypatch.setattr(SqlJournal, "record", fail)
    assert permission(client, login, "payroll", ["admin"]).status_code == 503
    with container.db.sessions() as db:
        assert db.get(UserRecord, "payroll").version == 1
        assert db.scalar(select(func.count()).select_from(ConfigurationRevision)) == 0
        assert db.scalar(select(func.count()).select_from(RequestRecord)) == 0
    monkeypatch.setattr(SqlJournal, "record", original)
    assert permission(client, login, "payroll", ["admin"]).status_code == 200


def test_first_admin_bootstrap_requires_existing_active_user_and_is_one_time(container):
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "admin").roles = []
    with container.scope() as services:
        assert services.org.configuration.bootstrap_admin("admin", 1)["version"] == 2
    with pytest.raises(DomainError, match="已有在职管理员"):
        with container.scope() as services:
            services.org.configuration.bootstrap_admin("hr", 1)
