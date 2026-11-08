"""HR assistant chat: answers from records, reviewed AI jobs, confirm-only business actions."""

from uuid import uuid4

import pytest
from test_ai_engine import enable
from test_ai_intent import Router, person
from test_candidates import attach, ok
from test_positions import opened

from app.engine.agent import agent_rule_route, grounded, message_content, to_agent_route
from app.engine.contracts import AgentRoute

URL = "/api/v1/hr/assistant"


def say(client, login, text, user="hr", **focus):
    return client.post(URL, headers=login(user, uuid4().hex), json={"text": text, "focus": focus})


def blocks(result, kind):
    return [b for b in result["blocks"] if b["type"] == kind]


def execute(client, login, action, reason="在 AI 助手中确认"):
    """What the browser does after the HR presses confirm: call the existing endpoint."""
    if action["kind"] == "attach":
        return client.post(
            "/api/v1/hr/applications",
            headers=login(key=uuid4().hex),
            json={
                "candidate_id": action["candidate_id"],
                "position_id": action["position_id"],
                "reason": reason,
            },
        )
    if action["kind"] in {"advance", "reject"}:
        body = {"action": action["kind"], "expected_version": action["expected_version"]}
        body |= (
            {"target_stage": action["target_stage"], "reason": reason}
            if action["kind"] == "advance"
            else {"reason": reason, "reason_code": "skills"}
        )
        return client.post(
            f"/api/v1/hr/applications/{action['application_id']}/actions",
            headers=login(key=uuid4().hex),
            json=body,
        )
    raise AssertionError(action["kind"])


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("今天有什么要处理", "overview"),
        ("给客服专员匹配简历", "A2"),
        ("从人才库里为客服专员做简历匹配", "A2"),
        ("白班客服还差几个人", "positions"),
        ("客服专员招聘进度怎么样", "positions"),
        ("分析客服专员的招聘瓶颈", "A7"),
        ("帮客服专员写一版JD", "A1"),
        ("给客服专员出一份人才搜索关键词", "A2"),
        ("把张三简历里的信息整理进档案", "A3"),
        ("帮我回复张三的消息", "A4"),
        ("评估一下张三是否符合要求", "A5"),
        ("整理张三的面试记录：沟通清晰", "A6"),
        ("张三到哪一步了", "candidate"),
        ("找会Python的候选人", "candidates"),
        ("最近的面试安排", "interviews"),
        ("录用进展", "hires"),
        ("待我复核的AI结果", "reviews"),
        ("招聘需求审批到哪了", "requisitions"),
        ("把张三加到客服专员岗位", "attach"),
        ("推进张三", "advance"),
        ("给张三安排面试", "advance"),
        ("淘汰张三", "reject"),
        ("给张三发消息：明天10点电话沟通", "message"),
        ("你能做什么", "help"),
        ("今天天气不错", "none"),
    ],
)
def test_rules_route_everyday_sentences(text, intent):
    assert agent_rule_route(text).intent == intent


def test_message_words_come_from_the_sentence():
    assert message_content("给张三发消息：明天10点电话沟通") == "明天10点电话沟通"
    assert message_content("跟张三说一声明天不用来了") == "明天不用来了"


def test_model_mentions_are_grounded_and_old_router_schema_still_works():
    route = AgentRoute(intent="message", candidate="李四", content="编造的话")
    clean = grounded(route, "给张三发消息：你好")
    assert clean.candidate == "" and clean.content == ""
    old = to_agent_route({"component": "A3", "candidate": "张三", "reason": "提取"})
    assert old.intent == "A3" and old.candidate == "张三"


