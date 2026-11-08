"""One synthetic record travels from requisition to joined, including A2 and A5.

Set LIVE_DIFY_ENV to a private .env path for the explicit paid-model variant.
Business writes always go to the disposable test database, never the live tenant.
Only the isolated test clock advances past the scheduled interview.
"""

import os
from datetime import timedelta
from types import SimpleNamespace

from test_ai_engine import Gateway, action, enable, get, start
from test_candidates import app_action, attach, command, docx, ok, upload
from test_conversations import hr_act, hr_get, link, portal_act
from test_feedback_matching import MatchingGateway
from test_hiring import act_hire, prepare
from test_interviews import DEFAULT_ROUND, feedback, finished
from test_positions import act, opened

from app.ai_worker import run_once
from app.engine.gateway import DifyGateway
from app.platform.settings import Settings


class LoopGateway(Gateway):
    def call(self, component, inputs, action_id, sample=0, **kwargs):
        if component == "A2":
            return MatchingGateway().call(component, inputs, action_id, **kwargs)
        return super().call(component, inputs, action_id, sample, **kwargs)


def test_requisition_resume_matching_interview_approval_handover_joined(
    client, login, fields, container
):
    live = os.environ.get("LIVE_DIFY_ENV")
    container.ai_gateway = (
        DifyGateway(Settings(_env_file=live, ai_timeout_seconds=120)) if live else LoopGateway()
    )
    enable(client, login, mode="manual")
    req, pos = opened(
        client,
        login,
        fields,
        container,
        title="合成闭环测试岗位",
        requirements="Python 后端开发实践",
    )
    assert req["status"] == "approved"
    pos = ok(act(client, login, pos, "save_interview_plan", rounds=[DEFAULT_ROUND]))
    c = ok(
        upload(
            client,
            login,
            docx(
                "姓名：合成闭环测试候选人\n邮箱：closed-loop@example.invalid\n技能：Python\n工作经历：使用 Python 开发后端服务并编写集成测试。"
            ),
        )
    )["candidate"]
    assert c["resumes"][0]["status"] == "ok"
    c = ok(
        command(
            client,
            login,
            c,
            "consent",
            granted=True,
            evidence="合成测试授权",
            reason="隔离闭环验证",
        )
    )

    def review(component, object_id, **extra):
        job = ok(start(client, login, component, object_id, **extra))
        assert run_once(container)
        job = get(client, login, job)
        assert job["status"] == "review", {
            "component": component,
            "status": job["status"],
            "error": job.get("error_code"),
        }
        return job

    extraction = review("A3", c["id"])
    assert ok(action(client, login, extraction))["status"] == "applied"
    c = ok(client.get("/api/v1/hr/candidates/" + c["id"], headers=login()))
    match = review("A2", pos["id"], candidate_ids=[c["id"]])
    assert match["output"]["matches"][0]["conclusion"] == "advance"
    assert ok(action(client, login, match))["status"] == "reviewed"
    app = ok(attach(client, login, c, pos))
    app = ok(app_action(client, login, app, "advance"))
    assert app["stage"] == "talking"
    portal = link(client, login, c["id"])
    ok(portal_act(client, portal, "send", content="合成测试：愿意了解岗位并参加面试。"))
    assert hr_get(client, login, c["id"])["messages"][-1]["sender"] == "candidate"
    ok(hr_act(client, login, c["id"], "take_over"))
    ok(hr_act(client, login, c["id"], "send", content="合成测试：收到，接下来安排面试。"))
    app = ok(app_action(client, login, app, "advance"))
    assert app["stage"] == "ai_eval"
    evaluation = review("A5", app["id"])
    assert evaluation["output"]["conclusion"] == "advance"
    assert ok(action(client, login, evaluation))["status"] == "applied"
    app = next(
        a
        for a in ok(client.get("/api/v1/hr/candidates/" + c["id"], headers=login()))["applications"]
        if a["id"] == app["id"]
    )
    assert app["stage"] == "interview"
    iv = ok(
        client.get("/api/v1/hr/interviews", headers=login(), params={"application_id": app["id"]})
    )["items"][0]
    f = SimpleNamespace(
        client=client,
        login=login,
        container=container,
        c=c,
        app=app,
        pos=pos,
        iv=iv,
        portal=portal,
        hid="HIRE-" + app["id"],
        auth={actor: login(actor) for actor in ("hr", "manager", "director", "hrbp", "salary_hrd")},
    )
    clock = container.clock
    finished(f)
    ok(feedback(f))
    container.clock = clock
    prepare(f)
    hire = ok(act_hire(f, "decide", "manager", decision="hire"))
    for node in hire["chain"]:
        hire = ok(act_hire(f, "approve", node["user_id"]))
    assert hire["status"] == "approved"
    ok(act_hire(f, "handover", evidence="合成测试移交核验"))
    ok(
        act_hire(
            f,
            "result",
            result="accepted",
            expected_start=(clock.now() + timedelta(days=20)).date().isoformat(),
        )
    )
    hire = ok(act_hire(f, "result", result="joined"))
    assert hire["status"] == "joined"
    with container.scope() as s:
        assert s.application.interview_context(app["id"])["outcome"] == "joined"
    assert ok(client.get("/api/v1/hr/positions/" + pos["id"], headers=login()))["hired"] == 1
