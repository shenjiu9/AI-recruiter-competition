"""Live quality check of A1–A7 against the DeepSeek API directly, without Dify.

It sends exactly the system prompt, user template and completion parameters that
the generated Dify DSL would send, then runs the backend's real validation and
bounded rewrite. Synthetic data only, no business writes. Each call is paid.

    DEEPSEEK_API_KEY=... python scripts/eval_deepseek_direct.py --reps 3

The key is read from the environment and is never printed or written.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine.validation import validate  # noqa: E402
from app.kernel.types import DomainError  # noqa: E402
from scripts.generate_dify_workflows import workflow  # noqa: E402

try:  # current pipeline
    from app.ai_worker import generate
    from app.engine.gateway import hints, parse_output
except ImportError:  # older checkouts, for A/B comparison
    generate = None

    def hints(reasons):
        return reasons

    def parse_output(text):
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("structured output required")
        return value


try:
    from app.engine.context import insight_sources
except ImportError:
    insight_sources = None

POSITION = {
    "title": "Python 后端工程师",
    "series": "技术",
    "level": "P5",
    "city": "深圳",
    "duties": "负责招聘平台后端服务的设计、开发与测试，维护 PostgreSQL 数据模型。",
    "requirements": "3 年以上 Python 后端经验；熟悉 PostgreSQL；有接口自动化测试实践。",
}
RESUME = {
    "RES-1:p1": "2020.07-2024.06  深圳某科技有限公司  后端工程师",
    "RES-1:p2": "负责订单与支付服务开发（Python / FastAPI），使用 PostgreSQL 设计数据表，日均处理 50 万笔订单。",
    "RES-1:p3": "编写 pytest 接口自动化测试，覆盖率从 40% 提升到 85%。",
    "RES-1:p4": "教育经历：华南理工大学 计算机科学与技术 本科",
    "RES-1:p5": "证书：AWS Certified Developer – Associate",
}
METRICS = {
    "total": 18,
    "active": 11,
    "stages": {
        "reach": 4,
        "talking": 3,
        "ai_eval": 4,
        "interview": 0,
        "manager_eval": 0,
        "hired": 0,
    },
    "reached": {
        "reach": 18,
        "talking": 12,
        "ai_eval": 8,
        "interview": 2,
        "manager_eval": 0,
        "hired": 0,
    },
    "outcomes": {"rejected": 5, "withdrawn": 2},
    "ended_at_stage": {
        "reach": 2,
        "talking": 1,
        "ai_eval": 2,
        "interview": 2,
        "manager_eval": 0,
        "hired": 0,
    },
    "reasons": {"skills": 3, "experience": 2},
    "sources": {"hr": 15, "candidate": 3},
    "idle_days": [1, 2, 2, 3, 5, 8, 9, 11, 12, 14, 16],
    "stale": {
        "reach": 1,
        "talking": 1,
        "ai_eval": 4,
        "interview": 0,
        "manager_eval": 0,
        "hired": 0,
    },
    "stale_days": 7,
    "today": "2026-11-06",
}


def a7_sources():
    if insight_sources:
        return insight_sources(
            {"planned": 2, "hired": 0, "fields": {"expectedOnboard": "2026-12-15"}}, METRICS
        )
    # What the previous context builder sent for the same pipeline.
    counts = {"total": 18, "active": 11, "hired": 0, "stages": METRICS["stages"]}
    return {
        "position_counts": json.dumps(counts, ensure_ascii=False),
        "headcount": "计划2，已录用0",
    }


def cases():
    criteria = [
        {"id": "M1", "text": "3 年以上 Python 后端开发经验", "kind": "must", "weight": 1},
        {"id": "M2", "text": "熟悉 PostgreSQL 数据建模", "kind": "must", "weight": 1},
        {"id": "P1", "text": "有接口自动化测试实践", "kind": "plus", "weight": 3},
        {"id": "P2", "text": "有云服务认证", "kind": "plus", "weight": 1},
        {"id": "R1", "text": "频繁跳槽（一年内多次离职）", "kind": "redflag", "weight": 1},
    ]
    return {
        "A1": {"position": POSITION, "prompt": "生成简洁的职业要求和 JD"},
        "A2": {"position": POSITION},
        "A3": {"sources": RESUME, "profile": {}},
        "A4-kb": {
            "first_reply": True,
            "messages": [{"sender": "candidate", "content": "你好，请问工作地点在哪？几点上班？"}],
            "knowledge": {
                "KB-1": "工作地点：深圳市南山区科技园。",
                "KB-2": "工作时间：周一至周五 9:30-18:30，双休。",
            },
            "questions": [],
        },
        "A4-unknown": {
            "first_reply": False,
            "messages": [
                {"sender": "candidate", "content": "这个岗位的薪资范围是多少？有股票吗？"}
            ],
            "knowledge": {"KB-1": "工作地点：深圳市南山区科技园。"},
            "questions": [],
        },
        "A5-advance": {"position": POSITION, "criteria": criteria, "sources": RESUME},
        "A5-gap": {
            "position": POSITION,
            "criteria": criteria,
            "sources": {k: v for k, v in RESUME.items() if k != "RES-1:p2"},
        },
        "A6": {
            "position": POSITION,
            "sources": {
                "T1": "面试官：介绍一下你做过最复杂的服务。",
                "T2": "候选人：我负责订单服务，用 FastAPI 和 PostgreSQL，高峰每秒 800 个请求。",
                "T3": "候选人：慢查询主要靠加联合索引和拆分大事务解决。",
                "T4": "面试官：测试怎么做？候选人：pytest 写接口测试，CI 每次提交都跑。",
            },
        },
        "A7": {"position": POSITION, "prompt": "", "sources": a7_sources()},
    }


class DirectGateway:
    def __init__(self, key, log):
        self.key, self.log = key, log
        root = Path(__file__).resolve().parents[2]
        self.routing = json.loads((root / "deploy/dify/model-routing.json").read_text("utf-8"))

    def call(self, component, inputs, action_id, sample=0, retry_reason=None):
        flow = workflow(component)
        llm = flow["workflow"]["graph"]["nodes"][1]["data"]
        params = llm["model"]["completion_params"]
        user = (
            llm["prompt_template"][1]["text"]
            .replace("{{#start.context#}}", json.dumps(inputs, ensure_ascii=False))
            .replace("{{#start.sample#}}", str(sample))
            .replace(
                "{{#start.retry_reason#}}",
                json.dumps(hints(retry_reason or []), ensure_ascii=False),
            )
        )
        body = {
            "model": llm["model"]["name"],
            "messages": [
                {"role": "system", "content": llm["prompt_template"][0]["text"]},
                {"role": "user", "content": user},
            ],
            "temperature": params["temperature"],
            "max_tokens": params["max_tokens"],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
        }
        started = time.monotonic()
        for attempt in range(3):
            try:
                request = Request(
                    "https://api.deepseek.com/chat/completions",
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": "Bearer " + self.key,
                        "Content-Type": "application/json",
                    },
                )
                with urlopen(request, timeout=120) as response:
                    raw = json.loads(response.read())
                break
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == 2:
                    raise DomainError("AI_PROVIDER_UNAVAILABLE", type(exc).__name__, 503) from None
                time.sleep(3 * (attempt + 1))
        text = raw["choices"][0]["message"]["content"] or ""
        self.log.append({"component": component, "retry": retry_reason, "text": text[:3000]})
        try:
            output = parse_output(text)
        except (ValueError, TypeError):
            code = "AI_OUTPUT_REJECTED" if generate else "AI_PROVIDER_UNAVAILABLE"
            raise DomainError(code, "not json", 422, {"reasons": ["json_invalid"]}) from None
        return {
            "output": output,
            "run_id": raw.get("id", ""),
            "tokens": raw.get("usage", {}).get("total_tokens", 0),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }


def legacy_generate(gateway, job, runs):
    """The previous worker: A5 three samples, only A4 got one rewrite."""
    component, inputs = job["component"], job["inputs"]
    samples = []
    for sample in range(3 if component == "A5" else 1):
        result = gateway.call(component, inputs, job["id"], sample)
        samples.append(result.pop("output"))
        runs.append(result)
    try:
        return validate(component, samples, inputs)
    except (DomainError, ValueError, TypeError, KeyError) as rejected:
        if component != "A4":
            raise
        reasons = (
            rejected.details.get("reasons", [rejected.code])
            if isinstance(rejected, DomainError)
            else ["schema_invalid"]
        )
        result = gateway.call("A4", inputs, job["id"], retry_reason=reasons)
        runs.append({**result, "kind": "rewrite"})
        return validate("A4", [result.pop("output")], inputs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("Set DEEPSEEK_API_KEY")
    log, results = [], []
    gateway = DirectGateway(key, log)
    run = generate or legacy_generate
    for name, inputs in cases().items():
        if args.only and name not in args.only:
            continue
        component = name.split("-")[0]
        for rep in range(args.reps):
            runs, start = [], len(log)
            row = {"case": name, "rep": rep}
            try:
                output = run(gateway, {"component": component, "inputs": inputs, "id": name}, runs)
                row.update(status="passed", output=output)
            except DomainError as exc:
                row.update(status="failed", code=exc.code, reasons=exc.details.get("reasons"))
            except (ValueError, TypeError, KeyError) as exc:
                row.update(status="failed", code=type(exc).__name__)
            row.update(
                calls=len(log) - start,
                rewrites=sum(1 for r in runs if r.get("kind") == "rewrite"),
                raw=log[start:],
            )
            results.append(row)
            print(name, rep, row["status"], row.get("reasons") or "", flush=True)
    summary = Counter((r["case"], r["status"]) for r in results)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "summary": {f"{c}:{s}": n for (c, s), n in sorted(summary.items())},
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
