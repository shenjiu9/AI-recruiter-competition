from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_positions import POS, ROOT, act, approved, generated, opened

from app.kernel.types import Ctx, DomainError, Principal
from app.modules.org.adapters.repository import UserRecord
from app.modules.position.adapters.repository import SqlPositions
from app.modules.position.calendar import WorkCalendar
from app.platform.records import EventRecord
from app.position_worker import run_once


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def colleague(container):
    with container.db.sessions.begin() as db:
        db.add(
            UserRecord(
                id="colleague", name="招聘协作", roles=["recruiter"], departments=["客服中心"]
            )
        )
    return "colleague"


def ctx(container, actor="hr"):
    with container.scope() as s:
        u = s.org.get_user(actor)
        return Ctx(
            Principal(u.id, u.name, tuple(u.roles), tuple(u.departments), u.permission_version),
            "test",
        )


def test_active_profile_survives_edits_and_history_is_immutable(client, login, fields, container):
    _, pos = opened(client, login, fields, container)
    original = pos["activeProfile"]
    pos = ok(
        act(
            client,
            login,
            pos,
            "save_profile",
            must="三年客服经验",
            plus="英文\n系统操作",
            plus_weights=["high", "low"],
            must_ask="是否接受轮班",
            jd="处理复杂问题",
        )
    )
    assert pos["activeProfile"] == original and pos["profile"]["confirmedBy"] is None
    with container.scope() as s:
        assert s.position.current_profile(pos["id"])["version"] == original["version"]
    draft = pos
    pos = ok(act(client, login, pos, "confirm_profile", "manager"))
    assert pos["activeProfile"]["version"] == 2 and pos["profiles"][0] == original
    assert act(client, login, draft, "confirm_profile", "manager", key="stale").status_code == 409
    with container.scope() as s:
        items = s.position.current_profile(pos["id"])["items"]
    assert [i["weight"] for i in items if i["kind"] == "plus"] == ["high", "low"]
    assert len({i["id"] for i in items}) == len(items)


def test_invalid_weight_count_and_non_manager_confirmation(client, login, fields, container):
    _, pos = generated(client, login, fields, container)
    assert (
        act(
            client,
            login,
            pos,
            "save_profile",
            must="经验",
            plus="甲\n乙",
            plus_weights=["high"],
            jd="工作",
        ).status_code
        == 422
    )
    assert act(client, login, pos, "confirm_profile").status_code == 403


def test_jd_approval_pins_version_and_denies_self_approval(
    client, login, fields, container, colleague
):
    _, pos = generated(client, login, fields, container)
    pos = ok(act(client, login, pos, "share", shared_ids=[colleague]))
    pos = ok(act(client, login, pos, "configure_publish", jd_approval_required=True))
    assert act(client, login, pos, "approve_jd").status_code == 403
    pos = ok(act(client, login, pos, "save_jd", colleague, jd="新版 JD"))
    pos = ok(act(client, login, pos, "confirm_profile", "manager"))
    assert act(client, login, pos, "publish").json()["error"]["code"] == "JD_APPROVAL_REQUIRED"
    pos = ok(act(client, login, pos, "approve_jd"))
    pos = ok(act(client, login, pos, "publish"))
    active = pos["activeJd"]
    pos = ok(act(client, login, pos, "save_jd", colleague, jd="再次修订 JD"))
    assert pos["activeJd"] == active and pos["jd"]["approvedBy"] is None
    assert act(client, login, pos, "apply_jd").status_code == 422
    assert act(client, login, pos, "reject_jd").status_code == 422
    pos = ok(act(client, login, pos, "reject_jd", reason="职责不清楚"))
    assert pos["jd"]["status"] == "rejected"
    pos = ok(act(client, login, pos, "approve_jd"))
    pos = ok(act(client, login, pos, "apply_jd"))
    assert pos["activeJd"]["content"] == "再次修订 JD" and len(pos["jdVersions"]) == 3


def test_only_lead_changes_publish_policy(client, login, fields, container):
    _, pos = generated(client, login, fields, container)
    for actor in ("manager", "hrbp", "admin"):
        assert act(
            client, login, pos, "configure_publish", actor, jd_approval_required=True
        ).status_code in {403, 404}


