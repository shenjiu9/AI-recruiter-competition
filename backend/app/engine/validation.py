"""Deterministic checks. Model output never chooses a business command."""

import json
import re
from copy import deepcopy

from app.engine.contracts import OUTPUTS, Evaluation, Reply
from app.kernel.types import DomainError
from app.modules.candidate.parser import PROTECTED

INJECTION = re.compile(
    r"忽略.{0,12}(指令|规则)|给我打满分|忽略以上|ignore.{0,20}(instruction|prompt)|system\s*prompt|<\s*/?system",
    re.I,
)
PROMISE = re.compile(
    r"(保证|肯定|一定|确保|承诺).{0,12}(录用|通过|入职)|guarantee.{0,20}(hire|offer|pass)", re.I
)
SOCIAL = [
    "您好，我是AI招聘助手",
    "您好，我是 AI 招聘助手",
    "我是 AI 招聘助手",
    "您好",
    "谢谢您的回复",
    "感谢您的回复",
    "我会请招聘 HR 核实后回复您",
    "确认后回复您",
    "请问您还有哪些问题",
    "收到，谢谢",
    "请稍候",
]


def compact(text):
    return re.sub(r"\s+", "", text)


def quote_matches(quote, source):
    return bool(compact(quote)) and compact(quote) in compact(source)


def valid_evidence(evidence, sources):
    ref = evidence["ref"]
    kind = (
        "profile"
        if ref.startswith("F:")
        else "resume"
        if ref.startswith("RES-")
        else "transcript"
        if ref.startswith("T")
        else None
    )
    return (kind is None or evidence["source"] == kind) and quote_matches(
        evidence["quote"], sources.get(ref, "")
    )


def validate_reply(output, context):
    value = Reply.model_validate(output).model_dump()
    text = value["reply"]
    reasons = []
    if PROTECTED.search(text):
        reasons.append("protected_attribute")
    if PROMISE.search(text):
        reasons.append("promise_forbidden")
    if INJECTION.search(text):
        reasons.append("injection_suspect")
    if context.get("first_reply") and "AI招聘助手" not in compact(text):
        reasons.append("ai_identity_required")
    knowledge = context["knowledge"]
    for claim in value["claims"]:
        if claim["kb_ref"] not in knowledge or not quote_matches(
            claim["quote"], knowledge.get(claim["kb_ref"], "")
        ):
            reasons.append("knowledge_reference_invalid")
    if reasons:
        raise DomainError(
            "AI_OUTPUT_REJECTED", "回复未通过证据或披露校验", 422, {"reasons": reasons}
        )
    # A claim list alone cannot prove all free text is grounded. Only allow exact
    # public knowledge passages, approved questions and neutral social phrases.
    allowed = [
        *SOCIAL,
        *context.get("questions", []),
        *(knowledge.get(c["kb_ref"], "") for c in value["claims"]),
    ]
    allowed += [claim["quote"] for claim in value["claims"]]
    remaining = compact(text)
    for phrase in sorted(filter(None, allowed), key=len, reverse=True):
        remaining = remaining.replace(compact(phrase), "")
    if re.sub(r"[。！!？?，,；;：:\s]", "", remaining):
        reasons.append("ungrounded_reply")
    if reasons:
        raise DomainError(
            "AI_OUTPUT_REJECTED", "回复未通过证据或披露校验", 422, {"reasons": sorted(set(reasons))}
        )
    return value


