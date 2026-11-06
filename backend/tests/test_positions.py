from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from test_requisition_api import ROOT, create

from app.modules.org.adapters.repository import UserRecord
from app.modules.position.adapters.repository import GenerationRecord, PositionRecord, SqlPositions
from app.platform.inbox import GROUP, InboxRecord
from app.platform.records import AuditRecord, EventRecord
from app.position_worker import consume, run_once

POS = "/api/v1/hr/positions"


def approved(client, login, fields, key="source", **extra):
    req = create(client, login, {**fields, "employmentType": "外包", **extra}, key=key)
    for actor in ("manager", "director", "hrbp"):
        response = client.post(
            f"{ROOT}/{req['id']}/approve",
            headers=login(actor, key + actor),
            json={
                "expected_version": req["version"],
                "node_id": req["chain"][req["currentNode"]]["id"],
            },
        )
        assert response.status_code == 200, response.text
        req = response.json()
    return req


def generated(client, login, fields, container, **extra):
    req = approved(client, login, fields, **extra)
    assert run_once(container)["failed"] == 0
    projection = client.get(f"{ROOT}/{req['id']}/position", headers=login()).json()
    assert projection["status"] == "generated", projection
    pos = client.get(f"{POS}/{projection['position']['id']}", headers=login()).json()
    return req, pos


def act(client, login, pos, action, actor="hr", key=None, **extra):
    return client.post(
        f"{POS}/{pos['id']}/actions",
        headers=login(actor, key or f"{action}-{pos['version']}"),
        json={"expected_version": pos["version"], "action": action, **extra},
    )


def opened(client, login, fields, container, **extra):
    req, pos = generated(client, login, fields, container, **extra)
    confirmed = act(client, login, pos, "confirm_profile", "manager")
    assert confirmed.status_code == 200, confirmed.text
    result = act(client, login, confirmed.json(), "publish")
    assert result.status_code == 200, result.text
    return req, result.json()


def test_worker_persists_one_position_and_per_consumer_receipt(client, login, fields, container):
    req, pos = generated(client, login, fields, container)
    assert pos["status"] == "to_publish" and pos["planned"] == 2 and pos["hired"] == 0
    assert pos["requisitionIds"] == [req["id"]] and pos["ownerId"] == "hr"
    assert not pos["profile"]["confirmedBy"] and "salary" not in pos
    with container.db.sessions() as db:
        evt = db.scalar(select(EventRecord).where(EventRecord.type == "requisition.approved"))
        event_id = evt.event_id
        assert evt.status == "pending"  # Another consumer still owns its own receipt.
        assert db.get(InboxRecord, (event_id, GROUP)).status == "done"
        assert b"requirements" not in db.get(PositionRecord, pos["id"]).data
        created = db.scalar(select(EventRecord).where(EventRecord.type == "position.created"))
        assert created.payload == {"position_id": pos["id"], "version": 1}
    assert consume(container, event_id) is False
    assert run_once(container) == {"completed": 0, "failed": 0}
    assert client.get(POS, headers=login()).json()["total"] == 1


def test_replayed_distinct_event_cannot_duplicate_source(client, login, fields, container):
    req, _ = generated(client, login, fields, container)
    with container.db.sessions.begin() as db:
        db.add(
            EventRecord(
                event_id="duplicate",
                type="requisition.approved",
                partition_key=req["id"],
                occurred_at=container.clock.now(),
                trace_id="retry",
                payload={"requisition_id": req["id"], "version": req["version"]},
            )
        )
    assert consume(container, "duplicate") is True
    assert client.get(POS, headers=login()).json()["total"] == 1


def test_worker_failure_rolls_back_position_generation_and_audit(
    client, login, fields, container, monkeypatch
):
    approved(client, login, fields)
    original = SqlPositions.save_generation

    def broken(self, task, previous=None):
        if previous:
            raise RuntimeError("sensitive failure body")
        original(self, task, previous)

    monkeypatch.setattr(SqlPositions, "save_generation", broken)
    assert run_once(container) == {"completed": 0, "failed": 1}
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(PositionRecord)) == 0
        assert db.scalar(select(func.count()).select_from(GenerationRecord)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(AuditRecord.action == "position.created")
            )
            == 0
        )
        receipt = db.scalar(select(InboxRecord))
        assert receipt.status == "retry" and receipt.error_code == "RuntimeError"
        event_id = receipt.event_id
    monkeypatch.setattr(SqlPositions, "save_generation", original)
    assert consume(container, event_id, force=True)
    assert client.get(POS, headers=login()).json()["total"] == 1


