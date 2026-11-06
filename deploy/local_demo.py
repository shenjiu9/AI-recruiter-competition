"""Create a labelled synthetic local demo and exercise real Dify-backed jobs.

Explicit opt-in script: uses development accounts, changes AI policy to manual
review, creates demo records, and invokes paid models. Never targets remote APIs.
Private resume state and the candidate capability URL stay under ignored backups/.
"""

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "backups/local-demo.json"


def main():
    env = dotenv_values(ROOT / "backend/.env")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"jobs": {}}

    def save():
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    with httpx.Client(base_url="http://localhost:8000/api/v1", trust_env=False, timeout=30) as c:
        tokens = {}

        def call(method, path, body=None, actor="hr"):
            if actor not in tokens:
                r = c.post(
                    "/auth/dev-login",
                    json={"user_id": actor, "password": env["DEV_LOGIN_PASSWORD"]},
                )
                if not r.is_success:
                    raise SystemExit("Local demo login failed: " + actor)
                tokens[actor] = r.json()["token"]
            r = c.request(
                method,
                path,
                json=body,
                headers={
                    "Authorization": "Bearer " + tokens[actor],
                    "Idempotency-Key": uuid4().hex,
                },
            )
            if not r.is_success:
                code = r.json().get("error", {}).get("code", "HTTP_ERROR")
                raise SystemExit(f"Local demo {method} {path}: {r.status_code} {code}")
            return r.json()

        policy = call("GET", "/hr/automation-live", actor="admin")
        state.setdefault("previous_policy", policy)
        if policy["mode"] != "manual" or not all(policy["components"].values()):
            call(
                "POST",
                "/hr/automation-live",
                {
                    "expected_version": policy["version"],
                    "mode": "manual",
                    "components": {f"A{i}": True for i in range(1, 8)},
                },
                actor="admin",
            )
        save()
        health = call("GET", "/hr/ai-health")
        if not health["worker_enabled"] or not all(health["components"].values()):
            raise SystemExit("Start the configured AI worker before running the demo")
        if "requisition" not in state:
            req = call(
                "POST",
                "/hr/requisitions",
                {
                    "recruitType": "社招",
                    "dept": "客服中心",
                    "employmentType": "外包",
                    "reqType": "新增",
                    "headcount": "2",
                    "title": "本机演示-Python支持工程师",
                    "series": "客服",
                    "level": "P3",
                    "city": "深圳",
                    "reportTo": "何美玲",
                    "expectedOnboard": (datetime.now(UTC).date() + timedelta(days=30)).isoformat(),
                    "salary": "8-12K/月×13",
                    "reason": "合成演示数据，仅用于本机功能联调",
                    "duties": "使用 Python 和 PostgreSQL 开发客服支持系统",
                    "requirements": "Python 开发实践",
                },
            )
            state["requisition"] = req["id"]
            save()
        req = call("GET", "/hr/requisitions/" + state["requisition"])
        while req["status"] == "in_approval":
            node = req["chain"][req["currentNode"]]
            req = call(
                "POST",
                f"/hr/requisitions/{req['id']}/approve",
                {"expected_version": req["version"], "node_id": node["id"]},
                actor=node["approver_id"],
            )
        if req["status"] != "approved":
            raise SystemExit("Demo requisition needs attention")
        for _ in range(30):
            projection = call("GET", f"/hr/requisitions/{req['id']}/position")
            if projection["status"] == "generated":
                state["position"] = projection["position"]["id"]
                save()
                break
            time.sleep(1)
        else:
            raise SystemExit("Position generation did not complete")
        pid = state["position"]

        def position_action(action, actor="hr", **body):
            pos = call("GET", "/hr/positions/" + pid)
            return call(
                "POST",
                f"/hr/positions/{pid}/actions",
                {"expected_version": pos["version"], "action": action, **body},
                actor=actor,
            )

        if not state.get("position_ready"):
            position_action(
                "save_profile",
                must="Python 开发实践",
                plus="PostgreSQL 实践",
                plus_weights=["medium"],
                jd="使用 Python 开发客服支持系统。工作地点：深圳。",
                must_ask="请介绍您的 Python 项目经验？",
            )
            position_action("confirm_profile", actor="manager")
            position_action("publish")
            position_action(
                "save_kb",
                content="工作地点：深圳",
                source="合成演示岗位信息",
                disclosure="proactive",
            )
            position_action(
                "save_interview_plan",
                rounds=[
                    {
                        "name": "演示专业面",
                        "format": "phone",
                        "duration": 30,
                        "interviewers": ["manager"],
                        "rule": "unanimous",
                        "criteria": "专业能力\n沟通能力",
                    }
                ],
            )
            state["position_ready"] = True
            save()
        if "candidate" not in state:
            candidate = call(
                "POST",
                "/hr/candidates",
                {
                    "profile": {
                        "name": "本机联调演示候选人",
                        "experience": "使用 Python 开发后端服务，使用 PostgreSQL 存储数据。",
                    },
                    "source": "manual",
                },
            )["candidate"]
            state["candidate"] = candidate["id"]
            save()
        cid = state["candidate"]
        candidate = call("GET", "/hr/candidates/" + cid)
        if candidate["consent"] != "granted":
            call(
                "POST",
                f"/hr/candidates/{cid}/actions",
                {
                    "expected_version": candidate["version"],
                    "action": "consent",
                    "granted": True,
                    "evidence": "纯合成演示数据，不涉及真实个人",
                    "reason": "本机功能联调",
                },
            )

        def job(component, object_id, actor="hr", prompt="", approve=True):
            if component == "A4" and component in state["jobs"]:
                old = call("GET", "/hr/ai-jobs/" + state["jobs"][component], actor=actor)
                if old["status"] == "cancelled" and old["error_code"] in {
                    "AI_CONTEXT_CHANGED",
                    "AI_DEBOUNCING",
                }:
                    state.setdefault("superseded_jobs", []).append(state["jobs"].pop(component))
                    save()
            if component not in state["jobs"]:
                item = call(
                    "POST",
                    "/hr/ai-jobs",
                    {"component": component, "object_id": object_id, "prompt": prompt},
                    actor=actor,
                )
                state["jobs"][component] = item["id"]
                save()
            key = state["jobs"][component]
            deadline, last = time.monotonic() + 420, None
            while time.monotonic() < deadline:
                item = call("GET", "/hr/ai-jobs/" + key, actor=actor)
                if item["status"] != last:
                    print(component + ": " + item["status"], flush=True)
                    last = item["status"]
                if item["status"] in {"review", "applied", "reviewed"}:
                    break
                if item["status"] in {"cancelled", "dead", "rejected"}:
                    raise SystemExit(component + " stopped: " + item["error_code"])
                time.sleep(2)
            else:
                raise SystemExit(component + " exceeded demo deadline")
            if approve and item["status"] == "review":
                if component == "A5" and item["output"]["conclusion"] != "advance":
                    raise SystemExit("Synthetic A5 evidence requires inspection")
                item = call(
                    "POST",
                    f"/hr/ai-jobs/{key}/actions",
                    {
                        "expected_version": item["version"],
                        "action": "approve",
                        "verified": True,
                        "reason": "核对合成演示原文，仅用于本机联调",
                    },
                    actor=actor,
                )
                print(component + ": " + item["status"], flush=True)
            return item

        job("A3", cid)
        if "application" not in state:
            state["application"] = call(
                "POST", "/hr/applications", {"candidate_id": cid, "position_id": pid}
            )["id"]
            save()
        if not state.get("application_ready"):
            for _ in range(2):
                candidate = call("GET", "/hr/candidates/" + cid)
                app = next(a for a in candidate["applications"] if a["id"] == state["application"])
                if app["stage"] in {"ai_eval", "interview"}:
                    break
                call(
                    "POST",
                    f"/hr/applications/{app['id']}/actions",
                    {"expected_version": app["version"], "action": "advance"},
                )
            state["application_ready"] = True
            save()
        job("A5", state["application"])
        interviews = call("GET", "/hr/interviews?application_id=" + state["application"])["items"]
        state["interview"] = interviews[0]["id"]
        save()
        job(
            "A6",
            state["interview"],
            actor="manager",
            prompt="我使用 Python 开发后端服务，使用 PostgreSQL 存储数据，并通过集成测试验证接口。",
        )
        conversation = call("GET", f"/hr/candidates/{cid}/conversation")
        link = call(
            "POST",
            f"/hr/candidates/{cid}/conversation",
            {"action": "issue_link", "expected_version": conversation["version"]},
        )
        state["portal_url"] = link["url"]
        save()
        if "A4" not in state["jobs"]:
            portal_headers = {
                "Authorization": "Bearer " + link["url"].split("#t=")[1],
                "Idempotency-Key": uuid4().hex,
            }
            current = c.get("/candidate/session", headers=portal_headers).json()
            response = c.post(
                "/candidate/actions",
                headers=portal_headers,
                json={
                    "action": "send",
                    "expected_version": current["version"],
                    "content": "请问工作地点在哪里？",
                },
            )
            if not response.is_success:
                raise SystemExit("Synthetic candidate message failed")
            # Let the persistent conversation debounce settle before taking an AI snapshot.
            time.sleep(12)
        job("A4", cid)
        job("A2", pid)
        job("A7", pid, prompt="说明当前岗位的招聘进度")
        job("A1", pid, approve=False)
        print(
            "Local synthetic demo completed; A1 remains pending review. Private state saved under backups/.",
            flush=True,
        )


if __name__ == "__main__":
    main()
