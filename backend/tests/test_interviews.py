from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_candidates import app_action, attach, command, create, ok
from test_conversations import link, portal_act
from test_positions import act, opened

from app.bootstrap import build_container
from app.interview_worker import run_once
from app.modules.interview.integration import IntegrationRejected
from app.modules.interview.repository import InterviewRecord, ReservationRecord

ROOT = "/api/v1/hr/interviews"
DEFAULT_ROUND = {
    "name": "专业面",
    "format": "phone",
    "duration": 30,
    "interviewers": ["manager"],
    "rule": "unanimous",
    "criteria": "专业能力\n沟通能力",
}


def setup(client, login, fields, container, rounds=None):
    _, pos = opened(
        client, login, fields, container, title="面试岗位" + uuid4().hex[:6], key=uuid4().hex
    )
    if rounds != []:
        pos = ok(act(client, login, pos, "save_interview_plan", rounds=rounds or [DEFAULT_ROUND]))
    c = create(
        client,
        login,
        name="面试候选人",
        phone="",
        experience="电话13800138000",
        expected_salary="不向面试官公开",
    )
    c = ok(
        command(client, login, c, "consent", granted=True, evidence="本人签名", reason="招聘评估")
    )
    app = ok(attach(client, login, c, pos))
    for _ in range(3):
        app = ok(app_action(client, login, app, "advance"))
    auth = {actor: login(actor) for actor in ("hr", "manager", "director", "outsider", "admin")}
    iv = ok(client.get(ROOT, headers=auth["hr"], params={"application_id": app["id"]}))["items"][0]
    return SimpleNamespace(
        client=client,
        login=login,
        container=container,
        c=c,
        app=app,
        pos=pos,
        iv=iv,
        auth=auth,
        portal=link(client, login, c["id"]),
    )


def get(f, actor="hr", iid=None):
    return ok(f.client.get(ROOT + "/" + (iid or f.iv["id"]), headers=f.auth[actor]))


def action(f, name, actor="hr", iid=None, version=None, **body):
    iid = iid or f.iv["id"]
    value = version if version is not None else get(f, actor, iid)["version"]
    return f.client.post(
        ROOT + "/" + iid + "/actions",
        headers={**f.auth[actor], "Idempotency-Key": uuid4().hex},
        json={"action": name, "expected_version": value, **body},
    )


def choose(f, slot, action_name="book", **body):
    iv = get(f)
    return f.client.post(
        f"/api/v1/candidate/interviews/{iv['id']}/actions",
        headers={**f.portal, "Idempotency-Key": uuid4().hex},
        json={"action": action_name, "expected_version": iv["version"], "slot_id": slot, **body},
    )


def offer(f):
    return ok(action(f, "offer", verified=True))


def finished(f):
    iv = offer(f)
    iv = ok(choose(f, iv["slots"][0]["id"]))
    now = datetime.fromisoformat(iv["end"]) + timedelta(minutes=1)
    f.container.clock = SimpleNamespace(now=lambda: now)
    return ok(action(f, "complete", reason="已核实双方完成面试"))


def feedback(f, actor="manager", recommendation="yes", **extra):
    return action(
        f,
        "feedback",
        actor=actor,
        scores={"专业能力": 4, "沟通能力": 3},
        recommendation=recommendation,
        strengths="能给出具体实践证据",
        concerns="需要补充案例" if recommendation in {"hold", "no"} else "",
        verified=True,
        **extra,
    )


def test_enter_interview_snapshots_plan_and_unconfigured_can_recover(
    client, login, fields, container
):
    f = setup(client, login, fields, container)
    assert f.iv["status"] == "waiting"
    assert f.iv["plan_version"] == 1
    pos = ok(
        act(
            client,
            login,
            f.pos,
            "save_interview_plan",
            rounds=[{**DEFAULT_ROUND, "name": "新流程", "duration": 60}],
        )
    )
    assert pos["interviewPlans"][-1]["version"] == 2
    assert get(f)["spec"]["duration"] == 30
    assert action(f, "configure").status_code == 409
    other = setup(client, login, fields, container, rounds=[])
    assert other.iv["status"] == "needs_configuration"
    ok(act(client, login, other.pos, "save_interview_plan", rounds=[DEFAULT_ROUND]))
    assert ok(action(other, "configure"))["status"] == "waiting"


