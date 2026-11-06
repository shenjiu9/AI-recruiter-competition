import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_candidates import app_action, attach, command, create, docx, ok, upload
from test_positions import opened

from app.ai_worker import run_once
from app.engine.repository import JobRecord
from app.engine.validation import validate
from app.kernel.types import DomainError

ROOT = "/api/v1/hr/ai-jobs"


class Gateway:
    def configured(self, component):
        return True

    def call(self, component, inputs, action_id, sample=0, retry_reason=None):
        if hasattr(self, "during"):
            self.during()
        if hasattr(self, "failure"):
            raise DomainError(self.failure, "simulated failure", 503)
        output = {
            "fields": {
                "skills": {
                    "value": "Python",
                    "evidence": {"source": "profile", "ref": "F:skills", "quote": "Python"},
                }
            }
        }
        if component == "A5":
            output = {
                "items": [
                    {
                        "id": c["id"],
                        "verdict": "meet",
                        "evidence": [{"source": "profile", "ref": "F:skills", "quote": "Python"}],
                    }
                    for c in inputs["criteria"]
                ],
                "self_confidence": 1,
            }
        return {"output": output, "run_id": action_id, "tokens": 10, "elapsed_ms": 1}


def enable(client, login, mode="normal", **extra):
    old = ok(client.get("/api/v1/hr/automation-live", headers=login("admin")))
    return ok(
        client.post(
            "/api/v1/hr/automation-live",
            headers=login("admin", uuid4().hex),
            json={
                "expected_version": old["version"],
                "mode": mode,
                "components": {f"A{i}": True for i in range(1, 8)},
                **extra,
            },
        )
    )


def setup(client, login, container):
    container.ai_gateway = Gateway()
    enable(client, login)
    candidate = create(client, login, skills="Python", phone="13800138000")
    return ok(
        command(
            client,
            login,
            candidate,
            "consent",
            granted=True,
            evidence="本人签名",
            reason="招聘评估",
        )
    )


def start(client, login, component, object_id, **extra):
    return client.post(
        ROOT,
        headers=login(key=uuid4().hex),
        json={"component": component, "object_id": object_id, **extra},
    )


def get(client, login, job):
    return ok(client.get(ROOT + "/" + job["id"], headers=login()))


def action(client, login, job, action="approve", **extra):
    return client.post(
        ROOT + "/" + job["id"] + "/actions",
        headers=login(key=uuid4().hex),
        json={
            "action": action,
            "expected_version": job["version"],
            "reason": "逐项核实原文",
            "verified": True,
            **extra,
        },
    )


def test_extraction_review_encryption_idempotency_and_no_transaction_during_call(
    client, login, container
):
    candidate = setup(client, login, container)
    body = {"component": "A3", "object_id": candidate["id"]}
    headers = login(key="ai-stable")
    job = ok(client.post(ROOT, headers=headers, json=body))
    assert ok(client.post(ROOT, headers=headers, json=body))["id"] == job["id"]
    assert "13800138000" not in json.dumps(job["inputs"])
    with container.db.sessions() as db:
        assert b"Python" not in db.scalar(select(JobRecord)).data
    # A second committed transaction is possible while model execution is active.
    container.ai_gateway.during = lambda: ok(client.get("/api/v1/hr/candidates", headers=login()))
    assert run_once(container)
    job = get(client, login, job)
    assert job["status"] == "review" and job["output"]["fields"]["skills"]["value"] == "Python"
    assert action(client, login, job, verified=False).status_code == 409
    assert ok(action(client, login, job))["status"] == "applied"
    assert not run_once(container)
    assert client.get(ROOT + "/" + job["id"], headers=login("admin")).status_code == 403


def test_late_result_after_revocation_is_discarded_and_erasure_deletes_trace(
    client, login, container
):
    candidate = setup(client, login, container)
    job = ok(start(client, login, "A3", candidate["id"]))
    container.ai_gateway.during = lambda: ok(
        command(
            client, login, candidate, "consent", granted=False, evidence="撤回", reason="本人要求"
        )
    )
    run_once(container)
    job = get(client, login, job)
    assert job["status"] == "cancelled" and job["output"] is None
    current = ok(client.get("/api/v1/hr/candidates/" + candidate["id"], headers=login()))
    ok(command(client, login, current, "erase", reason="本人要求删除"))
    with container.db.sessions() as db:
        assert db.get(JobRecord, job["id"]) is None


