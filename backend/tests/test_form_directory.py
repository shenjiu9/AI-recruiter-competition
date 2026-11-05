import pytest
from test_confirmation import confirm
from test_requisition_api import ROOT, create
from test_transfers import transfer

from app.modules.org.adapters.repository import DepartmentRecord, UserRecord

FORM = "/api/v1/hr/requisition-form"
DEPT = "客服中心"


def users(client, login, actor="hr", **params):
    return client.get(FORM + "/users", headers=login(actor), params={"dept": DEPT, **params})


def test_scoped_tree_uses_live_source_and_hides_ancestors(client, login, container):
    with container.db.sessions.begin() as db:
        policy = dict(db.get(DepartmentRecord, DEPT).policy)
        db.add(DepartmentRecord(id="客服一组", parent_id=DEPT, policy=policy))
        db.add(DepartmentRecord(id="客服中心相似名称", policy=policy))
        db.get(DepartmentRecord, DEPT).parent_id = "隐藏上级"
    rows = client.get(FORM + "/departments", headers=login("manager")).json()
    assert sorted(rows, key=lambda r: r["id"]) == sorted(
        [{"id": DEPT, "parent_id": None}, {"id": "客服一组", "parent_id": DEPT}],
        key=lambda r: r["id"],
    )
    assert users(client, login, "manager", dept="财务部").status_code == 403


@pytest.mark.parametrize("actor", ["admin", "payroll", "salary_hrd"])
def test_directory_requires_form_role(client, login, actor):
    assert client.get(FORM + "/departments", headers=login(actor)).status_code == 403
    assert users(client, login, actor).status_code == 403


def test_people_paging_selected_resolution_and_no_identity_leak(client, login, container):
    with container.db.sessions.begin() as db:
        for n in range(25):
            db.add(UserRecord(id=f"person-{n:02}", name=f"员工{n}", roles=[], departments=[DEPT]))
        db.add(
            UserRecord(
                id="inactive", name="不能泄漏姓名", active=False, roles=[], departments=[DEPT]
            )
        )
    result = users(
        client,
        login,
        q="person-",
        page=2,
        size=20,
        selected=["person-00", "inactive", "outsider", "missing"],
    ).json()
    assert result["total"] == 25 and len(result["items"]) == 5
    assert result["selected"][0] == {"id": "person-00", "name": "员工0", "available": True}
    assert all(row["name"] is None and not row["available"] for row in result["selected"][1:])
    assert "不能泄漏" not in str(result)
    assert users(client, login, q="员工24").json()["total"] == 1


@pytest.mark.parametrize(
    "params",
    [{"size": 101}, {"page": 0}, {"q": "a" * 101}, {"selected": [str(n) for n in range(51)]}],
)
def test_directory_query_bounds(client, login, params):
    assert users(client, login, **params).status_code == 400


def test_reporting_identity_is_independent_of_approval_policy(client, login, fields):
    req = create(client, login, {**fields, "reportToId": "hrbp", "reportTo": "伪造姓名"})
    assert req["fields"]["reportTo"] == "人力伙伴"
    assert req["fields"]["reportToId"] == "hrbp"
    assert req["managerId"] == "manager" and req["chain"][0]["approver_id"] == "manager"


def test_legacy_duplicate_name_requires_explicit_selection(client, login, fields, container):
    with container.db.sessions.begin() as db:
        db.add(UserRecord(id="same-name", name="何美玲", roles=[], departments=[DEPT]))
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    assert draft["fields"]["reportTo"] == "何美玲" and not draft["fields"].get("reportToId")
    path = f"{ROOT}/{draft['id']}/submit"
    rejected = client.post(path, headers=login(key="ambiguous"), json={"expected_version": 1})
    assert rejected.status_code == 422
    selected = client.post(
        path,
        headers=login(key="selected"),
        json={"expected_version": 1, "fields": {"reportToId": "same-name"}},
    )
    assert selected.status_code == 200
    assert selected.json()["fields"]["reportToId"] == "same-name"


