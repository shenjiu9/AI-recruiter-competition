"""Natural-language entry: one sentence becomes a permission-checked AI job."""

from uuid import uuid4

import pytest
from test_ai_engine import Gateway, enable
from test_candidates import app_action, attach, command, create, ok
from test_positions import opened

from app.engine.contracts import Route
from app.engine.intent import grounded, match_candidates, match_positions, rule_route
from app.kernel.types import DomainError

ASK = "/api/v1/hr/ai-intents"


class Router(Gateway):
    """Test gateway whose A0 router answers with a fixed route."""

    def __init__(self, route=None, a0=True):
        self.route, self.a0 = route, a0
        self.routed = []

    def configured(self, component):
        return self.a0 if component == "A0" else True

    def call(self, component, inputs, action_id, sample=0, retry_reason=None):
        if component == "A0":
            self.routed.append(inputs["text"])
            if isinstance(self.route, Exception):
                raise self.route
            return {"output": self.route, "run_id": "r", "tokens": 1, "elapsed_ms": 1}
        return super().call(component, inputs, action_id, sample, retry_reason)


def ask(client, login, text, user="hr"):
    return client.post(ASK, headers=login(user, uuid4().hex), json={"text": text})


def person(client, login, name, consent=True):
    c = create(client, login, name=name, skills="Python")
    if consent:
        c = ok(
            command(
                client, login, c, "consent", granted=True, evidence="本人签名", reason="招聘评估"
            )
        )
    return c


@pytest.mark.parametrize(
    ("text", "component"),
    [
        ("白班客服还差几个人", "A7"),
        ("客服专员招聘进度怎么样", "A7"),
        ("帮客服专员写一版JD", "A1"),
        ("给客服专员出一份人才搜索关键词", "A2"),
        ("提取张三的简历信息", "A3"),
        ("帮我回复张三的消息", "A4"),
        ("评估一下张三是否符合要求", "A5"),
        ("整理张三的面试记录：沟通清晰\n做过客服", "A6"),
        ("今天天气不错", "none"),
    ],
)
def test_rules_route_common_sentences(text, component):
    assert rule_route(text).component == component


def test_rules_keep_transcript_after_colon():
    assert rule_route("整理张三的面试记录：沟通清晰\n做过客服").transcript == "沟通清晰\n做过客服"


def test_model_mentions_must_be_copied_from_the_sentence():
    route = Route(component="A5", candidate="李四", position="客服专员", transcript="编造的记录")
    clean = grounded(route, "评估一下客服专员岗位的张三")
    assert clean.candidate == "" and clean.transcript == "" and clean.position == "客服专员"


def test_entity_matching_prefers_exact_and_longest_names():
    positions = [{"id": "P1", "name": "白班客服专员"}, {"id": "P2", "name": "夜班客服专员"}]
    assert [p["id"] for p in match_positions(positions, "白班客服还差几个人", "")] == ["P1"]
    assert len(match_positions(positions, "客服的进度", "")) == 2
    people = [{"id": "C1", "name": "张三"}, {"id": "C2", "name": "张三丰"}]
    assert [c["id"] for c in match_candidates(people, "评估张三丰", "")] == ["C2"]


def test_question_about_a_position_starts_a7_with_the_sentence_as_question(
    client, login, container, fields
):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    result = ok(ask(client, login, "客服专员还差几个人？"))
    assert result["status"] == "started" and result["component"] == "A7"
    assert result["router"] == "rules"
    assert result["job"]["object_id"] == pos["id"]
    assert result["job"]["inputs"]["prompt"] == "客服专员还差几个人？"
    assert result["job"]["status"] == "queued"


