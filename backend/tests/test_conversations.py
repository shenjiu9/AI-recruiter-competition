import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_candidates import app_action, attach, command, create, ok
from test_positions import opened

from app.bootstrap import build_container
from app.conversation_worker import run_once
from app.modules.conversation.repository import ConversationRecord

ROOT = "/api/v1/hr/candidates"


def hr_get(client, login, cid):
    return ok(client.get(f"{ROOT}/{cid}/conversation", headers=login()))


def hr_act(client, login, cid, action, **body):
    version = hr_get(client, login, cid)["version"]
    return client.post(
        f"{ROOT}/{cid}/conversation",
        headers=login(key=uuid4().hex),
        json={"expected_version": version, "action": action, **body},
    )


def link(client, login, cid):
    result = ok(hr_act(client, login, cid, "issue_link"))
    return {"Authorization": "Bearer " + result["url"].split("#t=")[1]}


def portal_get(client, headers):
    return ok(client.get("/api/v1/candidate/session", headers=headers))


def portal_act(client, headers, action, **body):
    version = portal_get(client, headers)["version"]
    return client.post(
        "/api/v1/candidate/actions",
        headers={**headers, "Idempotency-Key": uuid4().hex},
        json={"expected_version": version, "action": action, **body},
    )


def freeze(container, hour):
    # Keep JWT login iat valid while controlling Shanghai local hours.
    value = datetime.now(UTC).replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
        days=2
    )
    container.clock = SimpleNamespace(now=lambda: value)
    return value