def one_evaluation(raw, context):
    value = Evaluation.model_validate(raw).model_dump()
    criteria = context["criteria"]
    ids = [item["id"] for item in value["items"]]
    if len(ids) != len(set(ids)) or set(ids) != {c["id"] for c in criteria}:
        raise DomainError("AI_OUTPUT_REJECTED", "评估条目不完整或重复")
    invalid, sensitive = 0, False
    for item in value["items"]:
        if PROTECTED.search(item["note"]) or any(
            PROTECTED.search(e["quote"]) for e in item["evidence"]
        ):
            item.update(verdict="unknown", note="受保护内容已移除", evidence=[])
            sensitive = True
        if (item["verdict"] != "unknown" and not item["evidence"]) or any(
            not valid_evidence(e, context["sources"]) for e in item["evidence"]
        ):
            item.update(verdict="unknown", note="引用未匹配原文", evidence=[])
            invalid += 1
    answers = {i["id"]: i["verdict"] for i in value["items"]}
    must = [answers[c["id"]] for c in criteria if c["kind"] == "must"]
    redflags = sum(answers[c["id"]] == "meet" for c in criteria if c["kind"] == "redflag")
    conclusion = (
        "reject"
        if "not_meet" in must
        else "need_info"
        if "unknown" in must
        else "hold"
        if redflags
        else "advance"
    )
    plus = [c for c in criteria if c["kind"] == "plus"]
    weighted = sum(c["weight"] for c in plus if answers[c["id"]] == "meet") / max(
        1, sum(c["weight"] for c in plus)
    )
    score = max(
        0,
        round(
            100 * (0.6 * (must.count("meet") / max(1, len(must))) + 0.4 * weighted) - 15 * redflags
        ),
    )
    coverage = [answers[c["id"]] for c in criteria if c["kind"] != "redflag"]
    value.update(
        conclusion=conclusion,
        score=score,
        invalid_evidence=invalid,
        sensitive=sensitive,
        coverage=sum(v != "unknown" for v in coverage) / max(1, len(coverage)),
    )
    value["questions"] = [
        q for q in value["questions"] if not PROTECTED.search(q) and not INJECTION.search(q)
    ]
    return value


def validate(component, samples, context):
    if component == "A5":
        main = one_evaluation(samples[0], context)
        conclusions = []
        for raw in samples:
            try:
                conclusions.append(one_evaluation(raw, context)["conclusion"])
            except (ValueError, DomainError):
                conclusions.append("invalid")
        confidence = (
            0.5 * conclusions.count(main["conclusion"]) / 3
            + 0.3 * main["coverage"]
            + 0.2 * main["self_confidence"]
        )
        if main["invalid_evidence"]:
            confidence *= 0.8
        main.update(confidence=round(confidence, 4), sample_conclusions=conclusions)
        if main["conclusion"] == "hold":
            main["confidence"] = min(main["confidence"], 0.59)
        return main
    if component == "A4":
        return validate_reply(samples[0], context)
    result = OUTPUTS[component].model_validate(samples[0]).model_dump()
    if component in {"A1", "A2", "A7"} and PROTECTED.search(json.dumps(result, ensure_ascii=False)):
        raise DomainError("AI_OUTPUT_REJECTED", "建议包含受保护属性，请人工处理")
    if component == "A3":
        from app.modules.candidate.contracts import Profile

        allowed = {
            "city",
            "company",
            "title",
            "school",
            "degree",
            "skills",
            "experience",
            "education",
            "certificates",
            "expected_city",
        }
        if set(result["fields"]) - allowed:
            raise DomainError("AI_OUTPUT_REJECTED", "解析只能提出允许的非敏感字段")
        Profile(name="validation", **{k: field["value"] for k, field in result["fields"].items()})
        for field in result["fields"].values():
            evidence = field["evidence"]
            if (
                PROTECTED.search(field["value"])
                or not valid_evidence(evidence, context["sources"])
                or not quote_matches(field["value"], evidence["quote"])
            ):
                raise DomainError("AI_OUTPUT_REJECTED", "解析字段必须逐字匹配原文证据")
    if component == "A6":
        for item in result["items"]:
            if PROTECTED.search(item["notes"]) or any(
                not valid_evidence(e, context["sources"]) for e in item["evidence"]
            ):
                raise DomainError("AI_OUTPUT_REJECTED", "面评草稿证据不匹配")
    if component == "A7" and not set(result["data_refs"]).issubset(context["sources"]):
        raise DomainError("AI_OUTPUT_REJECTED", "洞察引用不存在")
    if component == "A1":
        from app.modules.position.content import check_language
        from app.modules.position.contracts import PositionCommand

        if set(result["fields"]) - {"must", "plus", "redflag", "jd", "must_ask"}:
            raise DomainError("AI_OUTPUT_REJECTED", "草稿字段不在允许范围")
        PositionCommand(action="save_profile", expected_version=1, **result["fields"])
        if (
            not result["fields"].get("must", "").strip()
            or not result["fields"].get("jd", "").strip()
        ):
            raise DomainError("AI_OUTPUT_REJECTED", "画像草稿必须包含职业要求和 JD")
        check_language(" ".join(result["fields"].values()))
    return deepcopy(result)