def test_invalid_event_dead_letter_does_not_poison_following_events(
    client, login, fields, container
):
    with container.db.sessions.begin() as db:
        db.add(
            EventRecord(
                event_id="bad",
                type="requisition.approved",
                partition_key="missing",
                occurred_at=container.clock.now(),
                trace_id="test",
                payload={"requisition_id": "missing", "version": 2},
            )
        )
    for _ in range(5):
        with container.db.sessions.begin() as db:
            row = db.get(InboxRecord, ("bad", GROUP))
            if row:
                row.next_attempt = container.clock.now()
        run_once(container)
    with container.db.sessions() as db:
        assert db.get(InboxRecord, ("bad", GROUP)).status == "dead"
    generated(client, login, fields, container)


def test_parallel_duplicate_delivery_is_serialized(client, login, fields, container):
    approved(client, login, fields)
    with container.db.sessions() as db:
        event_id = db.scalar(
            select(EventRecord.event_id).where(EventRecord.type == "requisition.approved")
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(container, event_id), range(2)))
    assert sorted(results) == [False, True]
    assert client.get(POS, headers=login()).json()["total"] == 1


@pytest.mark.parametrize("actor", ["admin", "payroll", "outsider"])
def test_position_visibility_requires_business_access(client, login, fields, container, actor):
    req, pos = generated(client, login, fields, container, confidential="1", visibleTo="hrbp")
    assert client.get(f"{POS}/{pos['id']}", headers=login(actor)).status_code == 404
    assert client.get(POS, headers=login(actor)).json()["total"] == 0
    assert client.get(f"{ROOT}/{req['id']}/position", headers=login(actor)).status_code == 404


def test_matching_sources_wait_for_explicit_merge_and_count_once(client, login, fields, container):
    _, pos = generated(client, login, fields, container)
    second = approved(client, login, fields, key="second")
    run_once(container)
    path = f"{ROOT}/{second['id']}/position"
    decision = client.get(path, headers=login()).json()
    assert decision["status"] == "decision" and len(decision["candidates"]) == 1
    body = {"expected_version": decision["version"], "target_id": pos["id"]}
    assert client.post(path, headers=login("manager", "denied"), json=body).status_code == 403
    result = client.post(path, headers=login(key="merge"), json=body)
    assert result.status_code == 200
    assert client.post(path, headers=login(key="merge"), json=body).json() == result.json()
    merged = client.get(f"{POS}/{pos['id']}", headers=login()).json()
    assert merged["planned"] == 4 and len(merged["requisitionIds"]) == 2
    assert client.get(POS, headers=login()).json()["total"] == 1


def test_confidential_source_is_never_merged_with_public_position(client, login, fields, container):
    generated(client, login, fields, container)
    generated(client, login, fields, container, key="private", confidential="1", visibleTo="hrbp")
    assert client.get(POS, headers=login()).json()["total"] == 2


def test_duplicate_can_explicitly_create_separate_position(client, login, fields, container):
    generated(client, login, fields, container)
    req = approved(client, login, fields, key="new")
    run_once(container)
    r = client.post(
        f"{ROOT}/{req['id']}/position", headers=login(key="separate"), json={"expected_version": 1}
    )
    assert r.status_code == 200
    assert client.get(POS, headers=login()).json()["total"] == 2


def test_profile_confirmation_required_and_edit_invalidates_it(client, login, fields, container):
    _, pos = generated(client, login, fields, container)
    assert act(client, login, pos, "publish").status_code == 422
    assert act(client, login, pos, "confirm_profile").status_code == 403
    pos = act(client, login, pos, "confirm_profile", "manager").json()
    pos = act(client, login, pos, "save_profile", must="服务经验", jd="处理客户咨询").json()
    assert pos["profile"]["version"] == 2 and pos["profile"]["confirmedBy"] is None
    assert act(client, login, pos, "publish").status_code == 422
    stale = act(client, login, {**pos, "version": 1}, "confirm_profile", "manager", key="stale")
    assert stale.status_code == 409


def test_pause_resume_close_release_headcount_atomically(client, login, fields, container):
    _, pos = opened(client, login, fields, container, employmentType="正式")
    assert act(client, login, pos, "pause").status_code == 422
    pos = act(
        client, login, pos, "pause", key="valid-pause", reason="调整计划", handling="freeze"
    ).json()
    assert pos["status"] == "paused" and pos["history"][-1]["handling"] == "freeze"
    pos = act(client, login, pos, "resume").json()
    response = act(client, login, pos, "close", reason="需求取消")
    assert response.status_code == 200, response.text
    assert act(client, login, pos, "close", reason="需求取消").json() == response.json()
    with container.scope() as services:
        assert services.org.headcount(fields["dept"])["reserved"] == 0
    assert act(client, login, response.json(), "resume").status_code == 409


