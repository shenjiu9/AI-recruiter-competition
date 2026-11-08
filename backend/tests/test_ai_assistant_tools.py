"""Assistant tools: catalog consistency, look-ups with charts, direct changes with undo."""

import typing
from uuid import uuid4

import pytest
from test_ai_assistant import blocks, say
from test_ai_engine import enable
from test_ai_intent import Router, person
from test_candidates import attach, ok
from test_positions import opened

from app.engine.agent import Assistant, agent_rule_route
from app.engine.contracts import AgentIntent
from app.engine.tools import CATALOG, TOOLS


def test_every_tool_is_routable_and_has_a_handler():
    names = set(typing.get_args(AgentIntent))
    assert names == set(TOOLS)
    handled = {t.name for t in CATALOG if t.mode != "ai"}
    for name in handled - {"help", "none"}:
        assert callable(
            getattr(
                Assistant,
                {
                    "positions": "position_status",
                    "candidate": "candidate_status",
                    "candidates": "candidate_search",
                }.get(name, name),
                None,
            )
        ), name
    for t in CATALOG:
        if t.example and t.pattern:
            assert agent_rule_route(t.example).intent == t.name, t.example


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("客服的薪资带宽是多少", "salary"),
        ("给张三定薪月薪8000", "none"),
        ("张三最近说了什么", "conversation"),
        ("张三回复了吗", "conversation"),
        ("把张三设为重点候选人", "key"),
        ("取消张三的重点", "key"),
        ("给张三打个标签：沟通好", "tag"),
        ("接管张三的会话", "take_over"),
        ("把张三的会话交还给AI", "hand_back"),
        ("撤销张三的淘汰", "restore"),
        ("暂停客服专员的招聘", "pause"),
        ("恢复客服专员的招聘", "resume"),
        ("看看客服专员的招聘漏斗", "stats"),
        ("淘汰原因统计", "stats"),
        ("客服专员面试阶段有哪些人", "pipeline"),
        ("本周的面试安排", "interviews"),
        ("各部门编制还剩多少", "headcount"),
        ("编制申请审批到哪了", "requisitions"),
        ("有哪些决策卡要处理", "cards"),
        ("现在的自动化设置是什么", "automation"),
        ("为什么客服专员招得慢", "A7"),
    ],
)
def test_rules_route_new_tools(text, intent):
    assert agent_rule_route(text).intent == intent


def test_rules_split_two_requests_in_one_sentence():
    route = agent_rule_route("客服专员还差几个人，再看看张三到哪一步了")
    assert route.intent == "positions" and [s.intent for s in route.then] == ["candidate"]
    assert agent_rule_route("给张三发消息：你好，然后明天来面试").then == []


def setup(client, login, container, fields):
    container.ai_gateway = Router(a0=False)
    enable(client, login)
    _, pos = opened(client, login, fields, container)
    zhang = person(client, login, "张三")
    ok(attach(client, login, zhang, pos))
    return pos, zhang


def test_lookups_answer_with_charts(client, login, container, fields):
    pos, zhang = setup(client, login, container, fields)
    name = pos["name"]
    stats = ok(say(client, login, f"看看{name}的招聘漏斗"))
    assert stats["intent"] == "stats"
    funnel = blocks(stats, "funnel")[0]["items"]
    assert funnel[0] == {"label": "触达", "value": 1}
    assert len(blocks(stats, "trend")[0]["items"]) == 8
    pipeline = ok(say(client, login, f"{name}有哪些候选人"))
    assert pipeline["intent"] == "pipeline"
    assert blocks(pipeline, "list")[0]["items"][0]["title"] == "张三"
    progress = ok(say(client, login, f"{name}还差几个人"))
    bar = blocks(progress, "progress")[0]["items"][0]
    assert bar["total"] == pos["planned"] and bar["value"] == 0
    overview = ok(say(client, login, "今天有什么要处理"))
    assert blocks(overview, "progress")
    person_view = ok(say(client, login, "张三到哪一步了"))
    timeline = blocks(person_view, "timeline")[0]["items"]
    assert timeline[0]["title"] == "进入岗位" and timeline[-1]["state"] == "todo"
    chat = ok(say(client, login, "张三最近说了什么"))
    assert chat["intent"] == "conversation" and blocks(chat, "chat")
    both = ok(say(client, login, f"{name}还差几个人，再看看张三到哪一步了"))
    assert both["steps"] == ["positions", "candidate"]
    assert blocks(both, "progress") and blocks(both, "profile")