def test_offer_24h_and_candidate_ownership_and_idempotency(client, login, fields, container):
    f = setup(client, login, fields, container)
    assert action(f, "offer").status_code == 422
    iv = offer(f)
    assert 3 <= len(iv["slots"]) <= 5
    assert all(
        datetime.fromisoformat(s["start"])
        >= container.clock.now() + timedelta(hours=25, minutes=59)
        for s in iv["slots"]
    )
    assert len({s["start"][:10] for s in iv["slots"]}) == len(iv["slots"])
    other = create(client, login)
    other_portal = link(client, login, other["id"])
    body = {
        "action": "book",
        "expected_version": iv["version"],
        "slot_id": iv["slots"][0]["id"],
        "recording_consent": False,
    }
    assert (
        client.post(
            f"/api/v1/candidate/interviews/{iv['id']}/actions",
            headers={**other_portal, "Idempotency-Key": uuid4().hex},
            json=body,
        ).status_code
        == 404
    )
    auth = {**f.portal, "Idempotency-Key": uuid4().hex}
    for _ in range(2):
        result = ok(
            client.post(f"/api/v1/candidate/interviews/{iv['id']}/actions", headers=auth, json=body)
        )
        assert result["status"] == "scheduled"
        assert not result["recording_enabled"]
        assert "feedback" not in result and "profile" not in result
    with container.scope() as s:
        reservations = list(s.session.scalars(select(ReservationRecord)))
        assert len(reservations) == 2 and all(r.expires_at is None for r in reservations)


def test_expired_holds_release_after_restart(client, login, fields, container):
    f = setup(client, login, fields, container)
    iv = offer(f)
    future = container.clock.now() + timedelta(hours=25)
    container.clock = SimpleNamespace(now=lambda: future)
    assert choose(f, iv["slots"][0]["id"]).status_code == 409
    restarted = build_container(container.settings, container.clock)
    run_once(restarted)
    assert get(f)["status"] == "waiting"
    with restarted.scope() as s:
        assert not list(s.session.scalars(select(ReservationRecord)))
    restarted.db.engine.dispose()


def test_concurrent_booking_same_interviewer_only_one_wins(client, login, fields, container):
    f = setup(client, login, fields, container)
    g = setup(client, login, fields, container)
    start = offer(f)["slots"][0]["start"]
    ok(action(f, "reschedule", reason="释放待选时段，手动协调"))

    def book(target):
        return action(target, "book", start=start, verified=True).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(book, [f, g])) == [200, 409]


def test_buffer_and_daily_limits_and_preferences(client, login, fields, container):
    f = setup(client, login, fields, container)
    g = setup(client, login, fields, container)
    iv = offer(f)
    booked = ok(choose(f, iv["slots"][0]["id"]))
    assert action(g, "book", verified=True, start=booked["end"]).status_code == 409
    pref = ok(client.get("/api/v1/biz/interview-availability", headers=f.auth["manager"]))
    payload = {k: v for k, v in pref.items() if k != "version"}
    payload.update(expected_version=pref["version"], daily_limit=1)
    ok(
        client.post(
            "/api/v1/biz/interview-availability",
            headers={**f.auth["manager"], "Idempotency-Key": uuid4().hex},
            json=payload,
        )
    )
    later = datetime.fromisoformat(booked["end"]) + timedelta(hours=2)
    assert (
        action(g, "book", verified=True, start=later.isoformat()).json()["error"]["code"]
        == "INTERVIEW_LIMIT"
    )


