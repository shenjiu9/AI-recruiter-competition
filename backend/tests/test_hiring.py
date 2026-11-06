from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_candidates import app_action, attach, create, ok
from test_candidates import command as candidate_command
from test_interviews import feedback, finished, setup
from test_positions import act

ROOT = "/api/v1/hr/hiring"


def ready(client, login, fields, container, existing=None):
    if existing is None:
        f = setup(client, login, fields, container)
    else:
        c = create(client, login, name="第二位候选人")
        c = ok(
            candidate_command(
                client, login, c, "consent", granted=True, evidence="签名", reason="招聘"
            )
        )
        app = ok(attach(client, login, c, existing.pos))
        for _ in range(3):
            app = ok(app_action(client, login, app, "advance"))
        iv = ok(
            client.get(
                "/api/v1/hr/interviews",
                headers=existing.auth["hr"],
                params={"application_id": app["id"]},
            )
        )["items"][0]
        f = SimpleNamespace(**{**vars(existing), "c": c, "app": app, "iv": iv})
        from test_conversations import link

        f.portal = link(client, login, c["id"])
    f.auth.update({a: login(a) for a in ("hrbp", "salary_hrd")})
    clock = container.clock
    finished(f)
    ok(feedback(f))
    container.clock = clock
    f.hid = "HIRE-" + f.app["id"]
    return f


def get(f, actor="hr"):
    return ok(f.client.get(ROOT + "/" + f.hid, headers=f.auth[actor]))


def act_hire(f, action, actor="hr", **body):
    h = get(f, actor)
    payload = {
        "action": action,
        "expected_version": h["version"],
        "verified": True,
        "review_stamp": h["review_stamp"],
        **body,
    }
    return f.client.post(
        ROOT + "/" + f.hid + "/actions",
        headers={**f.auth[actor], "Idempotency-Key": uuid4().hex},
        json=payload,
    )


def prepare(f, salary=10):
    return ok(
        act_hire(
            f,
            "prepare",
            salary_k=salary,
            salary_months=13,
            evidence="本人确认期望薪资",
            offer_owner="hr",
            expected_start=(f.container.clock.now() + timedelta(days=30)).date().isoformat(),
        )
    )


def approved(f):
    prepare(f)
    h = ok(act_hire(f, "decide", "manager", decision="hire"))
    for node in h["chain"]:
        h = ok(act_hire(f, "approve", node["user_id"]))
    assert h["status"] == "approved"
    return h


def handed(f):
    approved(f)
    return ok(act_hire(f, "handover", evidence="HR 已当面接收移交单"))


def test_hiring_review_permissions_risks_approvals_and_capacity(client, login, fields, container):
    f = ready(client, login, fields, container)
    for actor in ("admin", "outsider"):
        assert client.get(ROOT + "/" + f.hid, headers=f.auth[actor]).status_code == 404
    assert act_hire(f, "decide", decision="hire").status_code == 403
    assert act_hire(f, "decide", "manager", decision="hire", review_stamp="old").status_code == 409
    assert (
        act_hire(f, "decide", "manager", decision="hire").json()["error"]["code"]
        == "FACTS_REQUIRED"
    )
    prepare(f, 30)
    assert "salary_k" not in get(f, "manager")["facts"]
    h = ok(act_hire(f, "decide", "manager", decision="hire"))
    assert [n["role"] for n in h["chain"]] == ["director", "hrbp", "salary"]
    assert act_hire(f, "approve", "salary_hrd").status_code == 403
    assert get(f, "salary_hrd")["facts"]["salary_k"] == 30
    for actor in ("director", "hrbp", "salary_hrd"):
        h = ok(act_hire(f, "approve", actor))
    assert h["status"] == "approved" and get(f)["handoff"]["delivery"] == "not_sent"
    pos = ok(client.get(f"/api/v1/hr/positions/{f.pos['id']}", headers=f.auth["hr"]))
    assert pos["hired"] == 1 and get(f)["handoff"]["candidate"]["name"]
    assert act_hire(f, "approve", "hrbp").status_code == 409


