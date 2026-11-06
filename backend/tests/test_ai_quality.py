"""Quality regressions for the AI workflow: realistic model slips that used to fail a
whole job (paraphrased punctuation, one bad field, one malformed sample, invented
statistics) and the A7 insight context. Safety rules must still hold."""

import json
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from test_ai_engine import Gateway, enable, get, setup, start
from test_candidates import app_action, attach, command, create, ok
from test_positions import opened

from app.ai_worker import run_once
from app.engine.context import insight_sources
from app.engine.gateway import HINTS, DifyGateway, parse_output
from app.engine.validation import quote_matches, validate
from app.kernel.types import DomainError


def reasons(exc):
    return exc.value.details.get("reasons", [])


# --- Evidence matching -------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "使用 Python 开发后端服务, 使用 PostgreSQL 存储数据.",  # half-width punctuation
        "使用python开发后端服务",  # case and spacing
        "使用 Ｐｙｔｈｏｎ 开发",  # full-width letters
        "使用 Python 开发后端服务……存储数据",  # elided middle, pieces in order
    ],
)
def test_quote_matching_tolerates_formatting_not_content(quote):
    assert quote_matches(quote, "使用 Python 开发后端服务，使用 PostgreSQL 存储数据。")


@pytest.mark.parametrize(
    "quote",
    [
        "使用 Java 开发后端服务",  # different fact
        "存储数据……使用 Python",  # pieces out of order
        "使……据",  # trivially short pieces
        "，。",  # punctuation only
        "",
    ],
)
def test_quote_matching_still_rejects_fabrication(quote):
    assert not quote_matches(quote, "使用 Python 开发后端服务，使用 PostgreSQL 存储数据。")


# --- A5 evaluation -----------------------------------------------------------------

CRITERIA = {
    "criteria": [
        {"id": "M1", "text": "Python", "kind": "must", "weight": 1},
        {"id": "P1", "text": "PostgreSQL", "kind": "plus", "weight": 2},
    ],
    "sources": {"F:experience": "使用 Python 开发后端服务，使用 PostgreSQL 存储数据。"},
}


def item(id, verdict, *quotes):
    return {
        "id": id,
        "verdict": verdict,
        "evidence": [{"source": "profile", "ref": "F:experience", "quote": q} for q in quotes],
    }


def sample(m1="meet", p1="meet", conf=0.9):
    return {
        "items": [item("M1", m1, "使用 Python 开发后端服务"), item("P1", p1, "PostgreSQL")],
        "self_confidence": conf,
    }


def test_a5_one_malformed_sample_no_longer_fails_the_evaluation():
    result = validate("A5", [None, sample(), sample()], CRITERIA)
    assert result["conclusion"] == "advance"
    assert result["sample_conclusions"] == ["invalid", "advance", "advance"]
    assert result["confidence"] < validate("A5", [sample()] * 3, CRITERIA)["confidence"]


def test_a5_presents_majority_conclusion_not_first_sample():
    outlier = sample(m1="not_meet")
    result = validate("A5", [outlier, sample(), sample()], CRITERIA)
    assert result["conclusion"] == "advance"
    assert result["items"][0]["verdict"] == "meet"
    assert result["sample_conclusions"] == ["reject", "advance", "advance"]


def test_a5_keeps_matching_quotes_and_counts_the_bad_one():
    raw = sample()
    raw["items"][0]["evidence"].append(
        {"source": "profile", "ref": "F:experience", "quote": "十年 Go 经验"}
    )
    result = validate("A5", [raw] * 3, CRITERIA)
    assert result["items"][0]["verdict"] == "meet" and len(result["items"][0]["evidence"]) == 1
    assert result["invalid_evidence"] == 1 and result["conclusion"] == "advance"


def test_a5_all_samples_invalid_is_rejected():
    with pytest.raises(DomainError) as exc:
        validate("A5", [None, {"items": []}, {"bad": 1}], CRITERIA)
    assert reasons(exc) == ["evaluation_invalid"]


# --- A3 extraction / A6 feedback ---------------------------------------------------

SOURCES = {"RES-1:p1": "2019-2024 在深圳某科技公司担任后端工程师，负责支付系统。"}


def field(value, quote, ref="RES-1:p1", source="resume"):
    return {"value": value, "evidence": {"source": source, "ref": ref, "quote": quote}}