def test_overview_and_help_answer_without_model(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    opened(client, login, fields, container)
    result = ok(say(client, login, "今天有什么要处理"))
    assert result["intent"] == "overview" and result["router"] == "rules"
    metrics = {m["label"]: m["value"] for m in blocks(result, "metrics")[0]["items"]}
    assert metrics["在招岗位"] == 1 and metrics["还差人数"] >= 1
    help_ = ok(say(client, login, "你能做什么"))
    assert help_["intent"] == "help" and blocks(help_, "list")


def test_full_chat_loop_proposes_and_existing_endpoints_execute(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")

    # Attach: the assistant only proposes; nothing changes until the HR confirms.
    proposal = ok(say(client, login, f"把张三加到{pos['name']}岗位"))
    confirm = blocks(proposal, "confirm")[0]
    assert confirm["action"] == {
        "kind": "attach",
        "candidate_id": zhang["id"],
        "position_id": pos["id"],
    }
    status = ok(say(client, login, "张三到哪一步了"))
    assert "没有在途应聘" in status["reply"]
    app = ok(execute(client, login, confirm["action"]))
    assert app["stage"] == "reach"

    # Pronoun follow-up uses the focus from the previous turn.
    status = ok(say(client, login, "张三到哪一步了"))
    assert status["focus"]["candidate_id"] == zhang["id"] and "触达" in status["reply"]
    for expected in ("talking", "ai_eval"):
        step = ok(say(client, login, "推进他", candidate_id=zhang["id"]))
        action = blocks(step, "confirm")[0]["action"]
        assert action["target_stage"] == expected
        app = ok(execute(client, login, action))
        assert app["stage"] == expected

    # A stale confirmation is refused by the existing optimistic lock.
    stale = blocks(ok(say(client, login, "推进张三")), "confirm")[0]["action"]
    ok(execute(client, login, stale))
    assert execute(client, login, stale).status_code == 409

    # AI evaluation runs as a reviewed job and is returned for the chat to follow.
    evaluation = ok(say(client, login, "评估一下张三"))
    # 张三 is already in interview now, so the existing planner explains why it is blocked.
    assert evaluation["intent"] == "A5" and "AI 评估" in evaluation["reply"]

    # Position status is read straight from the records.
    progress = ok(say(client, login, f"{pos['name']}还差几个人"))
    assert progress["intent"] == "positions"
    assert progress["focus"]["position_id"] == pos["id"]
    funnel = {f["label"]: f["value"] for f in blocks(progress, "funnel")[0]["items"]}
    assert funnel["面试"] == 1

    # Rejection is proposed as a danger card and executed through the existing command.
    reject = blocks(ok(say(client, login, "淘汰张三")), "confirm")[0]
    assert reject["danger"] and reject["action"]["kind"] == "reject"
    assert ok(execute(client, login, reject["action"]))["outcome"] == "rejected"


def test_ai_task_from_chat_returns_job_block(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    app = ok(attach(client, login, zhang, pos))
    for stage in ("talking", "ai_eval"):
        app = ok(
            execute(
                client,
                login,
                {
                    "kind": "advance",
                    "application_id": app["id"],
                    "expected_version": app["version"],
                    "target_stage": stage,
                },
            )
        )
    result = ok(say(client, login, "评估一下张三"))
    job = blocks(result, "job")[0]["job"]
    assert job["component"] == "A5" and job["object_id"] == app["id"]
    assert job["status"] == "queued"
    reviews = ok(say(client, login, "待我复核的AI结果"))
    assert reviews["intent"] == "reviews"
    assert blocks(reviews, "list")[0]["items"][0]["job_id"] == job["id"]


def test_message_proposal_needs_content_consent_and_application(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    person(client, login, "王五", consent=False)
    assert not blocks(ok(say(client, login, "给张三发消息")), "confirm")
    assert "授权" in ok(say(client, login, "给王五发消息：你好"))["reply"]
    assert "在途应聘" in ok(say(client, login, "给张三发消息：你好"))["reply"]
    ok(attach(client, login, zhang, pos))
    # The phone number is kept: the words come from the original sentence, not the
    # redacted copy the router saw.
    card = blocks(ok(say(client, login, "给张三发消息：有问题打13800138000")), "confirm")[0]
    assert card["action"]["content"] == "有问题打13800138000"
    assert card["action"]["application_ids"]


def test_model_route_is_used_and_cannot_pick_a_name_not_in_the_sentence(
    client, login, container, fields
):
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    person(client, login, "李四")
    ok(attach(client, login, zhang, pos))
    container.ai_gateway = Router({"intent": "advance", "candidate": "李四", "reason": "推进"})
    result = ok(say(client, login, "把张三往下走一步"))
    assert result["router"] == "model" and result["intent"] == "advance"
    action = blocks(result, "confirm")[0]["action"]
    assert action["target_stage"] == "talking"
    assert container.ai_gateway.routed == ["把张三往下走一步"]
    # The legacy natural-language endpoint understands the new router schema too.
    container.ai_gateway = Router({"intent": "A3", "candidate": "张三", "reason": "提取"})
    legacy = ok(
        client.post(
            "/api/v1/hr/ai-intents",
            headers=login(key=uuid4().hex),
            json={"text": "提取张三的简历信息"},
        )
    )
    assert legacy["router"] == "model" and legacy["component"] == "A3"


def test_assistant_is_hr_only_and_never_writes(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    app = ok(attach(client, login, zhang, pos))
    assert say(client, login, "推进张三", user="manager").status_code == 403
    ok(say(client, login, "推进张三"))
    ok(say(client, login, "淘汰张三"))
    after = ok(client.get(f"/api/v1/hr/positions/{pos['id']}/applications", headers=login()))
    assert after[0]["version"] == app["version"] and after[0]["stage"] == "reach"
