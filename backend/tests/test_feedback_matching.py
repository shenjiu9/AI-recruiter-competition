import json

import pytest
from test_ai_engine import action, enable, get, start
from test_candidates import command, create, ok
from test_positions import opened
from test_requisition_api import ROOT
from test_requisition_api import create as create_requisition

from app.ai_worker import run_once
from app.engine.validation import validate
from app.kernel.types import DomainError


def test_workbench_includes_current_requisition_approvals_and_withdraw_owner(client, login, fields):
    req = create_requisition(client, login, fields)
    for actor, count in (("manager", 1), ("hrbp", 0), ("hr", 0)):
        board = ok(client.get("/api/v1/hr/workbench-live", headers=login(actor)))
        assert board["counts"]["my_approvals"] == count
        assert len(board["requisition_approvals"]) == count
    path = f"{ROOT}/{req['id']}"
    assert (
        client.post(
            path + "/withdraw", headers=login("manager"), json={"expected_version": req["version"]}
        ).status_code
        == 403
    )
    req = ok(
        client.post(
            path + "/approve",
            headers=login("manager"),
            json={"node_id": "manager", "expected_version": req["version"]},
        )
    )
    board = ok(client.get("/api/v1/hr/workbench-live", headers=login("director")))
    assert board["counts"]["my_approvals"] == 1
    assert board["requisition_approvals"][0]["id"] == req["id"]
    ok(
        client.post(
            path + "/withdraw", headers=login("hr"), json={"expected_version": req["version"]}
        )
    )
    assert (
        ok(client.get("/api/v1/hr/workbench-live", headers=login("director")))["counts"][
            "my_approvals"
        ]
        == 0
    )


def test_salary_picker_is_scoped_read_only_directory(client, login):
    path = "/api/v1/hr/requisition-form/salary-options"
    result = ok(client.get(path, params={"dept": "客服中心"}, headers=login("manager")))
    assert result["items"] and all(row["active"] for row in result["items"])
    assert "latest" not in result["items"][0]
    assert client.get(path, params={"dept": "财务部"}, headers=login("manager")).status_code == 403


class MatchingGateway:
    def configured(self, component):
        return True

    def call(self, component, inputs, action_id, **kwargs):
        matches = []
        for c in inputs["candidates"]:
            quote = c["sources"].get("F:skills", "")
            matches.append(
                {
                    "candidate_id": c["candidate_id"],
                    "self_confidence": 0.8,
                    "items": [
                        {
                            "id": r["id"],
                            "verdict": "meet" if "Python" in quote else "unknown",
                            "note": "职业技能证据",
                            "evidence": [{"source": "profile", "ref": "F:skills", "quote": quote}]
                            if quote
                            else [],
                        }
                        for r in inputs["criteria"]
                    ],
                }
            )
        return {
            "output": {
                "keywords": ["Python"],
                "explanation": "按岗位职业要求匹配",
                "matches": matches,
            },
            "run_id": action_id,
            "tokens": 50,
            "elapsed_ms": 1,
        }


def test_matching_real_job_pipeline_grounding_consent_and_no_automatic_attachment(
    client, login, fields, container
):
    container.ai_gateway = MatchingGateway()
    enable(client, login, mode="manual")
    _, position = opened(client, login, fields, container, requirements="Python 开发实践")
    candidates = [
        create(client, login, name="合成匹配样本一", skills="Python", email="one@example.invalid"),
        create(client, login, name="合成匹配样本二", skills="Excel"),
    ]
    for index, c in enumerate(candidates):
        candidates[index] = ok(
            command(client, login, c, "consent", granted=True, evidence="合成授权", reason="测试")
        )
    job = ok(
        start(client, login, "A2", position["id"], candidate_ids=[c["id"] for c in candidates])
    )
    payload = json.dumps(job["inputs"], ensure_ascii=False)
    assert "one@example.invalid" not in payload and "合成匹配样本一" not in payload
    assert run_once(container)
    job = get(client, login, job)
    assert job["status"] == "review", job
    assert job["output"]["matches"][0]["candidate_id"] == candidates[0]["id"]
    assert job["output"]["matches"][1]["conclusion"] == "need_info"
    assert ok(action(client, login, job))["status"] == "reviewed"
    for c in candidates:
        assert not ok(client.get("/api/v1/hr/candidates/" + c["id"], headers=login()))[
            "applications"
        ]
    ok(
        command(
            client,
            login,
            candidates[0],
            "consent",
            granted=False,
            evidence="撤回授权",
            reason="测试",
        )
    )
    assert client.get("/api/v1/hr/ai-jobs/" + job["id"], headers=login()).status_code == 409
    assert (
        start(client, login, "A2", position["id"], candidate_ids=[candidates[0]["id"]]).status_code
        == 409
    )
    current = ok(client.get("/api/v1/hr/candidates/" + candidates[0]["id"], headers=login()))
    ok(command(client, login, current, "erase", reason="删除合成测试资料"))
    with container.scope() as s:
        assert s.engine.jobs.get(job["id"]) is None


def test_matching_cannot_invent_candidates_or_borrow_other_resumes():
    context = {
        "criteria": [{"id": "M1", "kind": "must", "text": "Python", "weight": 1}],
        "candidates": [
            {"candidate_id": "one", "sources": {"F:skills": "Python"}},
            {"candidate_id": "two", "sources": {"F:skills": "Excel"}},
        ],
    }
    output = {
        "keywords": ["Python"],
        "explanation": "匹配",
        "matches": [
            {
                "candidate_id": cid,
                "self_confidence": 1,
                "items": [
                    {
                        "id": "M1",
                        "verdict": "meet",
                        "evidence": [{"source": "profile", "ref": "F:skills", "quote": "Python"}],
                    }
                ],
            }
            for cid in ("one", "two")
        ],
    }
    result = validate("A2", [output], context)
    assert result["matches"][1]["items"][0]["verdict"] == "unknown"
    # A real provider quoted Excel correctly but inferred absence of Python.
    # Grounding alone must not turn incomplete information into a rejection.
    item = output["matches"][1]["items"][0]
    item.update(verdict="not_meet", note="只描述 Excel，未体现 Python")
    item["evidence"][0]["quote"] = "Excel"
    result = validate("A2", [output], context)
    assert result["matches"][1]["conclusion"] == "need_info"
    assert result["matches"][1]["coverage"] == 0
    output["matches"][1]["candidate_id"] = "invented"
    with pytest.raises(DomainError):
        validate("A2", [output], context)
