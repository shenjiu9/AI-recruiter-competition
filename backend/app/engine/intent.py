"""Natural-language entry for AI tasks.

An HR types one sentence ("白班客服还差几个人", "评估一下张三"). A router decides which
A1–A7 task it asks for; the backend then resolves the target among the records the
requester may see and starts the job through the normal engine, so every permission,
consent, stage and policy check still applies and every result still goes to review.

The optional router model (Dify workflow "A0") only sees the sanitized sentence, never
business data. Names it returns must appear verbatim in the sentence, so a guessed or
hallucinated name can never select a record. Without the model, or when it fails,
deterministic keyword rules route the sentence instead.
"""

import re
import unicodedata
from difflib import SequenceMatcher

from pydantic import ValidationError

from app.engine.context import sanitize
from app.engine.contracts import Route, StartJob
from app.kernel.types import DomainError

NAMES = {
    "A1": "岗位画像与 JD 草稿",
    "A2": "简历匹配与人才搜索",
    "A3": "简历字段提取",
    "A4": "沟通回复草稿",
    "A5": "候选人证据评估",
    "A6": "面试记录整理",
    "A7": "岗位数据洞察",
}
POSITION_TASKS = {"A1", "A2", "A7"}
STAGES = {
    "reach": "触达",
    "talking": "沟通中",
    "ai_eval": "AI 评估",
    "interview": "面试",
    "manager_eval": "用人经理评估",
    "hired": "已录用",
}
EXAMPLES = [
    "白班客服还差几个人",
    "帮客服专员写一版 JD",
    "给客服专员出一份人才搜索关键词",
    "提取张三的简历信息",
    "帮我回复张三的消息",
    "评估一下张三是否符合客服专员",
    "整理张三的面试记录：（粘贴面试记录原文）",
]
# Checked in order; the first rule whose pattern appears in the sentence wins. More
# specific tasks come first so "整理面试记录" is not read as a data question.
RULES = [
    ("A6", r"面评|面试(记录|纪要|笔记|反馈)|整理.{0,8}面试"),
    (
        "A3",
        r"提取|解析.{0,6}简历|简历.{0,6}(字段|信息|内容)|识别.{0,4}简历|(录入|整理|填).{0,6}(档案|信息)|进档案|到档案",
    ),
    ("A4", r"回复|回消息|回一下|答复|怎么回|回他|回她|回个话|回应"),
    ("A2", r"人才库|匹配简历|简历匹配|批量.{0,6}(匹配|筛选)"),
    (
        "A5",
        r"评估|匹配|是否符合|符不符合|符合.{0,6}(要求|条件)|合不合适|适不适合|是否合适|适合|合适吗|打分|初筛|筛一下|够不够格",
    ),
    (
        "A1",
        r"画像|JD|jd|职位描述|岗位描述|岗位说明|任职要求|岗位要求|招聘要求|招聘启事|职位要求",
    ),
    ("A2", r"搜索|搜人|搜一下|找人|寻访|人才|关键词|去哪.{0,4}找|渠道|找.{0,8}候选人|挖人"),
    (
        "A7",
        r"还差|缺几|差几|进度|多少人|几个人|几人|数据|洞察|分析|瓶颈|转化|漏斗|情况|怎么样|如何|为什么|招到|招满|到岗|停留|卡在",
    ),
]
FILLER = re.compile(
    r"帮我|帮忙|麻烦|请你|请|一下|看看|看下|这个|那个|岗位|职位|招聘|候选人|简历|的|了|吗|呢|吧|给"
)
PUNCT = re.compile(r"[\s\W_]+")
SEPARATOR = re.compile(r"[：:\n]")


def norm(text):
    return PUNCT.sub("", unicodedata.normalize("NFKC", text or "")).casefold()


def overlap(a, b):
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match().size