@pytest.mark.parametrize("change", ["inactive", "scope"])
def test_stale_selection_is_preserved_in_draft_but_rejected_on_submit(
    client, login, fields, container, change
):
    draft = client.post(
        ROOT + "/drafts",
        headers=login(),
        json={**fields, "reportToId": "hrbp", "visibleTo": "hrbp"},
    ).json()
    with container.db.sessions.begin() as db:
        person = db.get(UserRecord, "hrbp")
        if change == "inactive":
            person.active = False
        else:
            person.departments = []
    response = client.post(
        f"{ROOT}/{draft['id']}/submit", headers=login(key="stale"), json={"expected_version": 1}
    )
    assert response.status_code == 422
    checks = response.json()["error"]["details"]["checks"]
    assert {c["key"] for c in checks} >= {"manager", "visible_users"}
    saved = client.get(f"{ROOT}/{draft['id']}", headers=login()).json()
    assert saved == draft
    assert users(client, login, selected=["hrbp"]).json()["selected"][0]["name"] is None


@pytest.mark.parametrize("field", ["reportToId", "visibleTo"])
def test_forged_out_of_scope_person_is_rejected(client, login, fields, field):
    response = client.post(ROOT, headers=login(), json={**fields, field: "outsider"})
    assert response.status_code == 422
    assert client.get(ROOT, headers=login()).json()["total"] == 0


def test_name_only_edit_does_not_reuse_old_id(client, login, fields):
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    changed = client.patch(
        f"{ROOT}/{draft['id']}",
        headers=login(key="edit"),
        json={"expected_version": 1, "fields": {"reportTo": "人力伙伴"}},
    )
    assert changed.json()["fields"]["reportToId"] == "hrbp"


def test_confirmation_directory_delegation_and_person_diff(client, login, fields):
    req = create(client, login, fields)
    assert users(client, login, "hr", requisition_id=req["id"]).status_code == 403
    delegated = transfer(client, login, req).json()
    assert users(client, login, "manager", requisition_id=req["id"]).status_code == 403
    assert users(client, login, "director", requisition_id=req["id"]).status_code == 200
    assert (
        users(client, login, "director", dept="财务部", requisition_id=req["id"]).status_code == 403
    )
    result = confirm(client, login, delegated, {"reportToId": "hrbp"}, user="director")
    assert result.status_code == 200, result.text
    changes = result.json()["history"][-1]["changes"]
    assert changes["reportToId"] == {"before": "manager", "after": "hrbp"}
    assert changes["reportTo"]["after"] == "人力伙伴"


def test_confirmation_revalidates_new_person_but_keeps_unchanged_history(
    client, login, fields, container
):
    req = create(client, login, {**fields, "reportToId": "hrbp"})
    preview = confirm(
        client, login, req, {"reportToId": "director"}, endpoint="confirmation-preview"
    )
    assert not [c for c in preview.json()["checks"] if c["status"] == "block"]
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "director").departments = []
        db.get(UserRecord, "director").directory_departments = []
        db.get(UserRecord, "hrbp").active = False
    rejected = confirm(client, login, req, {"reportToId": "director"})
    assert rejected.status_code == 422
    assert client.get(f"{ROOT}/{req['id']}", headers=login()).json() == req
    preserved = confirm(client, login, req, {"duties": "补充职责"}, key="keep-history")
    assert preserved.status_code == 200, preserved.text
    assert preserved.json()["fields"]["reportToId"] == "hrbp"


def test_draft_directory_owner_and_department_switch_revalidate(client, login, fields):
    draft = client.post(ROOT + "/drafts", headers=login(), json=fields).json()
    assert users(client, login, "director", requisition_id=draft["id"]).status_code == 403
    changed = client.patch(
        f"{ROOT}/{draft['id']}",
        headers=login(key="department-change"),
        json={"expected_version": 1, "fields": {"dept": "财务部"}},
    )
    assert changed.status_code == 200
    assert changed.json()["fields"]["reportToId"] == "manager"
    submitted = client.post(
        f"{ROOT}/{draft['id']}/submit",
        headers=login(key="invalid-person"),
        json={"expected_version": 2},
    )
    assert submitted.status_code == 422
    assert any(c["key"] == "manager" for c in submitted.json()["error"]["details"]["checks"])