def test_link_rotation_expiry_audience_and_missing_token(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    assert portal_get(client, headers)["profile"]["name"] == "测试候选人"
    assert client.get("/api/v1/candidate/session").status_code == 401
    assert client.get("/api/v1/candidate/session", headers=login()).status_code == 401
    assert client.get(f"{ROOT}/{c['id']}", headers=headers).status_code == 401
    newer = link(client, login, c["id"])
    assert client.get("/api/v1/candidate/session", headers=headers).status_code == 401
    future = container.clock.now() + timedelta(hours=73)
    container.clock = SimpleNamespace(now=lambda: future)
    assert client.get("/api/v1/candidate/session", headers=newer).status_code == 401


def test_send_before_consent_and_exactly_once(client, login):
    c = create(client, login)
    headers = link(client, login, c["id"])
    version = portal_get(client, headers)["version"]
    headers["Idempotency-Key"] = uuid4().hex
    body = {"action": "send", "expected_version": version, "content": "未授权也可以咨询"}
    for _ in range(2):
        data = ok(client.post("/api/v1/candidate/actions", headers=headers, json=body))
        assert len(data["messages"]) == 1
        assert data["consent"] == "none"
    body["content"] = "不能复用键改内容"
    assert client.post("/api/v1/candidate/actions", headers=headers, json=body).status_code == 409
    assert hr_get(client, login, c["id"])["messages"][0]["content"] == "未授权也可以咨询"


def test_takeover_reply_and_handback(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    now = container.clock.now()
    # A midday clock is injected after issuing auth headers so login JWTs remain valid.
    auth = login(key=uuid4().hex)
    container.clock = SimpleNamespace(now=lambda: now.replace(hour=4))
    with container.scope() as s:
        ctx = SimpleNamespace(
            principal=s.auth.current_principal(auth["Authorization"][7:]), trace_id="test"
        )
        from app.modules.conversation.contracts import Command

        with pytest.raises(Exception, match="先接管"):
            s.conversation.command(
                ctx, c["id"], Command(action="send", expected_version=1, content="你好")
            )
    # Restore clock for regular HTTP auth, assert the actual scheduling policy separately.
    container.clock = SimpleNamespace(now=lambda: now)
    ok(hr_act(client, login, c["id"], "take_over"))
    result = ok(hr_act(client, login, c["id"], "send", content="人工回复"))["conversation"]
    assert result["messages"][-1]["status"] in {"sent", "queued"}
    ok(hr_act(client, login, c["id"], "hand_back"))
    assert hr_act(client, login, c["id"], "send", content="未接管不能发").status_code == 409
    assert portal_get(client, headers)["mode"] == "waiting_human"


@pytest.mark.parametrize("action", ["revoke", "do_not_contact"])
def test_privacy_cancels_queue_and_blocks_hr(client, login, container, action):
    c = create(client, login)
    headers = link(client, login, c["id"])
    ok(hr_act(client, login, c["id"], "take_over"))
    ok(hr_act(client, login, c["id"], "send", content="晚间消息"))
    with container.scope() as s:
        record = s.conversation.store.get(c["id"])
        record["messages"][0]["status"] = "queued"
        s.conversation.store.save(record)
    data = ok(portal_act(client, headers, action))
    assert data["messages"] == []
    assert hr_get(client, login, c["id"])["messages"][0]["status"] == "cancelled"
    assert hr_act(client, login, c["id"], "send", content="不能再联系").status_code == 409
    assert ok(portal_act(client, headers, "send", content="我仍可提出资料请求"))["messages"]


def test_hr_privacy_also_cancels_queue(client, login, container):
    c = create(client, login)
    link(client, login, c["id"])
    ok(hr_act(client, login, c["id"], "take_over"))
    ok(hr_act(client, login, c["id"], "send", content="待发送"))
    with container.scope() as s:
        record = s.conversation.store.get(c["id"])
        record["messages"][0]["status"] = "queued"
        s.conversation.store.save(record)
    ok(command(client, login, c, "do_not_contact", reason="本人要求"))
    assert hr_get(client, login, c["id"])["messages"][0]["status"] == "cancelled"


def test_quiet_window_boundaries():
    from app.modules.conversation.public import SHANGHAI, ConversationFacade

    for hour, recent, expected_day, expected_hour in [
        (6, True, 1, 9),
        (7, True, 1, 7),
        (8, False, 1, 9),
        (9, False, 1, 9),
        (21, False, 2, 9),
        (22, True, 1, 22),
        (23, True, 2, 9),
    ]:
        now = datetime(2026, 10, 1, hour, tzinfo=SHANGHAI)
        due = ConversationFacade.delivery_time(now, recent).astimezone(SHANGHAI)
        assert (due.day, due.hour) == (expected_day, expected_hour)


def test_durable_debounce_restarts_and_quick_human(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    ok(portal_act(client, headers, "send", content="第一条"))
    ok(portal_act(client, headers, "send", content="第二条"))
    with container.scope() as s:
        record = s.conversation.store.get(c["id"])
        due = datetime.fromisoformat(record["debounce_at"])
    restarted = build_container(
        container.settings, SimpleNamespace(now=lambda: due + timedelta(seconds=1))
    )
    run_once(restarted)
    run_once(restarted)
    with restarted.scope() as s:
        record = s.conversation.store.get(c["id"])
        assert record["debounce_at"] is None
        assert len(record["messages"]) == 2  # No simulated AI answer.
        assert record["version"] == 4
    restarted.db.engine.dispose()
    ok(portal_act(client, headers, "send", content="请转人工"))
    with container.scope() as s:
        assert s.conversation.store.get(c["id"])["debounce_at"] is None


def test_stale_delayed_reply_cancelled(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    inbound = ok(portal_act(client, headers, "send", content="问题一"))["messages"][0]
    ok(hr_act(client, login, c["id"], "take_over"))
    ok(hr_act(client, login, c["id"], "send", content="旧问题的回复", reply_to_id=inbound["id"]))
    with container.scope() as s:
        record = s.conversation.store.get(c["id"])
        record["messages"][-1]["status"] = "queued"
        s.conversation.store.save(record)
    ok(portal_act(client, headers, "send", content="情况已经变了"))
    assert hr_get(client, login, c["id"])["messages"][1]["status"] == "cancelled"
    assert (
        hr_act(
            client, login, c["id"], "send", content="旧回复", reply_to_id=inbound["id"]
        ).status_code
        == 409
    )


def test_rights_requests_and_erasure_do_not_resurrect_messages(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    ok(portal_act(client, headers, "correction_request", content="我的学校需要更正"))
    data = ok(portal_act(client, headers, "deletion_request", content="请删除我的个人资料"))
    assert len(data["requests"]) == 2
    c = ok(client.get(f"{ROOT}/{c['id']}", headers=login()))
    ok(command(client, login, c, "erase", reason="已核实本人删除请求"))
    assert client.get("/api/v1/candidate/session", headers=headers).status_code == 401
    with container.scope() as s:
        assert s.session.scalars(select(ConversationRecord)).all() == []


def test_sse_contains_only_ids_and_versions(client, login):
    c = create(client, login, name="绝不出现在推送中的姓名")
    headers = link(client, login, c["id"])
    for path, auth in [
        (f"/api/v1/hr/stream?candidate_id={c['id']}&once=true", login()),
        ("/api/v1/candidate/stream?once=true", headers),
    ]:
        response = client.get(path, headers=auth)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        data = json.loads(response.text.removeprefix("data: ").strip())
        assert set(data) == {"id", "version", "candidate_version"}
    assert client.get("/api/v1/candidate/stream?once=true", headers=login()).status_code == 401


def test_role_and_capability_actions_are_separated(client, login):
    c = create(client, login)
    headers = link(client, login, c["id"])
    for actor in ["manager", "admin", "outsider"]:
        # An unassigned candidate is accessible to any formal HR, but business/admin are denied.
        if actor != "outsider":
            assert (
                client.get(f"{ROOT}/{c['id']}/conversation", headers=login(actor)).status_code
                == 403
            )
    assert portal_act(client, headers, "take_over").status_code == 403
    assert hr_act(client, login, c["id"], "consent").status_code == 403


def test_concurrent_candidate_commands_compare_versions(client, login):
    c = create(client, login)
    headers = link(client, login, c["id"])
    body = {"action": "send", "expected_version": 1, "content": "并发消息"}

    def send(_):
        return client.post(
            "/api/v1/candidate/actions",
            headers={**headers, "Idempotency-Key": uuid4().hex},
            json=body,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, range(2))) == [200, 409]
    assert len(portal_get(client, headers)["messages"]) == 1


def test_notice_is_public_only_after_delivery_and_undo_cancels(client, login, container, fields):
    _, p = opened(client, login, fields, container)
    c = create(client, login)
    a = ok(attach(client, login, c, p))
    headers = link(client, login, c["id"])
    a = ok(
        app_action(
            client,
            login,
            a,
            "reject",
            reason="内部不应公开的判断",
            reason_code="skills",
            notify=True,
        )
    )
    assert a["notice_status"] == "queued"
    assert portal_get(client, headers)["applications"][0]["status"] == "沟通中"
    a = ok(app_action(client, login, a, "undo_reject", reason="补充了解"))
    assert hr_get(client, login, c["id"])["messages"][0]["status"] == "cancelled"
    a = ok(
        app_action(
            client,
            login,
            a,
            "reject",
            reason="内部不应公开的判断",
            reason_code="skills",
            notify=True,
        )
    )
    due = datetime.fromisoformat(a["notice_at"])
    restarted = build_container(container.settings, SimpleNamespace(now=lambda: due))
    run_once(restarted)
    data = portal_get(client, headers)
    assert data["applications"][0]["status"] == "已结束"
    assert len(data["messages"]) == 1
    assert "内部不应公开" not in json.dumps(data, ensure_ascii=False)
    a = ok(client.get(f"{ROOT}/{c['id']}", headers=login()))["applications"][0]
    assert app_action(client, login, a, "undo_reject", reason="不能撤销").status_code == 409
    restarted.db.engine.dispose()


def test_message_storage_encrypted_and_merge_revokes_links(client, login, container):
    c, other = create(client, login), create(client, login)
    headers, second = link(client, login, c["id"]), link(client, login, other["id"])
    ok(portal_act(client, headers, "send", content="不得以明文保存的聊天"))
    c = ok(client.get(f"{ROOT}/{c['id']}", headers=login()))
    ok(
        command(
            client,
            login,
            c,
            "merge",
            target_id=other["id"],
            target_version=other["version"],
            reason="同一人",
        )
    )
    for auth in (headers, second):
        assert client.get("/api/v1/candidate/session", headers=auth).status_code == 401
    with container.scope() as s:
        raw = s.session.scalars(select(ConversationRecord)).first().data
        assert "不得以明文保存的聊天".encode() not in raw


def test_scoped_messages_and_cached_link_recheck_permissions(client, login, container, fields):
    _, p = opened(client, login, fields, container)
    c = create(client, login)
    a = ok(attach(client, login, c, p))
    auth = login(key=uuid4().hex)
    body = {"action": "issue_link", "expected_version": 0}
    result = ok(client.post(f"{ROOT}/{c['id']}/conversation", headers=auth, json=body))
    portal_headers = {"Authorization": "Bearer " + result["url"].split("#t=")[1]}
    ok(
        portal_act(
            client, portal_headers, "send", content="可见岗位消息", application_ids=[a["id"]]
        )
    )
    with container.scope() as s:
        hidden = s.application.store.get(a["id"])
        hidden.update(id="APP-hidden", position_id="POS-inaccessible", position_name="隐藏岗位")
        s.application.store.save(hidden)
    ok(
        portal_act(
            client,
            portal_headers,
            "send",
            content="跨岗位薪资私密内容",
            application_ids=["APP-hidden"],
        )
    )
    ok(portal_act(client, portal_headers, "send", content="没有岗位标签的私密内容"))
    data = hr_get(client, login, c["id"])
    assert [m["content"] for m in data["messages"]] == ["可见岗位消息"]
    assert client.post(f"{ROOT}/{c['id']}/conversation", headers=auth, json=body).status_code == 403
    assert client.get(f"{ROOT}/{c['id']}/conversation", headers=login("manager")).status_code == 403
    assert (
        client.get(f"{ROOT}/{c['id']}/conversation", headers=login("outsider")).status_code == 404
    )


def test_worker_rechecks_hr_access_and_does_not_send_after_revocation(client, login, container):
    from app.modules.org.adapters.repository import UserRecord

    c = create(client, login)
    link(client, login, c["id"])
    ok(hr_act(client, login, c["id"], "take_over"))
    ok(hr_act(client, login, c["id"], "send", content="权限撤回后的待发消息"))
    with container.scope() as s:
        record = s.conversation.store.get(c["id"])
        record["messages"][-1].update(
            status="queued", due_at=(container.clock.now() - timedelta(hours=1)).isoformat()
        )
        s.conversation.store.save(record)
        s.session.get(UserRecord, "hr").roles = []
    run_once(container)
    with container.scope() as s:
        assert s.conversation.store.get(c["id"])["messages"][-1]["status"] == "cancelled"


def test_real_queued_h5_delivery_after_restart_once(client, login, container):
    from app.kernel.types import Ctx
    from app.modules.conversation.contracts import Command

    c = create(client, login)
    headers = link(client, login, c["id"])
    ok(hr_act(client, login, c["id"], "take_over"))
    token = login()["Authorization"][7:]
    # 00:00 Shanghai; delivery is queued by the actual command, not a fixture status change.
    midnight = container.clock.now().replace(hour=16, minute=0, second=0, microsecond=0)
    with container.scope() as s:
        ctx = Ctx(s.auth.current_principal(token), "test")
        s.conversation.clock = SimpleNamespace(now=lambda: midnight)
        result = s.conversation.command(
            ctx, c["id"], Command(action="send", expected_version=2, content="持久化队列恢复发送")
        )
        record = s.conversation.store.get(result["id"])
        assert record["messages"][-1]["status"] == "queued"
        due = datetime.fromisoformat(record["messages"][-1]["due_at"])
    assert portal_get(client, headers)["messages"] == []
    restarted = build_container(container.settings, SimpleNamespace(now=lambda: due))
    run_once(restarted)
    run_once(restarted)
    assert [m["content"] for m in portal_get(client, headers)["messages"]] == ["持久化队列恢复发送"]
    restarted.db.engine.dispose()


def test_correction_resolution_and_opt_out_fast_route(client, login, container):
    c = create(client, login)
    headers = link(client, login, c["id"])
    data = ok(portal_act(client, headers, "correction_request", content="请更正我的资料"))
    rid = data["requests"][0]["id"]
    assert hr_act(client, login, c["id"], "resolve_request", request_id=rid).status_code == 422
    ok(hr_act(client, login, c["id"], "resolve_request", request_id=rid, content="已根据证明更正"))
    assert portal_get(client, headers)["requests"][0]["status"] == "resolved"
    data = ok(portal_act(client, headers, "send", content="请不再联系我"))
    assert data["do_not_contact"]
    with container.scope() as s:
        assert s.conversation.store.get(c["id"])["debounce_at"] is None


def test_revoke_cancels_notice_application_status(client, login, container, fields):
    _, p = opened(client, login, fields, container)
    c = create(client, login)
    a = ok(attach(client, login, c, p))
    headers = link(client, login, c["id"])
    ok(app_action(client, login, a, "reject", reason="技能", reason_code="skills", notify=True))
    ok(portal_act(client, headers, "revoke"))
    with container.scope() as s:
        assert s.application.store.get(a["id"])["notice_status"] == "cancelled"


def test_lead_can_recover_conversation_owned_by_departed_hr(client, login, container):
    from app.modules.org.adapters.repository import UserRecord

    c = create(client, login)
    response = client.post(
        f"{ROOT}/{c['id']}/conversation",
        headers=login("hrbp", uuid4().hex),
        json={"action": "take_over", "expected_version": 0},
    )
    assert response.status_code == 200
    with container.scope() as s:
        s.session.get(UserRecord, "hrbp").active = False
    assert hr_act(client, login, c["id"], "take_over").status_code == 409
    result = ok(hr_act(client, login, c["id"], "take_over", content="原接管人离职，由负责人接续"))
    assert result["conversation"]["owner_id"] == "hr"
    assert ok(hr_act(client, login, c["id"], "hand_back"))["conversation"]["owner_id"] is None