def test_a3_keeps_grounded_fields_and_reports_dropped_ones():
    raw = {
        "fields": {
            "title": field("后端工程师", "担任后端工程师"),
            "city": field("深圳", "在深圳某科技公司"),
            "company": field("腾讯", "腾讯"),  # not in the resume
            "skills": field("Java", "负责支付系统"),  # value not in its quote
        }
    }
    result = validate("A3", [raw], {"sources": SOURCES})
    assert set(result["fields"]) == {"title", "city"}
    assert result["dropped"] == [
        {"field": "company", "reason": "evidence_mismatch"},
        {"field": "skills", "reason": "value_not_in_quote"},
    ]


def test_a3_rejects_when_nothing_is_grounded_with_rule_codes():
    raw = {"fields": {"company": field("腾讯", "腾讯"), "age": field("30", "30")}}
    with pytest.raises(DomainError) as exc:
        validate("A3", [raw], {"sources": SOURCES})
    assert reasons(exc) == ["evidence_mismatch", "field_not_allowed"]


def test_a6_drops_only_ungrounded_items():
    sources = {"T1": "我用 Python 写过订单服务。", "T2": "我们用压测验证容量。"}
    raw = {
        "items": [
            {
                "id": "skills",
                "notes": "Python 订单服务",
                "evidence": [
                    {"source": "transcript", "ref": "T1", "quote": "用Python写过订单服务"}
                ],
            },
            {
                "id": "scale",
                "notes": "百万 QPS",
                "evidence": [{"source": "transcript", "ref": "T2", "quote": "百万 QPS"}],
            },
        ]
    }
    result = validate("A6", [raw], {"sources": sources})
    assert [i["id"] for i in result["items"]] == ["skills"]
    assert result["dropped"] == [{"id": "scale", "reason": "evidence_mismatch"}]


# --- A4 reply ----------------------------------------------------------------------

KB = {"knowledge": {"KB-1": "工作地点：深圳南山区，双休。"}, "first_reply": True}


def test_a4_accepts_neutral_connectives_and_punctuation_variants():
    reply = {
        "reply": "您好，我是AI招聘助手。关于您的问题：工作地点:深圳南山区。如有其他问题欢迎随时咨询！",
        "claims": [{"kb_ref": "KB-1", "quote": "工作地点:深圳南山区"}],
        "self_confidence": 0.9,
    }
    assert validate("A4", [reply], KB)["reply"] == reply["reply"]


@pytest.mark.parametrize(
    "text", ["您好，我是AI招聘助手。工作地点在深圳，薪资面议", "您好，我是AI招聘助手。双休，包三餐"]
)
def test_a4_still_rejects_unquoted_facts(text):
    reply = {
        "reply": text,
        "claims": [{"kb_ref": "KB-1", "quote": "双休"}],
        "self_confidence": 0.9,
    }
    with pytest.raises(DomainError) as exc:
        validate("A4", [reply], KB)
    assert reasons(exc) == ["ungrounded_reply"]


def test_a4_deferral_to_hr_always_flags_human_follow_up():
    # Seen live: the model deferred a salary question but left needs_human false.
    reply = {"reply": "关于您的问题，我会请招聘 HR 核实后回复您。", "self_confidence": 0.9}
    result = validate("A4", [reply], {**KB, "first_reply": False})
    assert result["needs_human"] is True and result["intents"] == ["ask_human"]


def test_a4_first_reply_still_requires_ai_identity():
    reply = {"reply": "您好", "self_confidence": 1}
    with pytest.raises(DomainError) as exc:
        validate("A4", [reply], KB)
    assert reasons(exc) == ["ai_identity_required"]


# --- A7 insight --------------------------------------------------------------------

METRICS = {
    "total": 8,
    "active": 5,
    "stages": {
        "reach": 2,
        "talking": 1,
        "ai_eval": 2,
        "interview": 0,
        "manager_eval": 0,
        "hired": 0,
    },
    "reached": {
        "reach": 8,
        "talking": 5,
        "ai_eval": 4,
        "interview": 1,
        "manager_eval": 0,
        "hired": 0,
    },
    "outcomes": {"rejected": 2, "withdrawn": 1},
    "ended_at_stage": {
        "reach": 1,
        "talking": 0,
        "ai_eval": 2,
        "interview": 0,
        "manager_eval": 0,
        "hired": 0,
    },
    "reasons": {"skills": 2},
    "sources": {"hr": 6, "candidate": 2},
    "idle_days": [1, 3, 9, 10, 12],
    "stale": {
        "reach": 1,
        "talking": 0,
        "ai_eval": 2,
        "interview": 0,
        "manager_eval": 0,
        "hired": 0,
    },
    "stale_days": 7,
    "today": "2026-11-06",
}
POSITION = {"planned": 2, "hired": 0, "fields": {"expectedOnboard": "2026-12-01"}}