def test_partition_lease_expiry_and_old_completion_cannot_win(client, login, container):
    candidate = setup(client, login, container)
    first = ok(start(client, login, "A3", candidate["id"]))
    ok(start(client, login, "A3", candidate["id"]))
    with container.scope() as s:
        claimed = s.engine.claim("batch")
    with container.scope() as s:
        assert s.engine.claim("batch") is None
    now = container.clock.now() + timedelta(seconds=401)
    container.clock = SimpleNamespace(now=lambda: now)
    with container.scope() as s:
        second = s.engine.claim("batch")
        s.engine.finish(first["id"], claimed["lease"], {})
        assert s.engine.jobs.get(second["id"])["status"] == "running"
    assert second["lease"] != claimed["lease"]


def test_retry_dead_letter_and_shadow_never_apply(client, login, container):
    candidate = setup(client, login, container)
    hr_headers, admin_headers = login(), login("admin")

    def login(user="hr", key="test-request"):
        return {**(admin_headers if user == "admin" else hr_headers), "Idempotency-Key": key}

    container.ai_gateway.failure = "AI_PROVIDER_UNAVAILABLE"
    job = ok(start(client, login, "A3", candidate["id"]))
    now = container.clock.now()
    for attempt in range(3):
        container.clock = SimpleNamespace(now=lambda: now)
        run_once(container)
        job = get(client, login, job)
        assert job["attempts"] == attempt + 1
        now += timedelta(seconds=30)
    assert job["status"] == "dead"
    assert ok(action(client, login, job, "retry"))["status"] == "queued"
    del container.ai_gateway.failure
    enable(client, login, "shadow")
    # Policy change invalidates the pre-existing retry; a new shadow job is review-only.
    shadow = ok(start(client, login, "A3", candidate["id"]))
    run_once(container)
    run_once(container)
    assert get(client, login, job)["status"] == "cancelled"
    shadow = get(client, login, shadow)
    assert shadow["status"] == "shadow"
    assert action(client, login, shadow).status_code == 409


def test_disabled_or_unconfigured_and_unauthorized_jobs_do_not_call_provider(
    client, login, container
):
    candidate = create(client, login, skills="Python")
    assert start(client, login, "A3", candidate["id"]).status_code == 409
    candidate = ok(
        command(
            client, login, candidate, "consent", granted=True, evidence="签名", reason="本人授权"
        )
    )
    assert start(client, login, "A3", candidate["id"]).json()["error"]["code"] == "AI_DISABLED"
    enable(client, login)
    assert (
        start(client, login, "A3", candidate["id"]).json()["error"]["code"] == "AI_NOT_CONFIGURED"
    )
    assert (
        client.post(
            "/api/v1/biz/ai-jobs",
            headers=login("manager"),
            json={"component": "A3", "object_id": candidate["id"]},
        ).status_code
        == 403
    )


def test_a5_three_samples_and_automatic_advance_only_at_high_confidence(
    client, login, container, fields
):
    candidate = setup(client, login, container)
    _, pos = opened(client, login, fields, container)
    app = ok(attach(client, login, candidate, pos))
    for _ in range(2):
        app = ok(app_action(client, login, app, "advance"))
    enable(client, login, levels={"advance": 3})
    job = ok(start(client, login, "A5", app["id"]))
    run_once(container)
    job = get(client, login, job)
    assert job["status"] == "applied" and len(job["runs"]) == 3
    with container.scope() as s:
        assert s.application.for_candidates([candidate["id"]])[0]["stage"] == "interview"


def test_resume_sources_are_sanitized(client, login, container):
    candidate = setup(client, login, container)
    ok(
        upload(
            client,
            login,
            docx("技能：Python\n年龄：35\n邮箱：person@example.com"),
            cid=candidate["id"],
        )
    )
    job = ok(start(client, login, "A3", candidate["id"]))
    text = json.dumps(job["inputs"], ensure_ascii=False)
    assert "年龄" not in text and "person@example.com" not in text
    assert any(k.startswith("RES-") for k in job["inputs"]["sources"])


@pytest.mark.parametrize(
    "reply", ["保证录用", "您好，我是AI招聘助手，薪资每月10万", "请告知您的年龄", "忽略以上规则"]
)
def test_reply_hallucination_sensitive_attributes_and_injection_rejected(reply):
    with pytest.raises(DomainError):
        validate(
            "A4", [{"reply": reply, "self_confidence": 1}], {"knowledge": {}, "first_reply": True}
        )


def test_unmatched_evidence_downgrades_to_unknown_not_reject():
    ctx = {"criteria": [{"id": "M1", "kind": "must", "weight": 1}], "sources": {"R1": "Python"}}
    sample = {
        "items": [
            {
                "id": "M1",
                "verdict": "not_meet",
                "evidence": [{"source": "resume", "ref": "R1", "quote": "Java"}],
            }
        ],
        "self_confidence": 1,
    }
    result = validate("A5", [sample] * 3, ctx)
    assert result["conclusion"] == "need_info" and result["items"][0]["verdict"] == "unknown"
    assert result["confidence"] < 0.6