def test_settings_lookups_keep_page_permissions(client, login, container, fields):
    setup(client, login, container, fields)
    headcount = ok(say(client, login, "各部门编制还剩多少"))
    assert headcount["intent"] == "headcount"
    assert "权限" in headcount["reply"] or blocks(headcount, "progress")
    auto = ok(say(client, login, "现在的自动化设置是什么"))
    assert auto["intent"] == "automation"
    assert "权限" in auto["reply"] or blocks(auto, "table")


def test_direct_changes_run_at_once_and_can_be_undone(client, login, container, fields):
    _, zhang = setup(client, login, container, fields)
    key = ok(say(client, login, "把张三设为重点候选人"))
    done = blocks(key, "done")[0]
    record = ok(client.get(f"/api/v1/hr/candidates/{zhang['id']}", headers=login()))
    assert record["key_candidate"] is True
    undo = done["undo"]["action"]
    assert undo["kind"] == "command" and undo["target"] == "candidate"
    ok(
        client.post(
            f"/api/v1/hr/candidates/{undo['id']}/actions",
            headers=login(key=uuid4().hex),
            json=undo["body"],
        )
    )
    record = ok(client.get(f"/api/v1/hr/candidates/{zhang['id']}", headers=login()))
    assert record["key_candidate"] is False
    tag = ok(say(client, login, "给张三打个标签：沟通好"))
    assert blocks(tag, "done")
    record = ok(client.get(f"/api/v1/hr/candidates/{zhang['id']}", headers=login()))
    assert "沟通好" in record["tags"]
    take = ok(say(client, login, "接管张三的会话"))
    assert take["intent"] == "take_over" and blocks(take, "done")
    conv = ok(client.get(f"/api/v1/hr/candidates/{zhang['id']}/conversation", headers=login()))
    assert conv["mode"] == "hr"
    back = ok(say(client, login, "把张三的会话交还给AI"))
    assert blocks(back, "done")


def test_confirm_tools_only_propose(client, login, container, fields):
    pos, zhang = setup(client, login, container, fields)
    pause = ok(say(client, login, f"暂停{pos['name']}的招聘"))
    action = blocks(pause, "confirm")[0]["action"]
    assert action == {
        "kind": "command",
        "target": "position",
        "id": pos["id"],
        "body": {"action": "pause", "expected_version": pos["version"], "handling": "continue"},
    }
    still = ok(client.get(f"/api/v1/hr/positions/{pos['id']}", headers=login()))
    assert still["status"] == "open"
    nothing = ok(say(client, login, "撤销张三的淘汰"))
    assert nothing["intent"] == "restore" and not blocks(nothing, "confirm")


def test_model_plan_runs_several_tools_and_a_refusal_stops_it(client, login, container, fields):
    pos, _ = setup(client, login, container, fields)
    container.ai_gateway = Router(
        {
            "intent": "positions",
            "position": pos["name"],
            "then": [{"intent": "candidate", "candidate": "张三"}],
        }
    )
    result = ok(say(client, login, f"{pos['name']}进度和张三的情况"))
    assert result["router"] == "model" and result["steps"] == ["positions", "candidate"]
    container.ai_gateway = Router(
        {"intent": "none", "then": [{"intent": "key", "candidate": "张三"}]}
    )
    refused = ok(say(client, login, "把张三删了，再设为重点"))
    assert refused["intent"] == "none" and "steps" not in refused