def test_close_rollback_restores_headcount(client, login, fields, container, monkeypatch):
    _, pos = opened(client, login, fields, container, employmentType="正式")

    def broken(*args):
        raise RuntimeError("write failed")

    monkeypatch.setattr(SqlPositions, "save", broken)
    with pytest.raises(RuntimeError):
        act(client, login, pos, "close", reason="组织调整")
    with container.scope() as services:
        assert services.org.headcount(fields["dept"])["reserved"] == 2


@pytest.mark.parametrize("actor", ["manager", "director", "hrbp", "outsider", "admin"])
def test_unauthorized_lifecycle_actions(client, login, fields, container, actor):
    _, pos = opened(client, login, fields, container)
    assert act(client, login, pos, "pause", actor, reason="test").status_code in {403, 404}


def test_owner_reassignment_revokes_added_collaborator_access(client, login, fields, container):
    _, pos = generated(client, login, fields, container, confidential="1", visibleTo="hrbp")
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "outsider").departments = [fields["dept"]]
    pos = act(client, login, pos, "assign", owner_id="outsider").json()
    assert client.get(f"{POS}/{pos['id']}", headers=login("outsider")).status_code == 200
    pos = act(client, login, pos, "assign", owner_id="hr").json()
    assert client.get(f"{POS}/{pos['id']}", headers=login("outsider")).status_code == 404


def test_no_direct_creation_endpoint(client, login, fields):
    assert client.post(POS, headers=login(), json=fields).status_code == 405


def test_manager_created_position_requires_assignment_before_publish(
    client, login, fields, container
):
    req = create(client, login, {**fields, "employmentType": "外包"}, user="manager")
    for actor in ("director", "hrbp"):
        req = client.post(
            f"{ROOT}/{req['id']}/approve",
            headers=login(actor),
            json={
                "expected_version": req["version"],
                "node_id": req["chain"][req["currentNode"]]["id"],
            },
        ).json()
    run_once(container)
    pos = client.get(POS, headers=login()).json()["items"][0]
    assert pos["ownerId"] is None
    pos = act(client, login, pos, "confirm_profile", "manager").json()
    assert act(client, login, pos, "publish").status_code == 422
    assert act(client, login, pos, "assign", "manager", owner_id="outsider").status_code == 422
    pos = act(client, login, pos, "assign", "manager", key="assign-valid", owner_id="hr").json()
    assert act(client, login, pos, "publish").status_code == 200


def test_parallel_matching_sources_produce_one_position_and_one_decision(
    client, login, fields, container
):
    approved(client, login, fields, key="one")
    approved(client, login, fields, key="two")
    with container.db.sessions() as db:
        ids = list(
            db.scalars(
                select(EventRecord.event_id).where(EventRecord.type == "requisition.approved")
            )
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda uid: consume(container, uid), ids)) == [True, True]
    with container.db.sessions() as db:
        assert db.scalar(select(func.count()).select_from(PositionRecord)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(GenerationRecord)
                .where(GenerationRecord.position_id.is_(None))
            )
            == 1
        )


def test_parallel_close_releases_once_and_closed_position_is_read_only(
    client, login, fields, container
):
    _, pos = opened(client, login, fields, container, employmentType="正式")
    tokens = [login(key="close-a"), login(key="close-b")]

    def close(token):
        return client.post(
            f"{POS}/{pos['id']}/actions",
            headers=token,
            json={"expected_version": pos["version"], "action": "close", "reason": "需求取消"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(close, tokens))
    assert sorted(r.status_code for r in responses) == [200, 409]
    closed = next(r.json() for r in responses if r.status_code == 200)
    assert act(client, login, closed, "assign", owner_id="hrbp").status_code == 409
    with container.scope() as services:
        assert services.org.headcount(fields["dept"])["reserved"] == 0
    with container.db.sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.type == "position.closed")
            )
            == 1
        )


def test_position_filter_pagination_and_profile_validation(client, login, fields, container):
    _, pos = generated(client, login, fields, container)
    generated(client, login, fields, container, key="two", title="不同岗位")
    result = client.get(
        POS, headers=login(), params={"page": 2, "size": 1, "status": "to_publish"}
    ).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert client.get(POS, headers=login(), params={"status": "closed"}).json()["total"] == 0
    assert client.get(POS, headers=login(), params={"size": 101}).status_code == 400
    rejected = act(
        client, login, pos, "save_profile", must="沟通能力", plus="男性优先", jd="咨询服务"
    )
    assert rejected.json()["error"]["code"] == "POSITION_JD_INVALID"
    assert client.get(f"{POS}/{pos['id']}", headers=login()).json()["version"] == pos["version"]