def test_a7_sources_are_labelled_chinese_aggregates():
    sources = insight_sources(POSITION, METRICS)
    assert sources["headcount"] == "计划招聘 2 人，已录用 0 人，剩余名额 2 人。"
    assert "沟通中 1 人" in sources["funnel"] and "ai_eval" not in json.dumps(sources)
    assert "触达→沟通中 62.5%" in sources["conversion"]
    assert "AI 评估→面试 25%" in sources["conversion"]
    assert "面试→用人经理评估 0%" in sources["conversion"]
    assert "淘汰 2 人" in sources["outcomes"] and "候选人退出 1 人" in sources["outcomes"]
    assert sources["reject_reasons"] == "淘汰原因分布：技能不匹配 2 人。"
    assert "中位数 9 天" in sources["aging"] and "AI 评估 2 人" in sources["aging"]
    assert sources["timeline"] == "期望到岗日期 2026-12-01，距今还有 25 天。"


def test_a7_sources_handle_empty_position_and_past_deadline():
    empty = {
        **METRICS,
        "total": 0,
        "active": 0,
        "stages": dict.fromkeys(METRICS["stages"], 0),
        "reached": dict.fromkeys(METRICS["reached"], 0),
        "outcomes": {},
        "reasons": {},
        "sources": {},
        "idle_days": [],
        "stale": dict.fromkeys(METRICS["stale"], 0),
    }
    sources = insight_sources({**POSITION, "fields": {"expectedOnboard": "2026-11-01"}}, empty)
    assert set(sources) == {"headcount", "funnel", "timeline"}
    assert "各阶段在途人数：无" in sources["funnel"]
    assert sources["timeline"] == "期望到岗日期 2026-11-01，已超过 5 天。"


A7_CTX = {"prompt": "当前进度如何？", "sources": insight_sources(POSITION, METRICS)}


def test_a7_grounded_answer_passes_and_cites_data():
    out = {
        "answer": "进度偏慢：计划招聘 2 人，已录用 0 人。AI 评估→面试 25%，是主要瓶颈。",
        "data_refs": ["headcount", "conversion", "conversion", "aging"],
        "suggestions": ["优先跟进停留 7 天及以上的 AI 评估候选人"],
    }
    result = validate("A7", [out], A7_CTX)
    assert result["data_refs"] == ["headcount", "conversion", "aging"]
    assert result["cited"]["headcount"] == A7_CTX["sources"]["headcount"]


@pytest.mark.parametrize(
    "answer",
    [
        "预计还需 3 周完成招聘。",  # invented forecast
        "AI 评估→面试 33%，转化偏低。",  # wrong rate
        "淘汰 7 人，主要因技能不匹配。",  # "7" exists only as days, not people
    ],
)
def test_a7_invented_numbers_are_rejected(answer):
    out = {"answer": answer, "data_refs": ["headcount"]}
    with pytest.raises(DomainError) as exc:
        validate("A7", [out], A7_CTX)
    assert reasons(exc) == ["ungrounded_number"]


def test_a7_allows_figures_from_position_fields_and_question():
    ctx = {**A7_CTX, "prompt": "Q4 进度如何？", "position": {"level": "P5", "title": "后端"}}
    out = {"answer": "P5 后端岗位 Q4 计划招聘 2 人。", "data_refs": ["headcount"]}
    assert validate("A7", [out], ctx)["answer"] == out["answer"]


def test_a7_figures_from_uncited_sources_are_added_to_citations():
    # Seen live: correct figures, but the model listed only some keys in data_refs.
    out = {
        "answer": "计划招聘 2 人，AI 评估→面试 25%。",
        "data_refs": ["headcount"],
        "suggestions": ["距期望到岗还有 25 天，HR 添加 6 人，需加快"],
    }
    result = validate("A7", [out], A7_CTX)
    assert result["data_refs"][0] == "headcount"
    assert {"conversion", "timeline", "channels"} <= set(result["cited"])