def test_knowledge_disclosure_revision_retirement_and_no_salary_leak(
    client, login, fields, container
):
    _, pos = generated(client, login, fields, container)
    for level in ("proactive", "asked", "internal", "handoff"):
        pos = ok(
            act(
                client,
                login,
                pos,
                "save_kb",
                "manager",
                content=f"说明-{level}",
                source="人工核验制度",
                disclosure=level,
            )
        )
    path = f"{POS}/{pos['id']}/knowledge-preview"
    proactive = ok(client.get(path, headers=login()))
    assert [e["disclosure"] for e in proactive["entries"]] == ["proactive"]
    assert proactive["needsHuman"] is True
    asked = ok(client.get(path, headers=login(), params={"asked": True}))
    assert {e["disclosure"] for e in asked["entries"]} == {"proactive", "asked"}
    assert "internal" not in str(asked) and fields["salary"] not in str(asked)
    old_id = proactive["entries"][0]["id"]
    pos = ok(
        act(
            client,
            login,
            pos,
            "save_kb",
            entry_id=old_id,
            content="修订事实",
            source="新制度",
            disclosure="asked",
        )
    )
    assert not pos["knowledge"][0]["active"] and pos["knowledge"][-1]["id"] != old_id
    principal = ctx(container)
    with container.scope() as s, pytest.raises(DomainError, match="知识引用"):
        s.position.knowledge_for_reply(principal, pos["id"], asked=True, refs=[old_id])
    assert (
        act(
            client, login, pos, "save_kb", entry_id=old_id, content="旧版本覆盖", source="制度"
        ).status_code
        == 409
    )
    pos = ok(act(client, login, pos, "retire_kb", entry_id=pos["knowledge"][-1]["id"]))
    assert not pos["knowledge"][-1]["active"]
    with container.db.sessions() as db:
        event = db.scalar(select(EventRecord).where(EventRecord.type == "kb.changed"))
        assert event.payload["position_id"] == pos["id"] and "content" not in event.payload


def test_confidential_knowledge_never_enters_reply_projection(client, login, fields, container):
    req, pos = generated(client, login, fields, container, confidential="1", visibleTo="manager")
    pos = ok(
        act(
            client,
            login,
            pos,
            "save_kb",
            content="秘密岗位信息",
            source="经理",
            disclosure="proactive",
        )
    )
    result = ok(client.get(f"{POS}/{pos['id']}/knowledge-preview", headers=login()))
    assert result == {"entries": [], "needsHuman": True}
    assert (
        client.get(f"{POS}/{pos['id']}/knowledge-preview", headers=login("outsider")).status_code
        == 404
    )


def test_sharing_grants_revokes_editor_access_and_cannot_expand_itself(
    client, login, fields, container, colleague
):
    req, pos = generated(client, login, fields, container, confidential="1", visibleTo="manager")
    assert client.get(f"{POS}/{pos['id']}", headers=login(colleague)).status_code == 404
    pos = ok(act(client, login, pos, "share", shared_ids=[colleague]))
    assert client.get(f"{ROOT}/{req['id']}", headers=login(colleague)).status_code == 200
    assert (
        ok(client.get(POS, headers=login(colleague), params={"view": "participating"}))["total"]
        == 1
    )
    before_comment = pos
    pos = ok(
        act(client, login, pos, "comment", colleague, content="请核对职责", mentions=["manager"])
    )
    assert pos["comments"][-1]["authorName"] == "招聘协作"
    assert act(client, login, pos, "share", colleague, shared_ids=[]).status_code == 403
    assert act(client, login, pos, "assign", colleague, owner_id=colleague).status_code == 403
    assert (
        act(client, login, pos, "comment", content="提及越界", mentions=["outsider"]).status_code
        == 422
    )
    pos = ok(act(client, login, pos, "share", shared_ids=[]))
    assert client.get(f"{POS}/{pos['id']}", headers=login(colleague)).status_code == 404
    assert client.get(f"{ROOT}/{req['id']}", headers=login(colleague)).status_code == 404
    assert (
        act(
            client,
            login,
            before_comment,
            "comment",
            colleague,
            content="请核对职责",
            mentions=["manager"],
        ).status_code
        == 404
    )