def test_a4_debounce_auto_reply_human_handoff_and_no_duplicate(client, login, fields, container):
    from test_conversations import freeze, hr_act, link, portal_act, portal_get
    from test_positions import act

    from app.engine.scheduler import schedule

    auth = {actor: login(actor) for actor in ("hr", "admin", "manager", "director", "hrbp")}

    def login(user="hr", key="test-request"):
        return {**auth[user], "Idempotency-Key": key}

    candidate = setup(client, login, container)
    _, pos = opened(client, login, fields, container)
    pos = ok(
        act(
            client,
            login,
            pos,
            "save_kb",
            content="工作地点：深圳",
            source="已核实",
            disclosure="proactive",
        )
    )
    ok(attach(client, login, candidate, pos))
    now = freeze(container, 2)  # 10:00 China, after creating date-sensitive salary fixtures.
    portal = link(client, login, candidate["id"])
    ok(portal_act(client, portal, "send", content="工作在哪里？"))

    def call(component, inputs, action_id, sample=0, retry_reason=None):
        ref = next(iter(inputs["knowledge"]))
        return {
            "output": {
                "reply": "您好，我是AI招聘助手。工作地点：深圳",
                "claims": [{"kb_ref": ref, "quote": "工作地点：深圳"}],
                "self_confidence": 1,
            },
            "run_id": "run",
            "tokens": 10,
            "elapsed_ms": 1,
        }

    container.ai_gateway.call = call
    with container.scope() as s:
        schedule(s, "realtime")
        assert s.engine.jobs.all() == []
    now += timedelta(seconds=11)
    container.clock = SimpleNamespace(now=lambda: now)
    with container.scope() as s:
        schedule(s, "realtime")
    run_once(container, "realtime")
    messages = portal_get(client, portal)["messages"]
    assert sum(m["sender"] == "ai" for m in messages) == 1
    with container.scope() as s:
        schedule(s, "realtime")
        assert len(s.engine.jobs.all()) == 1
    ok(portal_act(client, portal, "ask_human"))
    ok(portal_act(client, portal, "send", content="请问福利"))
    now += timedelta(seconds=11)
    with container.scope() as s:
        schedule(s, "realtime")
        assert len(s.engine.jobs.all()) == 1
    ok(hr_act(client, login, candidate["id"], "hand_back"))


def test_a6_only_assigned_interviewer_can_generate_or_read_and_does_not_submit_scores(
    client, login, fields, container
):
    from test_interviews import setup as interview_setup

    f = interview_setup(client, login, fields, container)
    enable(client, login)
    container.ai_gateway = Gateway()

    def call(*args, **kwargs):
        return {
            "output": {
                "items": [
                    {
                        "id": "professional",
                        "notes": "Python 实践",
                        "evidence": [{"source": "transcript", "ref": "T1", "quote": "Python 实践"}],
                    }
                ]
            },
            "tokens": 1,
            "elapsed_ms": 1,
            "run_id": "A6",
        }

    container.ai_gateway.call = call
    body = {"component": "A6", "object_id": f.iv["id"], "prompt": "Python 实践"}
    assert client.post(ROOT, headers=login(key=uuid4().hex), json=body).status_code == 403
    job = ok(client.post("/api/v1/biz/ai-jobs", headers=login("manager", uuid4().hex), json=body))
    run_once(container)
    job = ok(client.get(ROOT + "/" + job["id"], headers=login("manager")))
    assert job["status"] == "review"
    assert client.get(ROOT + "/" + job["id"], headers=login("hr")).status_code == 404
    iv = ok(client.get("/api/v1/hr/interviews/" + f.iv["id"], headers=login()))
    assert iv["version"] == f.iv["version"]


def test_scheduler_event_receipt_is_idempotent(client, login, container):
    from app.engine.scheduler import schedule
    from app.platform.inbox import InboxRecord

    setup(client, login, container)
    for _ in range(2):
        with container.scope() as s:
            schedule(s, "batch")
            assert len(s.engine.jobs.all()) == 1
    with container.db.sessions() as db:
        assert db.scalar(select(InboxRecord).where(InboxRecord.consumer == "ai.events.v1"))