def test_candidate_reschedule_limit_and_last_minute_keeps_booking(client, login, fields, container):
    f = setup(client, login, fields, container)
    for _ in range(2):
        iv = offer(f)
        ok(choose(f, iv["slots"][0]["id"]))
        assert ok(choose(f, "", "request_reschedule", reason="调整时间"))["status"] == "waiting"
    iv = offer(f)
    booked = ok(choose(f, iv["slots"][0]["id"]))
    result = ok(choose(f, "", "request_reschedule", reason="第三次调整"))
    assert result["status"] == "scheduled" and result["start"] == booked["start"]
    near = datetime.fromisoformat(booked["start"]) - timedelta(hours=1)
    container.clock = SimpleNamespace(now=lambda: near)
    assert ok(choose(f, "", "request_reschedule", reason="临近面试"))["status"] == "scheduled"


def test_feedback_validation_and_last_round_advances_without_hiring(
    client, login, fields, container
):
    f = setup(client, login, fields, container)
    assert feedback(f).status_code == 409
    finished(f)
    assert feedback(f, actor="hr").status_code == 403
    assert (
        action(
            f,
            "feedback",
            actor="manager",
            scores={"专业能力": 5},
            recommendation="yes",
            strengths="优势",
            verified=True,
        ).status_code
        == 422
    )
    assert (
        action(
            f,
            "feedback",
            actor="manager",
            scores={"专业能力": 4, "沟通能力": 4},
            recommendation="no",
            strengths="优点",
            verified=True,
        ).status_code
        == 422
    )
    result = ok(feedback(f))
    assert result["status"] == "completed" and result["result"] == "pass"
    with container.scope() as s:
        app = s.application.interview_context(f.app["id"])
        assert app["stage"] == "manager_eval" and app["outcome"] is None
    portal = ok(client.get("/api/v1/candidate/interviews", headers=f.portal))
    assert "scores" not in str(portal) and "recommendation" not in str(portal)


@pytest.mark.parametrize(
    "rule,recommendations,result",
    [
        ("unanimous", ["yes", "no"], "needs_hr_decision"),
        ("majority", ["yes", "hold"], "needs_hr_decision"),
        ("designated", ["yes", "no"], "pass"),
    ],
)
def test_multiple_feedback_rules_and_no_automatic_rejection(
    client, login, fields, container, rule, recommendations, result
):
    f = setup(
        client,
        login,
        fields,
        container,
        rounds=[
            {
                **DEFAULT_ROUND,
                "interviewers": ["manager", "director"],
                "rule": rule,
                "decision_by": "manager",
            }
        ],
    )
    finished(f)
    assert ok(feedback(f, recommendation=recommendations[0]))["status"] == "awaiting_feedback"
    data = ok(feedback(f, actor="director", recommendation=recommendations[1]))
    assert data["result"] == result
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["outcome"] is None


def test_prior_round_scores_hidden_until_current_submission(client, login, fields, container):
    f = setup(
        client,
        login,
        fields,
        container,
        rounds=[DEFAULT_ROUND, {**DEFAULT_ROUND, "name": "复试", "interviewers": ["director"]}],
    )
    finished(f)
    ok(feedback(f))
    rows = ok(client.get(ROOT, headers=f.auth["hr"]))["items"]
    second = next(r for r in rows if r["round_no"] == 2)
    data = get(f, "director", second["id"])
    assert "feedback" not in data["previous_rounds"][0]
    assert get(f, "director")["feedback"] == {}
    f.iv = second
    finished(f)
    data = ok(feedback(f, actor="director"))
    assert data["previous_rounds"][0]["feedback"]["manager"]["scores"]


def test_feedback_amendment_24h_audit_and_late_remark(client, login, fields, container):
    f = setup(client, login, fields, container)
    finished(f)
    ok(feedback(f))
    data = ok(feedback(f, recommendation="no"))
    assert data["result"] == "needs_hr_decision"
    with container.scope() as s:
        assert s.application.interview_context(f.app["id"])["stage"] == "interview"
        assert len(s.interview.store.get(f.iv["id"])["feedback_history"]) == 1
    later = container.clock.now() + timedelta(hours=25)
    container.clock = SimpleNamespace(now=lambda: later)
    assert feedback(f).status_code == 409
    assert (
        ok(action(f, "remark", actor="manager", reason="追加说明"))["my_feedback"]["remarks"][0][
            "text"
        ]
        == "追加说明"
    )