def test_a7_reference_and_safety_rules():
    with pytest.raises(DomainError) as exc:
        validate("A7", [{"answer": "进度正常", "data_refs": ["salary"]}], A7_CTX)
    assert reasons(exc) == ["data_reference_invalid"]
    with pytest.raises(DomainError) as exc:
        validate("A7", [{"answer": "  ", "data_refs": ["headcount"]}], A7_CTX)
    assert reasons(exc) == ["answer_required"]
    with pytest.raises(DomainError) as exc:
        validate("A7", [{"answer": "建议优先未婚候选人", "data_refs": ["headcount"]}], A7_CTX)
    assert reasons(exc) == ["protected_attribute"]


def test_a7_job_uses_pipeline_metrics_without_candidate_identity(client, login, fields, container):
    container.ai_gateway = Gateway()
    enable(client, login, mode="manual")
    _, pos = opened(client, login, fields, container)
    names = ["甲候选人", "乙候选人", "丙候选人"]
    apps = []
    for name in names:
        c = create(client, login, name=name, skills="Python")
        ok(command(client, login, c, "consent", granted=True, reason="授权", evidence="签名"))
        apps.append(ok(attach(client, login, c, pos)))
    ok(app_action(client, login, apps[0], "advance"))
    ok(app_action(client, login, apps[1], "reject", reason="技能不符", reason_code="skills"))
    seen = []

    def call(component, inputs, action_id, sample=0, retry_reason=None):
        seen.append((inputs, retry_reason))
        answer = (
            "计划招聘 2 人，已录用 0 人；累计应聘 3 人，当前在途 2 人。"
            if retry_reason
            else "计划招聘 2 人，预计 6 周内完成。"
        )
        return {
            "output": {"answer": answer, "data_refs": ["headcount", "funnel"], "suggestions": []},
            "run_id": str(len(seen)),
            "tokens": 5,
            "elapsed_ms": 1,
        }

    container.ai_gateway.call = call
    job = ok(start(client, login, "A7", pos["id"]))
    run_once(container)
    job = get(client, login, job)
    inputs = seen[0][0]
    text = json.dumps(inputs, ensure_ascii=False)
    assert not any(name in text for name in names)
    assert inputs["prompt"].startswith("请总结该岗位当前招聘进度")
    assert "累计应聘 3 人，当前在途 2 人" in inputs["sources"]["funnel"]
    assert "淘汰原因分布：技能不匹配 1 人" in inputs["sources"]["reject_reasons"]
    assert "触达→沟通中" in inputs["sources"]["conversion"]
    # First answer invented "6 周"; the bounded rewrite fixed it with the rule code.
    assert [r for _, r in seen] == [None, ["ungrounded_number"]]
    assert job["status"] == "review" and job["runs"][1]["kind"] == "rewrite"
    assert job["output"]["cited"]["funnel"] == inputs["sources"]["funnel"]


def test_a7_context_is_stable_within_a_day(client, login, fields, container):
    container.ai_gateway = Gateway()
    enable(client, login, mode="manual")
    _, pos = opened(client, login, fields, container)
    c = create(client, login, skills="Python")
    ok(attach(client, login, c, pos))
    job = ok(start(client, login, "A7", pos["id"]))
    started = container.clock.now()
    later = started.replace(hour=23, minute=59, second=59)
    clock, container.clock = container.clock, SimpleNamespace(now=lambda: later)
    with container.scope() as s:
        claimed = s.engine.claim("batch")
    assert claimed and claimed["id"] == job["id"]  # idle days unchanged: not cancelled
    container.clock = SimpleNamespace(now=lambda: later + timedelta(days=8))
    with container.scope() as s:
        job = s.engine.jobs.get(job["id"])
        s.engine.finish(job["id"], job["lease"], {"answer": "x", "data_refs": ["headcount"]})
        assert s.engine.jobs.get(job["id"])["error_code"] == "AI_CONTEXT_CHANGED"
    container.clock = clock


# --- Rewrites for every component --------------------------------------------------