def after_separator(text):
    """The transcript part of "整理张三的面试记录：<原文>" — everything after the first colon/newline."""
    parts = SEPARATOR.split(text, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def rule_route(text):
    for component, pattern in RULES:
        if re.search(pattern, text, re.I):
            return Route(
                component=component,
                transcript=after_separator(text) if component == "A6" else "",
                reason="按关键词识别",
            )
    return Route(component="none", reason="没有识别到对应的 AI 任务")


def grounded(route, text):
    """Drop any mention the model did not copy from the sentence itself."""
    sentence = norm(text)
    updates = {}
    for key in ("position", "candidate", "transcript"):
        value = getattr(route, key)
        if value and norm(value) not in sentence:
            updates[key] = ""
    return route.model_copy(update=updates)


def route_text(gateway, text, action_id):
    """Return (route, source). Called with no database transaction open."""
    clean = sanitize(text)
    if gateway.configured("A0"):
        try:
            result = gateway.call("A0", {"text": clean}, action_id)
            return grounded(Route.model_validate(result["output"]), clean), "model"
        except (DomainError, ValidationError, KeyError, TypeError, ValueError):
            pass  # Fall back to rules; a router outage must not block the HR.
    return rule_route(clean), "rules"


def match_positions(positions, text, mention):
    sentence = norm(text)
    target = norm(mention) or FILLER.sub("", sentence)
    scored = []
    for p in positions:
        title = norm(p["name"])
        if not title:
            continue
        if title in sentence:
            score = 1000 + len(title)
        elif mention and target and target in title:
            score = 500 + len(target)
        else:
            score = overlap(FILLER.sub("", title), target)
            if score < 2:
                continue
        scored.append((score, p))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [p for score, p in scored if score == best]


def match_candidates(candidates, text, mention):
    sentence, mention = norm(text), norm(mention)
    hits = []
    for c in candidates:
        name = norm(c["name"])
        if len(name) < 2:
            continue
        if name in sentence or (mention and len(mention) >= 2 and (mention in name)):
            hits.append(c)
    # Prefer the longest names: "张三丰" mentioned must not also select "张三".
    if hits:
        longest = max(len(norm(c["name"])) for c in hits)
        hits = [c for c in hits if len(norm(c["name"])) == longest or norm(c["name"]) == mention]
    return hits


def option(id_, label):
    return {"id": id_, "label": label}


class Planner:
    def __init__(self, s, ctx, text, route, source):
        self.s, self.ctx, self.text, self.route, self.source = s, ctx, text, route, source
        self.positions = [p for p in s.position.editable(ctx) if p["status"] != "closed"]
        self.candidates = s.candidate.directory(ctx)
        self.pos_hits = match_positions(self.positions, text, route.position)
        self.cand_hits = match_candidates(self.candidates, text, route.candidate)

    def result(self, status, component=None, message="", options=(), job_id="", prompt=""):
        return {
            "status": status,
            "component": component,
            "component_name": NAMES.get(component, ""),
            "message": message,
            "options": list(options)[:20],
            "job_id": job_id,
            "prompt": prompt,
            "router": self.source,
            "reason": self.route.reason,
            "examples": EXAMPLES if status == "unsupported" else [],
        }

    def start(self, component, object_id, label, prompt):
        try:
            with self.s.session.begin_nested():
                job = self.s.engine.start(
                    self.ctx, StartJob(component=component, object_id=object_id, prompt=prompt)
                )
        except DomainError as exc:
            return self.result(
                "blocked",
                component,
                f"已识别为“{NAMES[component]}”（{label}），但暂时无法开始：{exc.message}",
                prompt=prompt,
            ) | {"error_code": exc.code}
        return self.result(
            "started",
            component,
            f"已开始“{NAMES[component]}”：{label}。结果生成后请核对原文证据再确认。",
            job_id=job["id"],
            prompt=prompt,
        )

    def choose(self, component, message, options, prompt):
        return self.result("choose", component, message, options, prompt=prompt)

    def plan(self):
        component = self.route.component
        if self.source == "rules" and component in POSITION_TASKS | {"none"}:
            # "张三怎么样" names a person, not a position: that is an evaluation request.
            if self.cand_hits and not self.pos_hits and component != "A1":
                component = "A5"
        if component == "none":
            return self.result(
                "unsupported",
                None,
                "没听懂要让 AI 做哪件事。可以这样说：",
            )
        prompt = self.text.strip()[:8000]
        if component in POSITION_TASKS:
            return self.position_task(component, prompt)
        if component in {"A3", "A4"}:
            return self.candidate_task(component, prompt)
        if component == "A5":
            return self.evaluation(prompt)
        return self.interview_notes()

    def position_task(self, component, prompt):
        hits = self.pos_hits
        if not hits and len(self.positions) == 1 and not self.route.position:
            hits = self.positions
        if len(hits) == 1:
            return self.start(component, hits[0]["id"], hits[0]["name"], prompt)
        if not self.positions:
            return self.result(
                "blocked", component, "你名下还没有可发起 AI 任务的岗位。", prompt=prompt
            )
        pool = hits or self.positions
        message = (
            f"有 {len(hits)} 个岗位都对得上，请选一个："
            if hits
            else "没从这句话里找到岗位名称，请选择要处理的岗位："
        )
        return self.choose(component, message, [option(p["id"], p["name"]) for p in pool], prompt)

    def candidate_task(self, component, prompt):
        hits = self.cand_hits
        if len(hits) == 1:
            return self.start(component, hits[0]["id"], hits[0]["name"], prompt)
        pool = [c for c in (hits or self.candidates) if c["usable"]]
        message = (
            "有多位同名候选人，请选择："
            if hits
            else "没从这句话里找到候选人姓名，请选择候选人，或在指令里写上姓名："
        )
        if not pool:
            return self.result("blocked", component, "没有已授权、可处理的候选人。", prompt=prompt)
        return self.choose(component, message, [option(c["id"], c["name"]) for c in pool], prompt)

    def applications(self):
        rows = []
        for c in self.cand_hits:
            for app in self.s.application.for_candidates(self.s.candidate.family(c["id"])):
                try:
                    self.s.application.authorize(self.ctx, app["id"])
                except DomainError:
                    continue
                rows.append((c, app))
        if not self.cand_hits:
            for p in self.pos_hits:
                for app in self.s.application.for_position(self.ctx, p["id"]):
                    if app["can_edit"]:
                        rows.append(({"name": app["candidate_name"]}, app))
        if self.cand_hits and self.pos_hits:
            ids = {p["id"] for p in self.pos_hits}
            rows = [(c, a) for c, a in rows if a["position_id"] in ids]
        return [(c, a) for c, a in rows if not a["outcome"]]

    def evaluation(self, prompt):
        rows = self.applications()
        ready = [(c, a) for c, a in rows if a["stage"] == "ai_eval"]
        options = [option(a["id"], f"{c['name']} · {a['position_name']}") for c, a in ready]
        if len(ready) == 1:
            return self.start("A5", ready[0][1]["id"], options[0]["label"], prompt)
        if ready:
            return self.choose("A5", "找到多条待评估的应聘记录，请选择：", options, prompt)
        if rows:
            stages = "；".join(
                f"{c['name']} · {a['position_name']}（当前：{STAGES.get(a['stage'], a['stage'])}）"
                for c, a in rows[:5]
            )
            return self.result(
                "blocked",
                "A5",
                f"证据评估只能在“AI 评估”阶段发起。{stages}。请先把应聘推进到 AI 评估阶段。",
                prompt=prompt,
            )
        if not self.cand_hits and not self.pos_hits:
            return self.result(
                "blocked",
                "A5",
                "请在指令里写上候选人姓名或岗位名称，例如“评估一下张三”。",
                prompt=prompt,
            )
        return self.result(
            "blocked", "A5", "没有找到在途的应聘记录，请先把候选人关联到岗位。", prompt=prompt
        )

    def interview_notes(self):
        transcript = (self.route.transcript or after_separator(self.text)).strip()[:8000]
        ids = {c["id"] for c in self.cand_hits}
        rows = [
            iv
            for iv in self.s.interview.list(self.ctx, mine=True)
            if iv["status"] not in {"cancelled"}
            and (not ids or iv.get("candidate_id") in ids)
            and (not self.pos_hits or iv["position_id"] in {p["id"] for p in self.pos_hits})
        ]
        options = [
            option(iv["id"], f"{iv.get('candidate_name', '')} · {iv['round_name']}") for iv in rows
        ]
        if not transcript:
            return self.result(
                "blocked",
                "A6",
                "整理面试记录需要原文。请在冒号后粘贴已获授权的面试记录，例如“整理张三的面试记录：……”。",
            )
        if len(rows) == 1:
            return self.start("A6", rows[0]["id"], options[0]["label"], transcript)
        if not rows:
            return self.result(
                "blocked", "A6", "没有找到你担任面试官的对应面试。", prompt=transcript
            )
        return self.choose("A6", "找到多场面试，请选择要整理的一场：", options, transcript)


def plan(s, ctx, text, route, source):
    s.candidate.authorize(ctx)
    return Planner(s, ctx, text, route, source).plan()