def test_cancellation_termination_and_erasure_release_resources(client, login, fields, container):
    f = setup(client, login, fields, container)
    offer(f)
    app = ok(app_action(client, login, f.app, "withdraw", reason="候选人放弃"))
    assert app["outcome"] == "withdrawn" and get(f)["status"] == "cancelled"
    with container.scope() as s:
        assert not list(s.session.scalars(select(ReservationRecord)))
    current = ok(client.get(f"/api/v1/hr/candidates/{f.c['id']}", headers=f.auth["hr"]))
    ok(command(client, login, current, "erase", reason="本人要求"))
    with container.scope() as s:
        assert not list(s.session.scalars(select(InterviewRecord)))


def test_privacy_releases_holds_and_blocks_booking(client, login, fields, container):
    f = setup(client, login, fields, container)
    iv = offer(f)
    ok(portal_act(client, f.portal, "revoke"))
    assert get(f)["status"] == "waiting"
    assert choose(f, iv["slots"][0]["id"]).status_code == 409
    with container.scope() as s:
        assert not list(s.session.scalars(select(ReservationRecord)))


def test_permissions_masking_and_no_show_time_guard(client, login, fields, container):
    f = setup(client, login, fields, container)
    for actor in ("outsider", "admin"):
        assert client.get(ROOT + "/" + f.iv["id"], headers=f.auth[actor]).status_code == 404
    data = get(f, "manager")
    assert "expected_salary" not in data["profile"] and "13800138000" not in str(data)
    assert action(f, "cancel", actor="manager", reason="不能代 HR 取消").status_code == 404
    iv = offer(f)
    booked = ok(choose(f, iv["slots"][0]["id"]))
    assert action(f, "complete", reason="过早").status_code == 409
    assert action(f, "no_show", reason="过早").status_code == 409
    at = datetime.fromisoformat(booked["start"]) + timedelta(minutes=15)
    container.clock = SimpleNamespace(now=lambda: at)
    assert ok(action(f, "no_show", reason="人工核实未到场"))["status"] == "no_show"


def test_reminder_monitor_dedup_and_stops_after_feedback(client, login, fields, container):
    f = setup(client, login, fields, container)
    finished(f)
    after = container.clock.now() + timedelta(hours=49)
    container.clock = SimpleNamespace(now=lambda: after)
    run_once(container)
    run_once(container)
    assert len(get(f)["reminders"]) == 3
    ok(feedback(f))
    run_once(container)
    assert len(get(f)["reminders"]) == 3


def test_integration_failure_compensates_created_meeting_and_retries(
    client, login, fields, container
):
    class Gateway:
        def __init__(self):
            self.created, self.cancelled, self.calendar_keys = set(), [], set()
            self.fail = True

        def meeting_create(self, iv, key):
            assert iv["recording_enabled"] is False
            self.created.add(key)
            return "meeting-ref"

        def calendar_create(self, iv, key):
            self.calendar_keys.add(key)
            if self.fail:
                raise IntegrationRejected("secret must never be stored")
            return "calendar-ref"

        def meeting_cancel(self, reference, key):
            self.cancelled.append(reference)

        def calendar_cancel(self, reference, key):
            self.cancelled.append(reference)

    f = setup(client, login, fields, container, rounds=[{**DEFAULT_ROUND, "format": "video"}])
    gateway = Gateway()
    container.interview_gateway = gateway
    iv = offer(f)
    ok(choose(f, iv["slots"][0]["id"]))
    for _ in range(6):
        run_once(container)
    assert get(f)["integration_state"] == "failed"
    assert gateway.cancelled == ["meeting-ref"] and len(gateway.created) == 1
    with container.scope() as s:
        assert "secret must" not in str(s.interview.store.get(f.iv["id"]))
    gateway.fail = False
    ok(action(f, "retry_integration"))
    run_once(container)
    run_once(container)
    assert get(f)["integration_state"] == "synced"
    ok(action(f, "cancel", reason="取消并清理"))
    for _ in range(3):
        run_once(container)
    assert get(f)["integration_state"] == "cancelled"
    assert gateway.cancelled == ["meeting-ref", "calendar-ref", "meeting-ref"]