def test_approval_response_loss_replays_id_only_without_duplicate_hire(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    prepare(f)
    ok(act_hire(f, "decide", "manager", decision="hire"))
    ok(act_hire(f, "approve", "director"))
    h = get(f, "hrbp")
    auth = {**f.auth["hrbp"], "Idempotency-Key": uuid4().hex}
    body = {
        "action": "approve",
        "expected_version": h["version"],
        "verified": True,
        "review_stamp": h["review_stamp"],
    }
    for _ in range(2):
        assert (
            ok(client.post(ROOT + "/" + f.hid + "/actions", headers=auth, json=body))["status"]
            == "approved"
        )
    assert get(f)["remaining"] == 1


@pytest.mark.parametrize("result", ["declined", "no_show"])
def test_failed_result_releases_position_quota_and_has_no_cooldown(
    client, login, fields, container, result
):
    f = ready(client, login, fields, container)
    handed(f)
    h = ok(act_hire(f, "result", result=result, reason="候选人计划调整"))
    assert h["status"] == result and h["remaining"] == 2
    assert act_hire(f, "result", result=result, reason="重复").status_code == 409
    app = ok(attach(client, login, f.c, f.pos))
    assert app["stage"] == "reach"


def test_accepted_joined_keep_quota_and_hired_cannot_use_generic_rollback(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    handed(f)
    assert act_hire(f, "result", result="accepted").status_code == 422
    ok(
        act_hire(
            f,
            "result",
            result="accepted",
            expected_start=(container.clock.now() + timedelta(days=20)).date().isoformat(),
        )
    )
    h = ok(act_hire(f, "result", result="joined"))
    assert h["remaining"] == 1
    with container.scope() as s:
        app = s.application.interview_context(f.app["id"])
        assert app["outcome"] == "joined"
    assert (
        app_action(
            client, login, app, "rollback", target_stage="manager_eval", reason="绕过录用流程"
        ).status_code
        == 409
    )


def test_extra_round_and_rejection_require_reason(client, login, fields, container):
    f = ready(client, login, fields, container)
    assert act_hire(f, "decide", "manager", decision="reject").status_code == 422
    from test_interviews import DEFAULT_ROUND

    ok(
        act_hire(
            f,
            "decide",
            "manager",
            decision="extra_round",
            reason="补充实践证据",
            extra_round=DEFAULT_ROUND,
        )
    )
    assert get(f)["status"] == "cancelled"
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["stage"] == "interview"
        assert len([r for r in s.interview.store.all() if r["status"] == "waiting"]) == 1


def test_stale_cards_invalidated_after_context_change_and_no_batch_hire(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    cards = ok(client.get("/api/v1/biz/decision-cards", headers=f.auth["manager"]))["items"]
    assert len(cards) == 1
    key = cards[0]["id"]
    prepare(f)
    result = client.post(
        f"/api/v1/biz/decision-cards/{key}/resolve",
        headers={**f.auth["manager"], "Idempotency-Key": uuid4().hex},
        json={"expected_version": 1, "option": "dismiss", "reason": "旧卡"},
    )
    assert result.status_code == 409
    cards = ok(client.get("/api/v1/biz/decision-cards", headers=f.auth["manager"]))["items"]
    assert len(cards) == 1 and cards[0]["id"] != key
    bad = client.post(
        f"/api/v1/biz/decision-cards/{cards[0]['id']}/resolve",
        headers=f.auth["manager"],
        json={"expected_version": 1, "option": "hire", "reason": "不能一键录用"},
    )
    assert bad.status_code == 400


def test_context_change_resets_pending_approval_and_preserves_history(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    prepare(f)
    ok(act_hire(f, "decide", "manager", decision="hire"))
    ok(act_hire(f, "approve", "director"))
    c = ok(client.get(f"/api/v1/hr/candidates/{f.c['id']}", headers=f.auth["hr"]))
    ok(candidate_command(client, login, c, "key", key_candidate=True))
    h = get(f)
    assert h["status"] == "deciding" and h["facts"] is None
    assert any(x["action"] == "context_changed" for x in h["history"])


def test_approval_rejection_withdrawal_and_freeze(client, login, fields, container):
    f = ready(client, login, fields, container)
    prepare(f)
    ok(act_hire(f, "decide", "manager", decision="hire"))
    assert act_hire(f, "reject", "director").status_code == 422
    assert ok(act_hire(f, "reject", "director", reason="请补充信息"))["status"] == "deciding"
    ok(act_hire(f, "decide", "manager", decision="hire"))
    assert ok(act_hire(f, "withdraw", reason="重新核实"))["status"] == "deciding"
    pos = ok(act(client, login, f.pos, "pause", handling="freeze", reason="暂缓"))
    assert act_hire(f, "decide", "manager", decision="hire").status_code == 409
    assert ok(client.get("/api/v1/hr/decision-cards", headers=f.auth["hr"]))["items"] == []
    ok(act(client, login, pos, "resume"))


def test_parallel_final_approval_last_position_slot_only_one_wins(client, login, fields, container):
    f = ready(client, login, {**fields, "headcount": "1"}, container)
    g = ready(client, login, fields, container, existing=f)
    for target in (f, g):
        prepare(target)
        ok(act_hire(target, "decide", "manager", decision="hire"))
        ok(act_hire(target, "approve", "director"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(lambda target: act_hire(target, "approve", "hrbp").status_code, (f, g))
        )
    assert sorted(statuses) == [200, 409]


def test_workbench_scope_no_mock_data_and_overdue_never_auto_approves(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    get(f)
    later = container.clock.now() + timedelta(days=10)
    container.clock = SimpleNamespace(now=lambda: later)
    view = ok(client.get("/api/v1/hr/workbench-live", headers=f.auth["hr"]))
    assert not view["ai_enabled"] and not view["ai_activity"]
    assert view["hires"][0]["status"] == "deciding" and view["hires"][0]["reminders"]
    hidden = ok(client.get("/api/v1/hr/workbench-live", headers=f.auth["outsider"]))
    assert hidden["hires"] == [] and hidden["positions"] == [] and hidden["cards"] == []


def config(client, login, **body):
    return client.post(
        "/api/v1/hr/automation-live",
        headers=login("admin", uuid4().hex),
        json={"expected_version": 1, **body},
    )


@pytest.mark.parametrize(
    "node,level", [("reject", 3), ("hire", 2), ("conversation", 1), ("unknown", 2)]
)
def test_automation_hard_limits_rejected_by_api(client, login, node, level):
    assert config(client, login, levels={node: level}).json()["error"]["code"] == "AUTOMATION_LIMIT"


def test_automation_inheritance_modes_history_and_empty_approval_chain(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    v = ok(config(client, login, mode="normal", approval_nodes=[], levels={"advance": 3}))
    assert v["version"] == 2
    # Position overrides belong to a scoped recruiting lead, not the admin identity.
    r = client.post(
        "/api/v1/hr/automation-live",
        headers=login("hr", uuid4().hex),
        json={
            "scope": "position",
            "target": f.pos["id"],
            "expected_version": 1,
            "levels": {"advance": 2},
        },
    )
    ok(r)
    with container.scope() as s:
        p = {"id": f.pos["id"], "dept": f.pos["dept"], "series": "客服", "confidential": False}
        assert s.automation.effective("advance", p) == 2
        assert s.automation.effective("hire", p) == 1
        assert s.automation.effective("reject", p) <= 2
    prepare(f)
    assert ok(act_hire(f, "decide", "manager", decision="hire"))["status"] == "approved"
    restored = ok(config(client, login, expected_version=2, restore_version=1))
    assert restored["version"] == 3 and restored["mode"] == "manual"


def test_close_keeps_hired_application_and_headcount_until_failed_result(
    client, login, fields, container
):
    from app.kernel.types import Ctx, Principal

    f = ready(client, login, fields, container)
    with container.scope() as s:
        # This fixture uses an outsourced requisition; attach the same ledger that a formal approval creates.
        assert s.org.reserve_headcount(
            Ctx(Principal("hr", "HR", (), ()), "fixture"),
            f.pos["dept"],
            f.pos["requisitionIds"][0],
            2,
        )
    handed(f)
    ok(act(client, login, f.pos, "close", reason="招满"))
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["outcome"] is None
        assert s.org.headcount(f.pos["dept"])["reserved"] == 1
    ok(act_hire(f, "result", result="declined", reason="候选人放弃"))
    with container.scope() as s:
        assert s.org.headcount(f.pos["dept"])["reserved"] == 0
    assert get(f)["remaining"] == 2


def test_handoff_requires_evidence_and_excel_is_hr_only_and_text_safe(
    client, login, fields, container
):
    from io import BytesIO
    from xml.etree.ElementTree import fromstring
    from zipfile import ZipFile

    from app.modules.hiring.export import workbook

    f = ready(client, login, fields, container)
    approved(f)
    assert act_hire(f, "handover").status_code == 409
    assert client.get(ROOT + f"/{f.hid}/handoff.xlsx", headers=f.auth["manager"]).status_code == 403
    r = client.get(ROOT + f"/{f.hid}/handoff.xlsx", headers=f.auth["hr"])
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    with ZipFile(BytesIO(r.content)) as archive:
        sheet = fromstring(archive.read("xl/worksheets/sheet1.xml"))
        assert "录用移交单" in "".join(sheet.itertext())
    with ZipFile(BytesIO(workbook([("姓名", '=HYPERLINK("evil")\x00')]))) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml")
        sheet = fromstring(xml)
        assert b"<f>" not in xml and b"inlineStr" in xml


def test_accepted_candidate_creates_other_application_decision_and_stale_card_cannot_terminate(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    other = setup(client, login, fields, container)
    other_app = ok(attach(client, login, f.c, other.pos))
    handed(f)
    ok(
        act_hire(
            f,
            "result",
            result="accepted",
            expected_start=(container.clock.now() + timedelta(days=15)).date().isoformat(),
        )
    )
    cards = ok(client.get("/api/v1/hr/decision-cards", headers=f.auth["hr"]))["items"]
    card = next(c for c in cards if c["kind"] == "other_application")
    assert card["application_id"] == other_app["id"]
    ok(act_hire(f, "result", result="no_show", reason="原录用未入职"))
    response = client.post(
        f"/api/v1/hr/decision-cards/{card['id']}/resolve",
        headers={**f.auth["hr"], "Idempotency-Key": uuid4().hex},
        json={"expected_version": card["version"], "option": "terminate", "reason": "旧通知"},
    )
    assert response.status_code == 409
    with container.scope() as s:
        assert s.application.interview_context(other_app["id"])["outcome"] is None


def test_nonpassing_feedback_card_is_manual_and_idempotent(client, login, fields, container):
    f = setup(client, login, fields, container)
    original = container.clock
    finished(f)
    ok(feedback(f, recommendation="no"))
    container.clock = original
    cards = ok(client.get("/api/v1/hr/decision-cards", headers=f.auth["hr"]))["items"]
    card = next(c for c in cards if c["kind"] == "interview_reject")
    auth = {**f.auth["hr"], "Idempotency-Key": uuid4().hex}
    body = {"expected_version": card["version"], "option": "reject", "reason": "已核实面评证据"}
    for _ in range(2):
        assert (
            ok(
                client.post(
                    f"/api/v1/hr/decision-cards/{card['id']}/resolve", headers=auth, json=body
                )
            )["state"]
            == "resolved"
        )
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["outcome"] == "rejected"


def test_current_approver_revocation_and_automation_policy_snapshot(
    client, login, fields, container
):
    from app.modules.org.adapters.repository import UserRecord

    f = ready(client, login, fields, container)
    prepare(f)
    ok(act_hire(f, "decide", "manager", decision="hire"))
    ok(config(client, login, approval_nodes=[]))
    assert len(get(f)["chain"]) == 2
    with container.scope() as s:
        user = s.session.get(UserRecord, "director")
        user.roles = []
        user.directory_roles = []
        user.version += 1
    assert client.get(ROOT + "/" + f.hid, headers=f.auth["director"]).status_code == 404
    assert get(f)["status"] == "pending"


def test_active_hire_blocks_identity_merge_and_delete(client, login, fields, container):
    f = ready(client, login, fields, container)
    approved(f)
    other = create(client, login, name="另一份档案")
    c = ok(client.get(f"/api/v1/hr/candidates/{f.c['id']}", headers=f.auth["hr"]))
    assert (
        candidate_command(
            client,
            login,
            c,
            "merge",
            target_id=other["id"],
            target_version=other["version"],
            reason="合并",
        ).status_code
        == 409
    )
    assert candidate_command(client, login, c, "erase", reason="删除").status_code == 409


def test_series_policy_inheritance_scope_and_strict_levels(client, login, fields, container):
    f = ready(client, login, fields, container)
    ok(config(client, login, mode="normal", levels={"advance": 3}))
    series = "长序列:" * 20
    v = ok(
        config(
            client, login, scope="series", dept=f.pos["dept"], target=series, levels={"advance": 1}
        )
    )
    assert len(v["id"]) <= 64
    with container.scope() as s:
        p = {"id": f.pos["id"], "dept": f.pos["dept"], "series": series}
        assert s.automation.effective("advance", p) == 1
        assert s.automation.series_key("a:b", "c") != s.automation.series_key("a", "b:c")
    assert config(client, login, expected_version=2, levels={"hire": True}).status_code == 400
    assert (
        config(client, login, expected_version=2, low_threshold=0.9, high_threshold=0.8).status_code
        == 422
    )
    assert client.get("/api/v1/hr/automation-live", headers=login("manager")).status_code == 403
    assert (
        client.get("/api/v1/hr/automation-live?scope=invalid", headers=login("admin")).status_code
        == 400
    )


def test_failed_hire_save_rolls_back_final_approval_and_quota(
    client, login, fields, container, monkeypatch
):
    from app.modules.hiring.repository import HireRecord
    from app.platform.aggregates import EncryptedStore

    f = ready(client, login, fields, container)
    prepare(f)
    ok(act_hire(f, "decide", "manager", decision="hire"))
    ok(act_hire(f, "approve", "director"))
    before = get(f)
    original = EncryptedStore.save

    def fail_after_application_change(self, value, previous=None):
        if self.model is HireRecord and value["status"] == "approved":
            raise RuntimeError("injected hire save failure")
        return original(self, value, previous)

    monkeypatch.setattr(EncryptedStore, "save", fail_after_application_change)
    with pytest.raises(RuntimeError, match="injected hire save failure"):
        act_hire(f, "approve", "hrbp")
    after = get(f)
    assert after["version"] == before["version"] and after["status"] == "pending"
    assert after["chain"][-1]["status"] == "pending"
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["stage"] == "manager_eval"
        assert s.position.hiring_context(f.pos["id"])["hired"] == 0
    monkeypatch.setattr(EncryptedStore, "save", original)
    assert ok(act_hire(f, "approve", "hrbp"))["status"] == "approved"


def test_result_reminder_does_not_reopen_kept_other_application_card(
    client, login, fields, container
):
    f = ready(client, login, fields, container)
    other = setup(client, login, fields, container)
    ok(attach(client, login, f.c, other.pos))
    handed(f)
    ok(
        act_hire(
            f,
            "result",
            result="accepted",
            expected_start=(container.clock.now() + timedelta(days=15)).date().isoformat(),
        )
    )
    card = next(
        c
        for c in ok(client.get("/api/v1/hr/decision-cards", headers=f.auth["hr"]))["items"]
        if c["kind"] == "other_application"
    )
    ok(
        client.post(
            f"/api/v1/hr/decision-cards/{card['id']}/resolve",
            headers={**f.auth["hr"], "Idempotency-Key": uuid4().hex},
            json={
                "expected_version": card["version"],
                "option": "keep",
                "reason": "人工保留备选流程",
            },
        )
    )
    original = container.clock
    later = original.now() + timedelta(days=10)
    container.clock = SimpleNamespace(now=lambda: later)
    with container.scope() as s:
        s.decision.sync()
        assert s.hiring.records()[0]["reminders"]
        assert not any(
            c["kind"] == "other_application" and c["state"] == "open"
            for c in s.decision.store.all()
        )
    container.clock = original