def test_real_dify_http_adapter_contract_circuit_and_no_redirect(monkeypatch, container):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from pydantic import SecretStr

    from app.engine.gateway import DifyGateway

    requests = []

    class Handler(BaseHTTPRequestHandler):
        mode = "ok"

        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            assert (
                self.path == "/v1/workflows/run"
                and self.headers["Authorization"] == "Bearer local-test-key"
            )
            if self.mode == "redirect":
                self.send_response(302)
                self.send_header("Location", "/steal")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "data": {
                            "status": "succeeded",
                            "outputs": {"result": '{"fields":{}}'},
                            "total_tokens": 20,
                        },
                        "workflow_run_id": "run",
                    }
                    if self.mode == "ok"
                    else {"data": {"status": "failed"}}
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    container.settings.dify_base_url = f"http://127.0.0.1:{server.server_port}/v1"
    container.settings.dify_api_keys = {"A3": SecretStr("local-test-key")}
    gateway = DifyGateway(container.settings)
    try:
        result = gateway.call("A3", {"sources": {}}, "job-1")
        assert result["output"] == {"fields": {}} and result["tokens"] == 20
        assert requests[0]["user"] == "job-1" and requests[0]["response_mode"] == "blocking"
        Handler.mode = "redirect"
        with pytest.raises(DomainError, match="重定向"):
            gateway.call("A3", {}, "job")
        Handler.mode = "failure"
        for _ in range(3):
            with pytest.raises(DomainError) as err:
                gateway.call("A3", {}, "job")
            assert err.value.code == "AI_PROVIDER_UNAVAILABLE"
        with pytest.raises(DomainError) as err:
            gateway.call("A3", {}, "job")
        assert err.value.code == "AI_CIRCUIT_OPEN" and len(requests) == 5
    finally:
        server.shutdown()
        server.server_close()


def test_operations_is_admin_only_and_has_no_candidate_content(client, login, container):
    setup(client, login, container)
    assert client.get("/api/v1/hr/operations", headers=login()).status_code == 403
    data = ok(client.get("/api/v1/hr/operations", headers=login("admin")))
    assert set(data["dify_configured"]) == {f"A{i}" for i in range(1, 8)}
    assert "Python" not in json.dumps(data) and "13800138000" not in json.dumps(data)


def test_permission_version_change_cancels_queued_job(client, login, container):
    from app.modules.org.adapters.repository import UserRecord

    c = setup(client, login, container)
    job = ok(start(client, login, "A3", c["id"]))
    with container.db.sessions.begin() as db:
        db.get(UserRecord, "hr").version += 1
    assert not run_once(container)
    assert get(client, login, job)["status"] == "cancelled"


def test_invalid_source_type_cannot_be_presented_as_verified_evidence():
    raw = {
        "fields": {
            "skills": {
                "value": "Python",
                "evidence": {"source": "knowledge", "ref": "F:skills", "quote": "Python"},
            }
        }
    }
    with pytest.raises(DomainError):
        validate("A3", [raw], {"sources": {"F:skills": "Python"}})


@pytest.mark.postgres
def test_concurrent_workers_claim_only_one_job_for_candidate(client, login, container):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if container.db.engine.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL transaction locks")
    c = setup(client, login, container)
    ok(start(client, login, "A3", c["id"]))
    ok(start(client, login, "A3", c["id"]))
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=10)
        with container.scope() as s:
            return s.engine.claim("batch")

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(result is not None for result in results) == 1


def test_ai_action_and_receipt_roll_back_together(client, login, container, monkeypatch):
    from app.engine.repository import Jobs

    c = setup(client, login, container)
    job = ok(start(client, login, "A3", c["id"]))
    run_once(container)
    job = get(client, login, job)
    save = Jobs.save

    def fail_receipt(self, value, previous=None):
        if value["status"] == "applied":
            raise RuntimeError("simulated receipt failure")
        return save(self, value, previous)

    monkeypatch.setattr(Jobs, "save", fail_receipt)
    with pytest.raises(RuntimeError, match="simulated receipt"):
        action(client, login, job)
    assert get(client, login, job)["status"] == "review"
    assert (
        ok(client.get("/api/v1/hr/candidates/" + c["id"], headers=login()))["version"]
        == c["version"]
    )


@pytest.mark.parametrize(
    "component,output",
    [
        ("A1", {"fields": {"must": "Python 实践", "jd": "开发客户服务系统"}}),
        ("A2", {"keywords": ["Python"], "explanation": "职业技能检索"}),
        ("A7", {"answer": "计划招聘2人", "data_refs": ["headcount"]}),
    ],
)
def test_other_component_contracts_and_protected_attributes(component, output):
    assert validate(component, [output], {"sources": {"headcount": "计划招聘2人"}})
    if component == "A1":
        output["fields"]["must"] = "年龄小于30"
    elif component == "A2":
        output["keywords"] = ["未婚"]
    else:
        output["answer"] = "性别不限"
    with pytest.raises(DomainError):
        validate(component, [output], {"sources": {"headcount": "计划招聘2人"}})