def test_cross_position_candidate_conflict_with_different_interviewers(
    client, login, fields, container
):
    f = setup(client, login, fields, container)
    g = setup(
        client, login, fields, container, rounds=[{**DEFAULT_ROUND, "interviewers": ["director"]}]
    )
    app = ok(attach(client, login, f.c, g.pos))
    for _ in range(3):
        app = ok(app_action(client, login, app, "advance"))
    iv = ok(client.get(ROOT, headers=f.auth["hr"], params={"application_id": app["id"]}))["items"][
        0
    ]
    first = offer(f)
    booked = ok(choose(f, first["slots"][0]["id"]))
    response = action(f, "book", iid=iv["id"], start=booked["start"], verified=True)
    assert response.status_code == 409 and response.json()["error"]["code"] == "SLOT_CONFLICT"
    ok(action(f, "cancel", reason="释放原面试时间"))
    assert (
        ok(action(f, "book", iid=iv["id"], start=booked["start"], verified=True))["status"]
        == "scheduled"
    )


def test_position_freeze_blocks_booking_and_close_releases_holds(client, login, fields, container):
    f = setup(client, login, fields, container)
    iv = offer(f)
    pos = ok(act(client, login, f.pos, "pause", handling="freeze", reason="暂停面试"))
    assert choose(f, iv["slots"][0]["id"]).json()["error"]["code"] == "POSITION_FROZEN"
    ok(act(client, login, pos, "close", reason="需求取消"))
    assert get(f)["status"] == "cancelled"
    with container.scope() as s:
        assert not list(s.session.scalars(select(ReservationRecord)))


def test_feedback_requires_answers_and_recusal_and_strict_scores(client, login, fields, container):
    f = setup(client, login, fields, container)
    with container.scope() as s:
        iv = s.interview.store.get(f.iv["id"])
        iv["must_ask"] = "请描述一次解决故障的经历"
        s.interview.store.save(iv, iv["version"])
    finished(f)
    assert feedback(f).json()["error"]["code"] == "ANSWERS_REQUIRED"
    answers = {"请描述一次解决故障的经历": "描述排查过程及结果"}
    assert (
        feedback(f, answers=answers, recused=True).json()["error"]["code"]
        == "VERIFICATION_REQUIRED"
    )
    invalid = action(f, "feedback", actor="manager", scores={"专业能力": True, "沟通能力": 3})
    assert invalid.status_code in {400, 422}
    assert ok(feedback(f, answers=answers))["result"] == "pass"


def test_removed_interviewer_scope_blocks_read_feedback_and_booking(
    client, login, fields, container
):
    from app.modules.org.adapters.repository import UserRecord

    f = setup(client, login, fields, container)
    offered = offer(f)
    with container.scope() as s:
        user = s.session.get(UserRecord, "manager")
        user.directory_roles = []
        user.directory_departments = []
        user.roles = ["interviewer"]
        user.departments = []
        user.version += 1
    f.auth["manager"] = login("manager")
    assert client.get(ROOT + "/" + f.iv["id"], headers=f.auth["manager"]).status_code == 404
    result = choose(f, offered["slots"][0]["id"])
    assert result.status_code == 409 and result.json()["error"]["code"] == "INTERVIEWER_INVALID"


