import json
import re

from app.kernel.types import DomainError
from app.modules.candidate.parser import safe_text
from app.modules.hiring.public import fingerprint


def sanitize(value, candidate=None):
    if isinstance(value, dict):
        return {k: sanitize(v, candidate) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v, candidate) for v in value]
    if not isinstance(value, str):
        return value
    value = safe_text(value)
    if candidate:
        for key in ("name", "phone", "email"):
            if candidate["profile"].get(key):
                value = value.replace(candidate["profile"][key], "[已脱敏]")
    value = re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:\+86)?1[3-9]\d{9}(?!\d)", "[已脱敏]", value
    )
    return value


def build(s, ctx, component, object_id, prompt=""):
    s.candidate.lock(ctx)
    if component != "A6":
        s.candidate.require_hr(ctx)
    data = {
        "component": component,
        "prompt": sanitize(prompt),
        "sources": {},
        "criteria": [],
        "knowledge": {},
        "questions": [],
        "positions": [],
        "versions": {},
    }
    cid, pid, aid = None, None, None
    if component in {"A1", "A2", "A7"}:
        pos = s.position.get(ctx, object_id)
        if not pos["canEdit"]:
            raise DomainError("FORBIDDEN", "仅岗位负责 HR 可发起此 AI 任务", 403)
        pid = object_id
    elif component == "A5":
        app, pos = s.application.authorize(ctx, object_id)
        if app["outcome"] or app["stage"] != "ai_eval":
            raise DomainError("AI_STAGE_REQUIRED", "请先进入 AI 评估阶段", 409)
        cid, pid, aid = app["canonical_id"], app["position_id"], app["id"]
        data["versions"][aid] = app["version"]
    elif component == "A6":
        iv = s.interview.authorize(ctx, object_id)
        if not s.interview.assigned(iv, ctx.principal):
            raise DomainError("FORBIDDEN", "面评草稿只供本轮面试官使用", 403)
        cid, pid, aid = iv["candidate_id"], iv["position_id"], iv["application_id"]
        data["versions"][iv["id"]] = iv["version"]
        data["sources"] = {
            f"T{i + 1}": line
            for i, line in enumerate(sanitize(prompt).splitlines())
            if line.strip()
        }
        if not data["sources"]:
            raise DomainError("TRANSCRIPT_REQUIRED", "请提供已获授权的面试记录原文")
    else:
        candidate = s.candidate.authorize(ctx, object_id)
        cid = candidate["id"]
    if cid:
        candidate = s.candidate.canonical(cid)
        if candidate["consent"] != "granted" or candidate["do_not_contact"]:
            raise DomainError("CONSENT_REQUIRED", "候选人尚未授权或已要求停止处理", 409)
        data["versions"][cid] = candidate["version"]
        data["key_candidate"] = candidate["key_candidate"]
        data["profile"] = s.candidate.evaluation_input(cid)
        if component in {"A3", "A5"}:
            data["sources"] = s.candidate.ai_sources(cid)
        if component == "A4":
            conversation = s.conversation.snapshot(cid, ctx)
            if not s.conversation.readable(ctx, cid, []):
                raise DomainError("FORBIDDEN", "会话跨岗信息不在完整授权范围内", 403)
            data["versions"]["conversation"] = conversation["version"]
            data["mode"] = conversation["mode"]
            data["ai_paused"] = conversation["ai_paused"]
            data["first_reply"] = not any(
                m["sender"] in {"hr", "ai"} and m["status"] == "sent"
                for m in conversation["messages"]
            )
            messages = conversation["messages"][-20:]
            data["messages"] = [{k: m[k] for k in ("id", "content", "sender")} for m in messages]
            latest = s.conversation.latest_inbound(cid)
            data["reply_to_id"] = latest["id"] if latest else ""
            if not latest:
                raise DomainError("MESSAGE_REQUIRED", "候选人尚未发来消息", 409)
            apps = [a for a in s.conversation.apps(cid) if not a["outcome"]]
            if not apps or any(a["stage"] == "hired" for a in apps):
                raise DomainError("HUMAN_HANDOFF", "录用交接或没有在途应聘，请由 HR 回复", 409)
            for app in apps:
                s.application.authorize(ctx, app["id"])
                data["versions"][app["id"]] = app["version"]
                data["positions"].append(app["position_id"])
        data = sanitize(data, candidate)
    if pid:
        data["positions"].append(pid)
    for position_id in sorted(set(data["positions"])):
        pos = s.position.hiring_context(position_id)
        visible = s.position.get(ctx, position_id) if component != "A6" else None
        if (
            pos["status"] == "closed"
            or pos["frozen"]
            or (component == "A4" and pos["status"] != "open")
        ):
            raise DomainError("POSITION_UNAVAILABLE", "岗位状态不允许该 AI 任务", 409)
        data["versions"][position_id] = pos["version"]
        data["confidential"] = data.get("confidential", False) or pos["confidential"]
        data["position"] = {
            k: pos["fields"].get(k, "")
            for k in ("title", "series", "level", "city", "duties", "requirements")
        }
        if component == "A4":
            kb = s.position.knowledge_for_reply(ctx, position_id, asked=False)
            data["knowledge"].update({e["id"]: e["content"] for e in kb["entries"]})
            data["needs_human"] = data.get("needs_human", False) or kb["needsHuman"]
            data["questions"] += (
                s.position.current_profile(position_id).get("must_ask", "").splitlines()
            )
        if component == "A5":
            profile = s.position.current_profile(position_id)
            for key, prefix in (("must", "M"), ("plus", "P"), ("redflag", "R")):
                for i, line in enumerate(filter(str.strip, profile[key].splitlines())):
                    weight = 1
                    if key == "plus":
                        weight = {"high": 3, "medium": 2, "low": 1}.get(
                            profile["plus_weights"][i], 2
                        )
                    data["criteria"].append(
                        {"id": f"{prefix}{i + 1}", "text": line, "kind": key, "weight": weight}
                    )
        if component == "A7":
            data["sources"] = {
                "position_counts": json.dumps(visible["candidateCounts"], ensure_ascii=False),
                "headcount": f"计划{pos['planned']}，已录用{pos['hired']}",
            }
    config = s.automation.current()
    data["policy_versions"] = [config["version"]]
    for position_id in sorted(set(data["positions"])):
        pos = s.position.hiring_context(position_id)
        for key in (
            s.automation.series_key(pos["dept"], pos["fields"]["series"]),
            "position:" + position_id,
        ):
            data["policy_versions"].append(s.automation.current(key)["version"])
    data = sanitize(data, candidate if cid else None)
    if component == "A5" and (
        not any(c["kind"] == "must" for c in data["criteria"])
        or any(not c["text"].strip() for c in data["criteria"])
    ):
        raise DomainError("AI_CRITERIA_INVALID", "请先核对岗位生效画像中的职业要求", 409)
    return {
        "inputs": data,
        "stamp": fingerprint(data),
        "candidate_id": cid,
        "position_id": pid,
        "application_id": aid,
        "partition_key": cid or pid or object_id,
    }
