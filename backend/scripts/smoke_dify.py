"""Explicit live-model smoke test using synthetic data, with no business writes.

Run from the repository root. This sends up to 27 paid model requests; it is
intentionally excluded from CI. Reports contain metadata, never keys or prompts.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.engine.gateway import DifyGateway
from app.engine.validation import validate
from app.kernel.types import DomainError
from app.platform.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def contexts():
    position = {
        "title": "Python 后端工程师",
        "series": "技术",
        "level": "P5",
        "city": "深圳",
        "duties": "开发和测试 Python 后端服务",
        "requirements": "具备 Python 和 PostgreSQL 开发实践",
    }
    return {
        "A1": {"position": position, "prompt": "生成简洁的职业要求和 JD"},
        "A2": {"position": position},
        "A3": {"sources": {"F:skills": "Python；PostgreSQL"}},
        "A4": {
            "first_reply": True,
            "messages": [{"sender": "candidate", "content": "工作地点在哪里？"}],
            "knowledge": {"KB-demo": "工作地点：深圳"},
            "questions": [],
        },
        "A5": {
            "position": position,
            "criteria": [
                {"id": "M1", "text": "Python 开发实践", "kind": "must", "weight": 1},
                {"id": "P1", "text": "PostgreSQL 实践", "kind": "plus", "weight": 2},
            ],
            "sources": {"F:experience": "使用 Python 开发后端服务，使用 PostgreSQL 存储数据。"},
        },
        "A6": {
            "position": position,
            "sources": {"T1": "我使用 Python 开发后端服务，并通过集成测试验证接口。"},
        },
        "A7": {
            "position": position,
            "prompt": "说明当前招聘进度",
            "sources": {
                "headcount": "计划招聘 2 人，已录用 0 人，剩余名额 2 人。",
                "funnel": "累计应聘 5 人，当前在途 3 人。各阶段在途人数：触达 1 人，沟通中 1 人，AI 评估 1 人。",
                "conversion": "累计进入各阶段人数（含已结束）：触达 5 人，沟通中 3 人，AI 评估 1 人。阶段转化率：触达→沟通中 60%，沟通中→AI 评估 33.3%，AI 评估→面试 0%。",
            },
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--components", nargs="+", choices=list(contexts()), default=list(contexts())
    )
    parser.add_argument("--report", type=Path, default=ROOT / "test-results/dify-live-smoke.json")
    args = parser.parse_args()
    gateway = DifyGateway(Settings(_env_file=ROOT / "backend/.env", ai_timeout_seconds=120))
    routing = json.loads((ROOT / "deploy/dify/model-routing.json").read_text(encoding="utf-8"))
    results = []
    for component in args.components:
        data = contexts()[component]
        row = {
            "component": component,
            "model": routing[component]["model"],
            "runs": [],
            "transient_errors": [],
        }
        samples = []
        try:
            for sample in range(3 if component == "A5" else 1):
                for attempt in range(3):
                    try:
                        run = gateway.call(component, data, "smoke-" + uuid4().hex, sample)
                        break
                    except DomainError as exc:
                        if exc.code != "AI_PROVIDER_UNAVAILABLE" or attempt == 2:
                            raise
                        row["transient_errors"].append(exc.code)
                        time.sleep(3 ** (attempt + 1))
                samples.append(run.pop("output"))
                row["runs"].append(run)
            output = validate(component, samples, data)
            if component == "A3" and not output["fields"]:
                raise DomainError("SMOKE_EMPTY_EXTRACTION", "Expected synthetic evidence")
            if component == "A5" and output["conclusion"] != "advance":
                raise DomainError("SMOKE_UNEXPECTED_EVALUATION", "Expected synthetic evidence")
            row["status"] = "passed"
        except DomainError as exc:
            row.update(status="failed", error_code=exc.code)
        except (ValueError, TypeError, KeyError):
            row.update(status="failed", error_code="AI_OUTPUT_REJECTED")
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {"at": datetime.now(UTC).isoformat(), "synthetic_data_only": True, "results": results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if any(row["status"] != "passed" for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