def test_a3_rewrite_receives_rule_codes_and_recovers(client, login, container):
    candidate = setup(client, login, container)
    calls = []

    def call(component, inputs, action_id, sample=0, retry_reason=None):
        calls.append(retry_reason)
        quote = "Python" if retry_reason else "Rust"
        return {
            "output": {
                "fields": {
                    "skills": {
                        "value": quote,
                        "evidence": {"source": "profile", "ref": "F:skills", "quote": quote},
                    }
                }
            },
            "run_id": "r",
            "tokens": 1,
            "elapsed_ms": 1,
        }

    container.ai_gateway.call = call
    job = ok(start(client, login, "A3", candidate["id"]))
    run_once(container)
    job = get(client, login, job)
    assert calls == [None, ["evidence_mismatch"]]
    assert job["status"] == "review" and job["output"]["fields"]["skills"]["value"] == "Python"


def test_a5_worker_tolerates_one_unparseable_sample(client, login, fields, container):
    candidate = setup(client, login, container)
    _, pos = opened(client, login, fields, container)
    a = ok(attach(client, login, candidate, pos))
    a = ok(app_action(client, login, a, "advance"))
    a = ok(app_action(client, login, a, "advance"))
    assert a["stage"] == "ai_eval"
    fake = Gateway()
    count = []

    def call(component, inputs, action_id, sample=0, retry_reason=None):
        count.append(sample)
        if sample == 1:
            raise DomainError("AI_OUTPUT_REJECTED", "bad json", 422, {"reasons": ["json_invalid"]})
        return Gateway.call(fake, component, inputs, action_id, sample)

    container.ai_gateway.call = call
    job = ok(start(client, login, "A5", a["id"]))
    run_once(container)
    job = get(client, login, job)
    assert count == [0, 1, 2] and job["status"] in {"review", "applied"}
    assert job["output"]["sample_conclusions"][1] == "invalid"
    assert job["runs"][1] == {"kind": "invalid", "reasons": ["json_invalid"]}


# --- Gateway -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        '{"fields": {}}',
        '```json\n{"fields": {}}\n```',
        '以下是结果：{"fields": {}}',
    ],
)
def test_gateway_extracts_json_object_from_common_wrappers(text):
    assert parse_output(text) == {"fields": {}}


def test_gateway_hints_and_malformed_output_do_not_trip_breaker(container):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"data": {"status": "succeeded", "outputs": {"result": "抱歉，我无法回答"}}}
                ).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    container.settings.dify_base_url = f"http://127.0.0.1:{server.server_port}/v1"
    container.settings.dify_api_keys = {"A7": SecretStr("k")}
    gateway = DifyGateway(container.settings)
    try:
        for _ in range(4):
            with pytest.raises(DomainError) as exc:
                gateway.call("A7", {}, "job", retry_reason=["ungrounded_number"])
            assert exc.value.code == "AI_OUTPUT_REJECTED" and reasons(exc) == ["json_invalid"]
        assert len(requests) == 4  # breaker never opened
        sent = json.loads(requests[0]["inputs"]["retry_reason"])
        assert sent == [{"code": "ungrounded_number", "hint": HINTS["ungrounded_number"]}]
    finally:
        server.shutdown()
        server.server_close()


def test_every_rule_code_has_a_hint():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    code = (root / "engine/validation.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'"([a-z_]+)"', " ".join(re.findall(r"reject\([^)]*\)", code))))
    codes |= set(re.findall(r'reason = "([a-z_]+)"', code))
    codes |= set(re.findall(r'"reason": "([a-z_]+)"', code))
    codes |= set(re.findall(r'reasons\.append\("([a-z_]+)"\)', code))
    codes -= {"reason"}
    assert codes and codes <= set(HINTS), codes - set(HINTS)


def test_generated_workflows_match_generator_and_routing():
    from pathlib import Path

    from scripts.generate_dify_workflows import TASKS, workflow

    root = Path(__file__).resolve().parents[2] / "deploy/dify"
    routing = json.loads((root / "model-routing.json").read_text(encoding="utf-8"))
    for component in TASKS:
        on_disk = json.loads((root / "workflows" / (component + ".yml")).read_text("utf-8"))
        assert on_disk == workflow(component), component + " DSL is stale; re-run the generator"
        params = on_disk["workflow"]["graph"]["nodes"][1]["data"]["model"]["completion_params"]
        assert params["temperature"] == routing[component]["temperature"]
    assert routing["A5"]["temperature"] > routing["A3"]["temperature"]
    system = workflow("A7")["workflow"]["graph"]["nodes"][1]["data"]["prompt_template"][0]["text"]
    assert "上次校验结果" in system and "hint" in system