def test_model_route_used_and_hallucinated_name_cannot_pick_a_record(
    client, login, container, fields
):
    enable(client, login)
    zhang = person(client, login, "张三")
    person(client, login, "李四")
    container.ai_gateway = Router({"component": "A3", "candidate": "李四", "reason": "提取"})
    result = ok(ask(client, login, "把张三简历里的信息整理进档案 13800138000"))
    assert container.ai_gateway.routed == ["把张三简历里的信息整理进档案 [已脱敏]"]
    # The model said 李四, but 李四 is not in the sentence; 张三 is.
    assert result["router"] == "model" and result["status"] == "started"
    assert result["job"]["object_id"] == zhang["id"] and result["job"]["component"] == "A3"


def test_router_failure_falls_back_to_rules(client, login, container):
    enable(client, login)
    zhang = person(client, login, "张三")
    container.ai_gateway = Router(DomainError("AI_PROVIDER_UNAVAILABLE", "down", 503))
    result = ok(ask(client, login, "提取张三的简历信息"))
    assert result["router"] == "rules" and result["job"]["object_id"] == zhang["id"]
    container.ai_gateway = Router({"component": "A9"})  # Schema-invalid router output.
    assert ok(ask(client, login, "提取张三的简历信息"))["router"] == "rules"


def test_ambiguous_or_missing_target_offers_choices(client, login, container):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    a = person(client, login, "张三")
    b = person(client, login, "张三")
    person(client, login, "王五", consent=False)
    result = ok(ask(client, login, "提取张三的简历信息"))
    assert result["status"] == "choose" and {o["id"] for o in result["options"]} == {
        a["id"],
        b["id"],
    }
    result = ok(ask(client, login, "帮我提取简历字段"))
    assert result["status"] == "choose"
    assert "王五" not in {o["label"] for o in result["options"]}  # Not consented.


def test_engine_checks_still_apply(client, login, container):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    person(client, login, "王五", consent=False)
    result = ok(ask(client, login, "提取王五的简历信息"))
    assert result["status"] == "blocked" and result["error_code"] == "CONSENT_REQUIRED"
    assert ok(client.get("/api/v1/hr/ai-jobs", headers=login()))["total"] == 0


def test_disabled_component_is_reported_not_started(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    old = ok(client.get("/api/v1/hr/automation-live", headers=login("admin")))
    ok(
        client.post(
            "/api/v1/hr/automation-live",
            headers=login("admin", uuid4().hex),
            json={
                "expected_version": old["version"],
                "mode": "normal",
                "components": {f"A{i}": i != 7 for i in range(1, 8)},
            },
        )
    )
    result = ok(ask(client, login, "客服专员进度怎么样"))
    assert result["status"] == "blocked" and result["error_code"] == "AI_DISABLED"


def test_evaluation_needs_ai_eval_stage(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    app = ok(attach(client, login, zhang, pos))
    result = ok(ask(client, login, "评估一下张三"))
    assert result["status"] == "blocked" and "AI 评估" in result["message"]
    for _ in range(2):
        app = ok(app_action(client, login, app, "advance"))
    result = ok(ask(client, login, "评估一下张三是否符合客服专员"))
    assert result["status"] == "started" and result["job"]["object_id"] == app["id"]
    # A bare name with a position-type keyword is still read as an evaluation.
    assert ok(ask(client, login, "张三怎么样"))["component"] == "A5"


def test_unsupported_sentence_and_non_hr(client, login, container):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    result = ok(ask(client, login, "今天天气不错"))
    assert result["status"] == "unsupported" and result["examples"]
    assert ask(client, login, "客服专员进度", user="manager").status_code == 403


def test_idempotent_replay_does_not_start_twice(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    opened(client, login, fields, container)
    headers = login(key="ask-once")
    first = ok(client.post(ASK, headers=headers, json={"text": "客服专员进度怎么样"}))
    second = ok(client.post(ASK, headers=headers, json={"text": "客服专员进度怎么样"}))
    assert first["job_id"] == second["job_id"]
    assert ok(client.get("/api/v1/hr/ai-jobs", headers=login()))["total"] == 1
