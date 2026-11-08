"""Explicit paid A0 smoke through Dify, using synthetic sentences and no business writes."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from app.engine.agent import grounded, to_agent_route
from app.engine.gateway import DifyGateway
from app.platform.settings import Settings
from scripts.eval_router_direct import CASES

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "test-results/assistant-router.json")
    args = parser.parse_args()
    gateway = DifyGateway(Settings(_env_file=ROOT / "backend/.env", ai_timeout_seconds=120))
    rows = []
    cases = CASES + [
        ("为客服专员做简历匹配", "A2", "客服专员", ""),
        ("从人才库里为客服专员匹配简历", "A2", "客服专员", ""),
    ]
    for text, intent, position, candidate in cases:
        result = gateway.call("A0", {"text": text}, "router-smoke-" + uuid4().hex)
        route = grounded(to_agent_route(result["output"]), text)
        row = {
            "text": text,
            "expected": intent,
            "actual": route.intent,
            "intent_ok": route.intent == intent,
            "position_ok": route.position == position,
            "candidate_ok": route.candidate == candidate,
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report = {
        "synthetic_data_only": True,
        "total": len(rows),
        "intent_passed": sum(row["intent_ok"] for row in rows),
        "rows": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["intent_passed"] != report["total"]:
        raise SystemExit("Router intent smoke failed; inspect the synthetic report")


if __name__ == "__main__":
    main()