def test_unknown_external_result_retries_original_key_before_cancellation(
    client, login, fields, container
):
    class Gateway:
        def __init__(self):
            self.keys, self.cancelled, self.timeout = set(), [], True

        def meeting_create(self, iv, key):
            self.keys.add(key)  # The provider created it, but its response was lost.
            if self.timeout:
                raise TimeoutError("untrusted provider detail")
            return "original-meeting"

        def calendar_create(self, iv, key):
            return "calendar"

        def meeting_cancel(self, reference, key):
            self.cancelled.append(reference)

        def calendar_cancel(self, reference, key):
            self.cancelled.append(reference)

    f = setup(client, login, fields, container, rounds=[{**DEFAULT_ROUND, "format": "video"}])
    gateway = Gateway()
    container.interview_gateway = gateway
    iv = offer(f)
    ok(choose(f, iv["slots"][0]["id"]))
    for _ in range(3):
        run_once(container)
    assert get(f)["integration_state"] == "uncertain_meeting"
    assert (
        action(f, "cancel", reason="不能遗留未核实会议").json()["error"]["code"]
        == "INTEGRATION_UNCERTAIN"
    )
    gateway.timeout = False
    ok(action(f, "retry_integration"))
    run_once(container)
    run_once(container)
    assert get(f)["integration_state"] == "synced" and len(gateway.keys) == 1
    ok(action(f, "cancel", reason="完成核实后取消"))
    for _ in range(3):
        run_once(container)
    assert gateway.cancelled == ["calendar", "original-meeting"]


@pytest.mark.postgres
def test_postgres_exclusion_constraint_blocks_overlap_without_service_lock(container):
    if container.db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only database exclusion constraint")
    now = datetime.now(UTC)

    def insert(key):
        try:
            with container.db.sessions.begin() as s:
                s.add(
                    ReservationRecord(
                        id=key,
                        interview_id=key,
                        resource="user:race",
                        slot_id=key,
                        start_at=now,
                        end_at=now + timedelta(hours=1),
                        expires_at=None,
                    )
                )
            return "booked"
        except IntegrityError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(insert, ["first", "second"])) == ["booked", "conflict"]


def test_undo_rejection_creates_new_schedulable_cycle(client, login, fields, container):
    f = setup(client, login, fields, container)
    offer(f)
    ended = ok(app_action(client, login, f.app, "reject", reason="补充核实", reason_code="skills"))
    assert get(f)["status"] == "cancelled"
    restored = ok(app_action(client, login, ended, "undo_reject", reason="恢复面试"))
    assert restored["stage"] == "interview"
    rows = ok(client.get(ROOT, headers=f.auth["hr"], params={"application_id": restored["id"]}))[
        "items"
    ]
    assert len(rows) == 2
    active = next(r for r in rows if r["status"] == "waiting")
    assert ok(action(f, "offer", iid=active["id"], verified=True))["slots"]


def test_frozen_position_cannot_advance_with_feedback_then_can_restart(
    client, login, fields, container
):
    f = setup(client, login, fields, container)
    login = lambda actor="hr", key="test-request": {**f.auth[actor], "Idempotency-Key": key}  # noqa: E731
    finished(f)
    pos = ok(act(client, login, f.pos, "pause", handling="freeze", reason="暂缓决定"))
    assert feedback(f).json()["error"]["code"] == "POSITION_FROZEN"
    assert get(f, "manager")["my_feedback"] is None
    ok(act(client, login, pos, "resume"))
    assert ok(feedback(f))["result"] == "pass"
    apps = ok(client.get(f"/api/v1/hr/candidates/{f.c['id']}", headers=f.auth["hr"]))[
        "applications"
    ]
    app = next(a for a in apps if a["id"] == f.app["id"])
    assert app["stage"] == "manager_eval"
    ok(app_action(client, login, app, "rollback", target_stage="interview", reason="补充面试"))
    rows = ok(client.get(ROOT, headers=f.auth["hr"], params={"application_id": app["id"]}))["items"]
    assert len([r for r in rows if r["status"] == "waiting"]) == 1
