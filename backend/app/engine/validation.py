"""Deterministic checks. Model output never chooses a business command."""

import json
import re
import unicodedata
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
    "感谢您的关注",
    "关于您的问题",
    "以下是相关信息",
    "我会请招聘 HR 核实后回复您",
    "确认后回复您",
    "请问您还有哪些问题",
    "如有其他问题欢迎随时咨询",
    "收到，谢谢",
    "请稍候",
]
# Models often normalise punctuation, width or case, or elide the middle of a long
# passage with an ellipsis. Those are not fabrications, so match on the normalised
# characters and require every elided piece to appear, in order, in the source.
ELLIPSIS = re.compile(r"…+|\.{3,}|。{3,}")
NOISE = re.compile(r"[\W_]+")
# A figure is its value plus the unit right after it ("3 人" differs from "3 周"),
# so a real count cannot be reused to dress up an invented forecast or rate.
NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*([人名位个天日周月年次轮倍家万千小%]?)")
A3_FIELDS = {
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


def reject(message, *reasons):
    raise DomainError("AI_OUTPUT_REJECTED", message, 422, {"reasons": sorted(set(reasons))})


def compact(text):
    return NOISE.sub("", unicodedata.normalize("NFKC", text or "").casefold())


def quote_matches(quote, source):
    pieces = [compact(piece) for piece in ELLIPSIS.split(quote or "")]
    pieces = [piece for piece in pieces if piece]
    if not pieces or (len(pieces) > 1 and min(map(len, pieces)) < 4):
        return False
    target, position = compact(source), 0
    for piece in pieces:
        found = target.find(piece, position)
        if found < 0:
            return False
        position = found + len(piece)
    return True


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


def numbers(text):
    return {
        (float(n), unit) for n, unit in NUMBER.findall(unicodedata.normalize("NFKC", text or ""))
    }


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
    if context.get("first_reply") and compact("AI招聘助手") not in compact(text):
        reasons.append("ai_identity_required")
    knowledge = context["knowledge"]
    for claim in value["claims"]:
        if claim["kb_ref"] not in knowledge or not quote_matches(
            claim["quote"], knowledge.get(claim["kb_ref"], "")
        ):
            reasons.append("knowledge_reference_invalid")
    if reasons:
        reject("回复未通过证据或披露校验", *reasons)
    # A claim list alone cannot prove all free text is grounded. Only allow exact
    # public knowledge passages, approved questions and neutral social phrases.
    allowed = [
        *SOCIAL,
        *context.get("questions", []),
        *(knowledge.get(c["kb_ref"], "") for c in value["claims"]),
    ]
    for claim in value["claims"]:
        allowed += ELLIPSIS.split(claim["quote"])
    remaining = compact(ELLIPSIS.sub("", text))
    for phrase in sorted({compact(p) for p in allowed if compact(p)}, key=len, reverse=True):
        remaining = remaining.replace(phrase, "")
    if remaining:
        reject("回复未通过证据或披露校验", "ungrounded_reply")
    # Deferring to HR is a promise of human follow-up; never let it auto-close.
    # Live runs showed the model sometimes defers but leaves needs_human false.
    if compact("核实后回复") in compact(text):
        value["needs_human"] = True
        if "ask_human" not in value["intents"]:
            value["intents"].append("ask_human")
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
        # Keep the quotes that do match; one paraphrased quote should not erase
        # an otherwise grounded judgement. No matching quote means "unknown".
        matched = [e for e in item["evidence"] if valid_evidence(e, context["sources"])]
        invalid += len(item["evidence"]) - len(matched)
        item["evidence"] = matched
        if item["verdict"] != "unknown" and not matched:
            item.update(verdict="unknown", note="引用未匹配原文")
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


def evaluation(samples, context):
    evaluated = []
    for raw in samples:
        try:
            evaluated.append(one_evaluation(raw, context))
        except (ValueError, TypeError, KeyError, DomainError):
            evaluated.append(None)
    conclusions = [e["conclusion"] if e else "invalid" for e in evaluated]
    valid = [c for c in conclusions if c != "invalid"]
    if not valid:
        reject("多次评估均未通过结构校验", "evaluation_invalid")
    # Present the majority view (earliest sample breaks ties), not whatever sample
    # happened to come first: a single malformed or outlier run no longer decides.
    majority = max(dict.fromkeys(valid), key=valid.count)
    main = next(e for e in evaluated if e and e["conclusion"] == majority)
    confidence = (
        0.5 * conclusions.count(majority) / max(3, len(samples))
        + 0.3 * main["coverage"]
        + 0.2 * main["self_confidence"]
    )
    if main["invalid_evidence"]:
        confidence *= 0.8
    main.update(confidence=round(confidence, 4), sample_conclusions=conclusions)
    if main["conclusion"] == "hold":
        main["confidence"] = min(main["confidence"], 0.59)
    return main


def extraction(result, context):
    from app.modules.candidate.contracts import Profile

    kept, dropped = {}, []
    for key, field in result["fields"].items():
        evidence, value = field["evidence"], field["value"]
        reason = None
        if key not in A3_FIELDS:
            reason = "field_not_allowed"
        elif PROTECTED.search(value) or PROTECTED.search(evidence["quote"]):
            reason = "protected_attribute"
        elif not valid_evidence(evidence, context["sources"]):
            reason = "evidence_mismatch"
        elif not quote_matches(value, evidence["quote"]):
            reason = "value_not_in_quote"
        else:
            try:
                Profile(name="validation", **{key: value})
            except ValueError:
                reason = "field_invalid"
        if reason:
            dropped.append({"field": key, "reason": reason})
        else:
            kept[key] = field
    # Grounded fields survive a bad neighbour; reject only when nothing usable is left.
    if dropped and not kept:
        reject("解析字段必须逐字匹配原文证据", *(d["reason"] for d in dropped))
    return {"fields": kept, "dropped": dropped}


def feedback(result, context):
    kept, dropped = [], []
    for item in result["items"]:
        if PROTECTED.search(item["notes"]) or any(
            PROTECTED.search(e["quote"]) for e in item["evidence"]
        ):
            dropped.append({"id": item["id"], "reason": "protected_attribute"})
        elif not all(valid_evidence(e, context["sources"]) for e in item["evidence"]):
            dropped.append({"id": item["id"], "reason": "evidence_mismatch"})
        else:
            kept.append(item)
    if not kept:
        reject("面评草稿证据不匹配", *(d["reason"] for d in dropped))
    return {"items": kept, "dropped": dropped}


def insight(result, context):
    sources = context["sources"]
    refs = list(dict.fromkeys(result["data_refs"]))
    if not result["answer"].strip():
        reject("洞察缺少结论", "answer_required")
    if not set(refs).issubset(sources):
        reject("洞察引用不存在", "data_reference_invalid")
    # Every figure must come from the position's aggregates, its own fields (e.g. level
    # P5) or the HR's question; otherwise it is invented. Live runs showed the model
    # quotes correct figures but forgets to list every key, so a figure found in an
    # uncited source adds that source to the citations instead of failing the job.
    used = numbers(" ".join([result["answer"], *result["suggestions"]]))
    covered = numbers(context.get("prompt", "")).union(
        numbers(" ".join(map(str, (context.get("position") or {}).values()))),
        *(numbers(sources[r]) for r in refs),
    )
    for key, text in sources.items():
        if key not in refs and (used - covered) & numbers(text):
            refs.append(key)
            covered |= numbers(text)
    if used - covered:
        reject("洞察数字未在岗位数据中出现", "ungrounded_number")
    return {**result, "data_refs": refs, "cited": {r: sources[r] for r in refs}}


def validate(component, samples, context):
    if component == "A5":
        return evaluation(samples, context)
    if component == "A4":
        return validate_reply(samples[0], context)
    try:
        result = OUTPUTS[component].model_validate(samples[0]).model_dump()
    except ValueError:
        reject("输出结构不符合约定", "schema_invalid")
    if component in {"A1", "A2", "A7"} and PROTECTED.search(json.dumps(result, ensure_ascii=False)):
        reject("建议包含受保护属性，请人工处理", "protected_attribute")
    if component == "A3":
        result = extraction(result, context)
    if component == "A6":
        result = feedback(result, context)
    if component == "A7":
        result = insight(result, context)
    if component == "A2" and not any(k.strip() for k in result["keywords"]):
        reject("搜索建议缺少关键词", "keywords_required")
    if component == "A1":
        from app.modules.position.content import check_language
        from app.modules.position.contracts import PositionCommand

        if set(result["fields"]) - {"must", "plus", "redflag", "jd", "must_ask"}:
            reject("草稿字段不在允许范围", "field_not_allowed")
        if (
            not result["fields"].get("must", "").strip()
            or not result["fields"].get("jd", "").strip()
        ):
            reject("画像草稿必须包含职业要求和 JD", "profile_incomplete")
        try:
            PositionCommand(action="save_profile", expected_version=1, **result["fields"])
        except ValueError:
            reject("画像草稿字段不合法", "field_invalid")
        try:
            check_language(" ".join(result["fields"].values()))
        except DomainError:
            reject("请修改画像或 JD 中的歧视性表述", "discriminatory_language")
    return deepcopy(result)