def test_regular_hr_close_requires_manager_and_releases_only_on_confirmation(
    client, login, fields, container, colleague
):
    _, pos = opened(client, login, fields, container, employmentType="正式")
    pos = ok(act(client, login, pos, "assign", owner_id=colleague))
    assert act(client, login, pos, "close", colleague, reason="需求取消").status_code == 403
    pos = ok(act(client, login, pos, "request_close", colleague, reason="需求取消"))
    assert pos["status"] == "open"
    with container.scope() as s:
        assert s.org.headcount(fields["dept"])["reserved"] == 2
    assert act(client, login, pos, "confirm_close", colleague).status_code == 403
    pos = ok(act(client, login, pos, "reject_close", "manager", reason="还需要招聘"))
    assert pos["closeRequest"] is None and pos["status"] == "open"
    pos = ok(act(client, login, pos, "request_close", colleague, reason="组织调整"))
    result = ok(act(client, login, pos, "confirm_close", "manager"))
    assert result["status"] == "closed"
    with container.scope() as s:
        assert s.org.headcount(fields["dept"])["reserved"] == 0
    with container.db.sessions() as db:
        assert (
            len(list(db.scalars(select(EventRecord).where(EventRecord.type == "position.closed"))))
            == 1
        )


def test_close_confirmation_rollback_and_race(client, login, fields, container, monkeypatch):
    _, pos = opened(client, login, fields, container, employmentType="正式")
    pos = ok(act(client, login, pos, "request_close", reason="需求取消"))
    original = SqlPositions.save

    def broken(*args, **kwargs):
        raise RuntimeError("transaction failure")

    monkeypatch.setattr(SqlPositions, "save", broken)
    with pytest.raises(RuntimeError):
        act(client, login, pos, "confirm_close", "manager")
    monkeypatch.setattr(SqlPositions, "save", original)
    with container.scope() as s:
        assert s.org.headcount(fields["dept"])["reserved"] == 2
    tokens = [login("manager", "confirm-a"), login("manager", "reject-b")]

    def submit(i):
        return client.post(
            f"{POS}/{pos['id']}/actions",
            headers=tokens[i],
            json={
                "expected_version": pos["version"],
                "action": ["confirm_close", "reject_close"][i],
                "reason": "仍需招聘",
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(r.status_code for r in executor.map(submit, (0, 1))) == [200, 409]


def test_interview_plan_versions_validate_people_and_preserve_snapshot(
    client, login, fields, container
):
    _, pos = generated(client, login, fields, container)
    rounds = [
        {
            "name": "业务面",
            "format": "video",
            "duration": 30,
            "interviewers": ["manager"],
            "criteria": "问题解决",
            "rule": "designated",
            "decision_by": "manager",
        }
    ]
    pos = ok(act(client, login, pos, "save_interview_plan", rounds=rounds))
    original = pos["interviewPlans"][0]
    rounds[0]["duration"] = 60
    pos = ok(act(client, login, pos, "save_interview_plan", rounds=rounds))
    assert pos["interviewPlans"][0] == original and pos["interviewPlans"][-1]["version"] == 2
    rounds[0]["interviewers"] = ["outsider"]
    assert act(client, login, pos, "save_interview_plan", rounds=rounds).status_code == 422


def test_calendar_includes_holiday_and_makeup_workday():
    calendar = WorkCalendar([date(2026, 11, 9)], [date(2026, 11, 7)])
    # Friday -> make-up Saturday -> Tuesday -> Wednesday, preserving Shanghai wall time.
    assert calendar.deadline("2026-11-06T02:00:00+00:00") == datetime(2026, 11, 11, 2, tzinfo=UTC)


def test_timeout_generates_once_and_manual_choice_races_safely(client, login, fields, container):
    _, first = generated(client, login, fields, container)
    req = approved(client, login, fields, key="same")
    run_once(container)
    task = ok(client.get(f"{ROOT}/{req['id']}/position", headers=login()))
    assert task["status"] == "decision"
    due = datetime.fromisoformat(task["dueAt"])
    actual_clock = container.clock
    container.clock = SimpleNamespace(now=lambda: due - timedelta(seconds=1))
    assert run_once(container)["completed"] == 0
    container.clock = actual_clock
    with container.scope() as s:
        pending = s.position.store.generation(req["id"])
        pending["due_at"] = actual_clock.now().isoformat()
        s.position.store.save_generation(pending, pending["version"])
    # Existing auth token expires under the advanced clock, so issue it now.
    headers = login(key="merge-race")

    def resolve():
        return client.post(
            f"{ROOT}/{req['id']}/position",
            headers=headers,
            json={"expected_version": task["version"], "target_id": first["id"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker = executor.submit(run_once, container)
        manual = executor.submit(resolve)
        assert manual.result() in {200, 409}
        assert worker.result()["failed"] == 0
    assert run_once(container)["completed"] == 0
    positions = ok(client.get(POS, headers=login()))["items"]
    assert sum(p["planned"] for p in positions) == 4
    assert ok(client.get(f"{ROOT}/{req['id']}/position", headers=login()))["status"] == "generated"


def test_list_filters_respect_scope(client, login, fields, container, colleague):
    _, pos = generated(client, login, fields, container)
    ok(act(client, login, pos, "share", shared_ids=[colleague]))
    assert ok(client.get(POS, headers=login(colleague), params={"view": "mine"}))["total"] == 0
    assert (
        ok(
            client.get(
                POS,
                headers=login(colleague),
                params={"view": "participating", "query": "客服", "city": "深圳"},
            )
        )["total"]
        == 1
    )
    assert ok(client.get(POS, headers=login("outsider"), params={"query": "客服"}))["total"] == 0


def test_scope_revocation_removes_shared_position_and_source_access(
    client, login, fields, container, colleague
):
    req, pos = generated(client, login, fields, container, confidential="1", visibleTo="manager")
    ok(act(client, login, pos, "share", shared_ids=[colleague]))
    with container.db.sessions.begin() as db:
        db.get(UserRecord, colleague).departments = []
    assert client.get(f"{POS}/{pos['id']}", headers=login(colleague)).status_code == 404
    assert client.get(f"{ROOT}/{req['id']}", headers=login(colleague)).status_code == 404


def test_legacy_profiles_restore_confirmed_history_without_mutating_version(
    client, login, fields, container
):
    _, pos = generated(client, login, fields, container)
    pos = ok(act(client, login, pos, "confirm_profile", "manager"))
    pos = ok(act(client, login, pos, "save_profile", must="新版待确认", jd="工作职责"))
    with container.scope() as s:
        stored = s.position.store.get(pos["id"])
        stored.pop("profiles")
        stored.pop("active_profile")
        s.position.store.save(stored, stored["version"])
    restored = ok(client.get(f"{POS}/{pos['id']}", headers=login()))
    assert restored["activeProfile"]["version"] == 1
    assert restored["profile"]["version"] == 2 and restored["version"] == pos["version"]
    assert len(restored["profiles"]) == 2


def test_timeout_without_manual_action_creates_separate_position(client, login, fields, container):
    _, first = generated(client, login, fields, container)
    req = approved(client, login, fields, key="timeout")
    run_once(container)
    with container.scope() as s:
        task = s.position.store.generation(req["id"])
        task["due_at"] = (container.clock.now() - timedelta(seconds=1)).isoformat()
        s.position.store.save_generation(task, task["version"])
    assert run_once(container) == {"completed": 1, "failed": 0}
    projection = ok(client.get(f"{ROOT}/{req['id']}/position", headers=login()))
    assert projection["position"]["id"] != first["id"]
    assert run_once(container)["completed"] == 0


def test_manager_amend_and_confirm_is_atomic_and_role_scoped(client, login, fields, container):
    _, pos = opened(client, login, fields, container)
    assert (
        act(client, login, pos, "amend_confirm_profile", must="修改", jd="职责").status_code == 403
    )
    amended = ok(
        act(
            client,
            login,
            pos,
            "amend_confirm_profile",
            "manager",
            must="经理修改条件",
            jd="新职责",
            must_ask="能否轮班",
        )
    )
    assert amended["activeProfile"]["version"] == 2
    assert amended["activeProfile"]["confirmedBy"] == "manager"
    assert amended["profile"]["must"] == "经理修改条件"
    assert amended["profiles"][0]["must"] == fields["requirements"]
    assert (
        act(
            client,
            login,
            pos,
            "amend_confirm_profile",
            "manager",
            key="stale-amend",
            must="过期修改",
            jd="职责",
        ).status_code
        == 409
    )
