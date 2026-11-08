"""Conversational HR assistant: one chat box for questions, AI tasks and everyday actions.

The assistant understands a sentence (A0 router model, or keyword rules without it),
resolves the people and positions it names among the records the requester may see,
and answers with structured blocks the HR web renders as a chat reply.

Three kinds of answers, with the same safety rules as the rest of the system:

* Questions ("今天有什么要处理", "张三到哪一步了") are answered from the existing
  read facades, so every row passes the usual visibility checks. No model writes the
  numbers; they are copied from the records.
* AI work (A1–A7) is planned by the existing natural-language planner and runs as a
  normal reviewed job.
* Business changes (推进、淘汰、关联岗位、发消息、处理决策卡) are never executed here.
  The assistant returns a confirmation card carrying the exact, versioned command; the
  browser sends it to the existing endpoint only after the HR presses confirm, so
  permissions, idempotency, optimistic locking and audit are unchanged.
"""

import re
from datetime import datetime, timedelta

from app.engine.agent_views import MoreViews, week_trend
from app.engine.context import sanitize
from app.engine.contracts import AgentRoute, AgentStep, Route
from app.engine.intent import (
    NAMES,
    STAGES,
    Planner,
    after_separator,
    match_candidates,
    match_positions,
    norm,
)
from app.engine.intent import RULES as TASK_PATTERNS
from app.engine.tools import CAPABILITIES, POST_RULES, PRE_RULES
from app.kernel.types import DomainError

NEXT_STAGE = {"reach": "talking", "talking": "ai_eval", "ai_eval": "interview"}
INTERVIEW_STATES = {
    "waiting": "待约时间",
    "offered": "已发可选时段",
    "scheduled": "已约定",
    "awaiting_feedback": "待提交面评",
    "no_show": "未到场",
    "completed": "已完成",
    "cancelled": "已取消",
}
REQUISITION_STATES = {
    "draft": "草稿",
    "in_approval": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已撤回",
    "pending_confirmation": "待经理确认",
}
POSITION_STATES = {
    "to_publish": "待发布",
    "open": "招聘中",
    "paused": "已暂停",
    "closed": "已关闭",
}
HIRE_STATES = {
    "deciding": "待经理决定",
    "pending": "审批中",
    "approved": "已录用 · 待移交",
    "handed_over": "已移交",
    "accepted": "已接受",
    "joined": "已入职",
    "declined": "未接受",
    "no_show": "未入职",
    "rejected": "不录用",
    "cancelled": "流程已变更",
}
CARD_OPTIONS = {
    "reject": "确认淘汰",
    "terminate": "终止本次应聘",
    "keep": "保留当前流程",
    "dismiss": "已阅，关闭提醒",
}
JOB_STATES = {"review": "待复核", "queued": "排队中", "running": "生成中", "retry": "等待重试"}

HELP_SUGGESTIONS = ["今天有什么要处理", "岗位招聘进度", "看看招聘漏斗", "最近的面试安排"]

# Offers and pay are decided by people in the hiring flow; the assistant declines them before
# the "录用|offer" read rule can turn "给张三发offer，月薪两万" into a hires listing. Looking
# up a salary band ("客服的薪资带宽是多少") is a read and stays allowed.
OUT_OF_SCOPE = re.compile(
    r"(发|给|开|谈|出).{0,8}(offer|录用通知)|定薪|谈薪|调薪|涨薪"
    r"|(月薪|年薪|薪资|工资)(定|开|给|谈|为|是)?\s*(\d|[一二两三四五六七八九十]+\s*[万千kK])"
    r"|(决定|批准|同意)录用|删除.{0,8}(候选人|档案|数据)",
    re.I,
)
REFUSAL = (
    "发 offer、定薪资、录用决定和删除数据要由 HR 在对应流程里亲自操作，我不能代办。"
    "我可以帮你看录用待办、候选人进展或薪资带宽。"
)
# "客服专员还差几个人，再看看张三到哪一步了" asks two things.
CLAUSE = re.compile(
    r"[，,；;。]\s*(?:然后|再|另外|顺便|同时|并且|还有|以及)|(?:然后再|顺便再|另外再)"
)
TASK_RULES = [(c, p) for c, p in TASK_PATTERNS if c != "A7"]
PRONOUN_PERSON = re.compile(r"他|她|ta|TA|此人|这个人|这位|该候选人|这个候选人|这名候选人")
PRONOUN_POSITION = re.compile(r"这个岗位|该岗位|这个职位|该职位|这岗位")
SKILL = re.compile(r"(?:会|懂|熟悉|精通|擅长|做过|有)([^\s，。,？?的]{1,20})(?:的|经验)")
QUOTED = re.compile(r"[“\"「](.{1,30}?)[”\"」]")


def message_content(text):
    """The words to send: after a colon, or after "说/告诉…" in "跟张三说一声…"."""
    content = after_separator(text)
    if not content:
        m = re.search(r"(?:说|告诉[^，。,]{0,12}?)[，, ]?(.{2,})$", text)
        content = m.group(1).strip() if m else ""
    return re.sub(r"^(一声|一下|下)[，,：: ]?", "", content).strip()


def rule_step(text):
    for intent, pattern in [*PRE_RULES, *TASK_RULES, *POST_RULES]:
        if re.search(pattern, text, re.I):
            content = ""
            if intent == "A6":
                content = after_separator(text)
            elif intent == "message":
                content = message_content(text)
            return AgentRoute(intent=intent, content=content, reason="按关键词识别")
    return AgentRoute(intent="none", reason="没有识别到对应的操作")


def agent_rule_route(text):
    if OUT_OF_SCOPE.search(text):
        return AgentRoute(intent="none", reason=REFUSAL)
    whole = rule_step(text)
    if whole.intent in {"message", "A6"}:
        return whole  # The words after the colon are content, not another request.
    parts = [p.strip() for p in CLAUSE.split(text) if p and p.strip()]
    if len(parts) < 2:
        return whole
    steps = [rule_step(p) for p in parts[:3]]
    if any(st.intent == "none" for st in steps):
        return whole
    first, rest = steps[0], steps[1:]
    return first.model_copy(
        update={"then": [AgentStep(**st.model_dump(exclude={"reason", "then"})) for st in rest]}
    )


def to_agent_route(output):
    """Accept both the assistant router schema and the older A1–A7-only router schema."""
    if "intent" in output:
        return AgentRoute.model_validate(output)
    old = Route.model_validate(output)
    return AgentRoute(
        intent=old.component,
        position=old.position,
        candidate=old.candidate,
        content=old.transcript,
        reason=old.reason,
    )


def grounded(route, text):
    """Drop every mention the model did not copy from the sentence itself."""
    sentence = norm(text)

    def clean(step):
        updates = {}
        for key in ("position", "candidate", "keyword", "content"):
            value = getattr(step, key)
            if value and norm(value) not in sentence:
                updates[key] = ""
        return step.model_copy(update=updates)

    first = clean(route)
    return first.model_copy(update={"then": [clean(st) for st in route.then]})


def route_agent(gateway, text, action_id):
    """Return (route, source). Called with no database transaction open."""
    clean = sanitize(text)
    if gateway.configured("A0"):
        try:
            result = gateway.call("A0", {"text": clean}, action_id)
            return grounded(to_agent_route(result["output"]), clean), "model"
        except (DomainError, ValueError, KeyError, TypeError):
            pass  # A router outage must not block the HR; rules still work.
    return agent_rule_route(clean), "rules"


def item(id_, title, subtitle="", meta="", href="", tag="", tone="", **extra):
    return {
        "id": id_,
        "title": title,
        "subtitle": subtitle,
        "meta": meta,
        "href": href,
        "tag": tag,
        "tone": tone,
        **extra,
    }


def short_time(value):
    return value[5:16].replace("T", " ") if value else ""


class Assistant(MoreViews):
    item = staticmethod(item)
    short = staticmethod(short_time)

    @staticmethod
    def position_state(status):
        return POSITION_STATES.get(status, status)

    def __init__(self, s, ctx, text, route, source, focus):
        self.s, self.ctx, self.text, self.source = s, ctx, text, source
        self.route = route
        self.positions = [p for p in s.position.editable(ctx) if p["status"] != "closed"]
        self.candidates = s.candidate.directory(ctx)
        focus = focus or {}
        if not route.candidate and PRONOUN_PERSON.search(text):
            known = next((c for c in self.candidates if c["id"] == focus.get("candidate_id")), None)
            if known:
                self.route = self.route.model_copy(update={"candidate": known["name"]})
        if not self.route.position and PRONOUN_POSITION.search(text):
            known = next((p for p in self.positions if p["id"] == focus.get("position_id")), None)
            if known:
                self.route = self.route.model_copy(update={"position": known["name"]})
        self.pos_hits = match_positions(self.positions, text, self.route.position)
        self.cand_hits = match_candidates(self.candidates, text, self.route.candidate)
        self.focus = {}
        if len(self.cand_hits) == 1:
            self.focus.update(
                candidate_id=self.cand_hits[0]["id"], candidate_name=self.cand_hits[0]["name"]
            )
        if len(self.pos_hits) == 1 and self.pos_hits[0]["name"] and self.mentions_position():
            self.focus.update(
                position_id=self.pos_hits[0]["id"], position_name=self.pos_hits[0]["name"]
            )

    def mentions_position(self):
        sentence = norm(self.text)
        return bool(self.route.position) or any(norm(p["name"]) in sentence for p in self.pos_hits)

    # ----- response helpers -------------------------------------------------------

    def answer(self, intent, reply, blocks=(), suggestions=()):
        return {
            "intent": intent,
            "router": self.source,
            "reason": self.route.reason,
            "reply": reply,
            "blocks": [b for b in blocks if b],
            "suggestions": list(dict.fromkeys(suggestions))[:4],
            "focus": self.focus,
        }

    def person_suggestions(self, name):
        return [f"{name}到哪一步了", f"评估一下{name}", f"帮我回复{name}的消息"]

    # ----- dispatch -------------------------------------------------------------------

    def run(self):
        intent = self.route.intent
        if OUT_OF_SCOPE.search(self.text):
            intent = "none"
        elif self.source == "rules":
            # "张三怎么样" names a person: answer with that person, not a position overview.
            if intent in {"positions", "overview", "none", "candidates"} and (
                self.cand_hits and not self.mentions_position()
            ):
                intent = "candidate"
            # "客服专员怎么样" names a position.
            if intent in {"candidate", "none"} and not self.cand_hits and self.mentions_position():
                intent = "positions"
            if intent == "candidate" and not self.cand_hits and not self.route.candidate:
                intent = "none"
        handler = {
            "help": self.help,
            "none": self.unknown,
            "overview": self.overview,
            "positions": self.position_status,
            "candidates": self.candidate_search,
            "candidate": self.candidate_status,
            "interviews": self.interviews,
            "hires": self.hires,
            "reviews": self.reviews,
            "requisitions": self.requisitions,
            "attach": self.attach,
            "advance": self.advance,
            "reject": self.reject,
            "message": self.message,
            "pipeline": self.pipeline,
            "stats": self.stats,
            "conversation": self.conversation,
            "cards": self.cards,
            "headcount": self.headcount,
            "salary": self.salary,
            "automation": self.automation,
            "org": self.org,
            "key": self.key,
            "tag": self.tag,
            "take_over": self.take_over,
            "hand_back": self.hand_back,
            "restore": self.restore,
            "pause": self.pause,
            "resume": self.resume,
        }.get(intent)
        if handler:
            return handler()
        return self.task(intent)

    # ----- conversation -----------------------------------------------------------------

    def help(self):
        return self.answer(
            "help",
            f"你好，{self.ctx.principal.name}。我是 AI 招聘助手，大部分招聘工作都可以直接跟我说。"
            "查询会立刻回答；需要 AI 生成的内容会进入复核；推进、淘汰、发消息这类操作会先给你确认卡片，确认后才执行。",
            [
                {
                    "type": "list",
                    "title": "可以这样跟我说",
                    "items": [item(k, k, v) for k, v in CAPABILITIES],
                }
            ],
            HELP_SUGGESTIONS,
        )

    def unknown(self):
        if OUT_OF_SCOPE.search(self.text):
            return self.answer("none", REFUSAL, [], ["录用待办", "今天有什么要我处理的"])
        return self.answer(
            "none",
            "这句话我还没理解要做什么。可以问我进展、让 AI 写东西或评估，也可以让我推进流程。",
            [
                {
                    "type": "list",
                    "title": "可以这样跟我说",
                    "items": [item(k, k, v) for k, v in CAPABILITIES],
                }
            ],
            HELP_SUGGESTIONS,
        )

    # ----- read-only answers ----------------------------------------------------------

    def review_jobs(self):
        try:
            return [j for j in self.s.engine.listing(self.ctx) if j["status"] in JOB_STATES]
        except DomainError:
            return []

    def label_job(self, job):
        name = NAMES.get(job["component"], job["component"])
        target = ""
        if job["component"] in {"A1", "A2", "A7"}:
            target = next((p["name"] for p in self.positions if p["id"] == job["object_id"]), "")
        else:
            target = next((c["name"] for c in self.candidates if c["id"] == job["object_id"]), "")
        return name, target

    def job_items(self, jobs):
        rows = []
        for j in jobs:
            name, target = self.label_job(j)
            rows.append(
                item(
                    j["id"],
                    f"{name}{' · ' + target if target else ''}",
                    "",
                    short_time(j["updated_at"]),
                    "",
                    JOB_STATES.get(j["status"], j["status"]),
                    "ai" if j["status"] == "review" else "",
                    job_id=j["id"],
                )
            )
        return rows

    def card_items(self, cards):
        rows = []
        for c in cards:
            actions = [
                {
                    "label": CARD_OPTIONS.get(o, o),
                    "action": {
                        "kind": "card",
                        "card_id": c["id"],
                        "expected_version": c["version"],
                        "option": o,
                    },
                    "danger": o in {"reject", "terminate"},
                }
                for o in c["options"]
            ]
            rows.append(
                item(
                    c["id"],
                    c["title"],
                    "已超时" if c["overdue"] else "",
                    ("截止 " + short_time(c["due_at"])) if c["due_at"] else "",
                    c["href"],
                    "已超时" if c["overdue"] else "待处理",
                    "danger" if c["overdue"] else "warning",
                    actions=actions,
                )
            )
        return rows

    def overview(self):
        wb = self.s.query.workbench(self.ctx)
        counts = wb["counts"]
        jobs = self.review_jobs()
        reviews = [j for j in jobs if j["status"] == "review"]
        interviews = [
            iv
            for iv in self.s.interview.list(self.ctx)
            if iv["status"] in {"waiting", "offered", "scheduled", "awaiting_feedback"}
        ]
        hires = [h for h in wb["hires"] if h["can_handover"] or h["can_result"] or h["can_approve"]]
        todo = len(wb["cards"]) + len(reviews) + len(hires)
        tight = sorted(
            (p for p in wb["positions"] if p["status"] == "open" and p["remaining"]),
            key=lambda p: -p["remaining"],
        )
        parts = [
            f"{n} {label}"
            for n, label in (
                (len(wb["cards"]), "张决策卡待你决定"),
                (len(reviews), "个 AI 结果待复核"),
                (len(hires), "个录用待办"),
            )
            if n
        ]
        reply = (
            f"{self.ctx.principal.name}，你现在有 {todo} 件事要处理：{'、'.join(parts)}。"
            if todo
            else f"{self.ctx.principal.name}，目前没有需要你处理的待办。"
        ) + f"在招岗位 {counts['open_positions']} 个，还差 {counts['remaining']} 人。"
        if interviews:
            reply += f"进行中的面试 {len(interviews)} 场。"
        blocks = [
            {
                "type": "metrics",
                "items": [
                    {"label": "在招岗位", "value": counts["open_positions"]},
                    {"label": "还差人数", "value": counts["remaining"]},
                    {
                        "label": "待处理决策",
                        "value": len(wb["cards"]),
                        "tone": "warning" if wb["cards"] else "",
                    },
                    {"label": "AI 待复核", "value": len(reviews), "tone": "ai" if reviews else ""},
                    {"label": "进行中面试", "value": len(interviews)},
                    {"label": "录用待办", "value": len(hires)},
                ],
            },
        ]
        if todo:
            blocks.append(
                {
                    "type": "stack",
                    "title": "待办构成",
                    "items": [
                        {"label": label, "value": n, "tone": tone}
                        for label, n, tone in (
                            ("决策卡", len(wb["cards"]), "warning"),
                            ("AI 待复核", len(reviews), "ai"),
                            ("录用待办", len(hires), "brand"),
                        )
                        if n
                    ],
                }
            )
        opened = [p for p in wb["positions"] if p["status"] == "open"]
        if opened:
            blocks.append(
                self.progress_block(
                    sorted(opened, key=lambda p: -p["remaining"])[:6], "在招岗位进度"
                )
            )
        if wb["cards"]:
            blocks.append(
                {
                    "type": "list",
                    "title": "等你决定",
                    "items": self.card_items(wb["cards"][:5]),
                    "more_href": "/workbench" if len(wb["cards"]) > 5 else "",
                }
            )
        if reviews:
            blocks.append(
                {
                    "type": "list",
                    "title": "AI 结果待复核",
                    "items": self.job_items(reviews[:5]),
                    "more_href": "/ai-jobs" if len(reviews) > 5 else "",
                }
            )
        if hires:
            blocks.append(
                {
                    "type": "list",
                    "title": "录用待办",
                    "items": [
                        item(
                            h["id"],
                            f"{h['candidate_name']} · {h['position_name']}",
                            "",
                            "",
                            f"/hiring/{h['id']}",
                            HIRE_STATES.get(h["status"], h["status"]),
                            "warning",
                        )
                        for h in hires[:5]
                    ],
                }
            )
        suggestions = []
        if tight:
            suggestions.append(f"分析{tight[0]['name']}的招聘瓶颈")
        suggestions += ["最近的面试安排", "岗位招聘进度"]
        return self.answer("overview", reply, blocks, suggestions)

    def position_card(self, p):
        stages = p["candidateCounts"]["stages"]
        remaining = max(0, p["planned"] - p["hired"])
        return [
            {
                "type": "metrics",
                "title": p["name"],
                "href": f"/positions/{p['id']}",
                "items": [
                    {"label": "计划招聘", "value": p["planned"]},
                    {"label": "已录用", "value": p["hired"]},
                    {
                        "label": "还差",
                        "value": remaining,
                        "tone": "warning" if remaining else "success",
                    },
                    {"label": "在途候选人", "value": p["candidateCounts"]["active"]},
                ],
            },
            {
                "type": "funnel",
                "items": [
                    {"label": STAGES[k], "value": stages.get(k, 0)}
                    for k in ("reach", "talking", "ai_eval", "interview", "manager_eval")
                ],
            },
        ]

    def position_status(self):
        if len(self.pos_hits) == 1 and self.mentions_position():
            p = self.s.position.get(self.ctx, self.pos_hits[0]["id"])
            remaining = max(0, p["planned"] - p["hired"])
            stages = p["candidateCounts"]["stages"]
            busiest = max(
                ("reach", "talking", "ai_eval", "interview", "manager_eval"),
                key=lambda k: stages.get(k, 0),
            )
            reply = (
                f"{p['name']}（{POSITION_STATES.get(p['status'], p['status'])}）计划招 {p['planned']} 人，"
                f"已录用 {p['hired']} 人，还差 {remaining} 人。"
                + (
                    f"在途 {p['candidateCounts']['active']} 人，最多的停在“{STAGES[busiest]}”阶段（{stages.get(busiest, 0)} 人）。"
                    if p["candidateCounts"]["active"]
                    else "目前没有在途候选人。"
                )
                + (f"期望到岗：{p['expectedOnboard']}。" if p.get("expectedOnboard") else "")
            )
            blocks = self.position_card(p)
            blocks.insert(1, self.progress_block([p], "招聘进度"))
            m = self.s.application.insight_metrics(p["id"])
            stale = {k: v for k, v in m["stale"].items() if v}
            if stale:
                blocks.append(
                    {
                        "type": "bar",
                        "title": f"超过 {m['stale_days']} 天没有进展",
                        "unit": "人",
                        "items": [
                            {"label": STAGES[k], "value": v, "tone": "warning"}
                            for k, v in stale.items()
                        ],
                    }
                )
                reply += f"有 {sum(stale.values())} 人超过 {m['stale_days']} 天没有进展。"
            blocks.append(
                {
                    "type": "trend",
                    "title": "每周新进入流程的人数",
                    "unit": "人",
                    "items": week_trend(
                        [
                            datetime.fromisoformat(a["started_at"]).date()
                            for a in self.s.application.for_position(self.ctx, p["id"])
                        ],
                        self.today(),
                    ),
                }
            )
            return self.answer(
                "positions",
                reply,
                blocks,
                [
                    f"分析{p['name']}的招聘瓶颈",
                    f"给{p['name']}出一份人才搜索关键词",
                    f"帮{p['name']}写一版 JD",
                ],
            )
        rows = self.s.query.workbench(self.ctx)["positions"]
        if self.pos_hits and self.mentions_position():
            ids = {p["id"] for p in self.pos_hits}
            rows = [p for p in rows if p["id"] in ids] or rows
        open_rows = [p for p in rows if p["status"] == "open"]
        reply = (
            f"你能看到 {len(rows)} 个在招或待发布的岗位，招聘中的 {len(open_rows)} 个合计还差 "
            f"{sum(p['remaining'] for p in open_rows)} 人。"
            if rows
            else "你名下还没有在招岗位。招聘需求审批通过后会自动生成岗位。"
        )
        items = [
            item(
                p["id"],
                p["name"],
                f"计划 {p['planned']} · 已录用 {p['hired']} · 沟通 {p['stages'].get('talking', 0)} · 评估 {p['stages'].get('ai_eval', 0)} · 面试 {p['stages'].get('interview', 0)}",
                f"还差 {p['remaining']} 人",
                f"/positions/{p['id']}",
                POSITION_STATES.get(p["status"], p["status"]),
                "warning" if p["remaining"] else "success",
                ask=f"{p['name']}还差几个人",
            )
            for p in sorted(rows, key=lambda p: -p["remaining"])[:10]
        ]
        top = max(open_rows, key=lambda p: p["remaining"], default=None)
        return self.answer(
            "positions",
            reply,
            [
                self.progress_block(sorted(rows, key=lambda p: -p["remaining"])[:10]),
                {"type": "list", "title": "各阶段人数", "items": items, "more_href": "/positions"},
            ],
            [f"分析{top['name']}的招聘瓶颈"] if top else ["查看招聘需求"],
        )

    def candidate_rows(self, rows):
        out = []
        for c in rows:
            active = [a for a in c["applications"] if not a["outcome"]]
            subtitle = " · ".join(
                x for x in (c["profile"].get("title"), c["profile"].get("city")) if x
            )
            out.append(
                item(
                    c["id"],
                    c["profile"]["name"],
                    subtitle or (c["profile"].get("skills") or "")[:40],
                    "、".join(a["position_name"] for a in active[:2]) or "暂无在途应聘",
                    f"/candidates/{c['id']}",
                    "未授权"
                    if c["consent"] != "granted"
                    else ("重点" if c["key_candidate"] else ""),
                    "warning" if c["consent"] != "granted" else "",
                    ask=f"{c['profile']['name']}到哪一步了",
                )
            )
        return out

    def candidate_search(self):
        keyword = self.route.keyword
        if not keyword:
            m = QUOTED.search(self.text) or SKILL.search(self.text)
            keyword = m.group(1) if m else ""
        result = self.s.candidate.search(self.ctx, 1, 8, query=keyword)
        if keyword:
            reply = (
                f"找到 {result['total']} 位与“{keyword}”相关的候选人"
                + ("，先列出最近的 8 位。" if result["total"] > 8 else "。")
                if result["total"]
                else f"候选人库里还没有与“{keyword}”相关的人。可以让 AI 给岗位出一份人才搜索关键词，去外部渠道找人。"
            )
        else:
            reply = f"候选人库共 {result['total']} 人，这是最近加入的几位。要按技能找，可以说“找会 Excel 的候选人”。"
        return self.answer(
            "candidates",
            reply,
            [
                {
                    "type": "list",
                    "title": "候选人",
                    "items": self.candidate_rows(result["items"]),
                    "more_href": "/candidates" + (f"?q={keyword}" if keyword else ""),
                }
            ]
            if result["items"]
            else [],
            self.person_suggestions(result["items"][0]["profile"]["name"])
            if result["items"]
            else [],
        )

    def which_candidate(self, intent, verb):
        """Return the single matched candidate, or a reply asking which one."""
        if len(self.cand_hits) == 1:
            return self.cand_hits[0], None
        if self.cand_hits:
            return None, self.answer(
                intent,
                f"有 {len(self.cand_hits)} 位候选人都叫这个名字，请先确认是哪一位，再告诉我{verb}。",
                [
                    {
                        "type": "list",
                        "title": "同名候选人",
                        "items": self.candidate_rows(
                            [self.s.candidate.get(self.ctx, c["id"]) for c in self.cand_hits[:8]]
                        ),
                    }
                ],
            )
        return None, self.answer(
            intent,
            f"没从这句话里找到候选人姓名。请写上姓名，例如“{verb}张三”。",
            [],
            ["找会 Excel 的候选人"],
        )

    def candidate_status(self):
        hit, reply = self.which_candidate("candidate", "查看")
        if reply:
            return reply
        c = self.s.candidate.get(self.ctx, hit["id"])
        name = c["profile"]["name"]
        apps = [a for a in c["applications"] if not a.get("restricted")]
        active = [a for a in apps if not a["outcome"]]
        ivs = [
            iv
            for iv in self.s.interview.list(self.ctx, candidate_id=c["id"])
            if iv["status"] not in {"cancelled"}
        ]
        parts = []
        for a in active:
            parts.append(f"{a['position_name']}：{STAGES.get(a['stage'], a['stage'])}")
        reply = f"{name}" + (
            f"目前有 {len(active)} 条在途应聘（{'；'.join(parts)}）。"
            if active
            else "目前没有在途应聘。"
        )
        if c["consent"] != "granted":
            reply += "还没有取得候选人授权，AI 任务和沟通暂时不能进行。"
        if c["do_not_contact"]:
            reply += "候选人要求不再联系。"
        profile = c["profile"]
        facts = [
            {"label": k, "value": profile.get(f) or "—"}
            for k, f in (
                ("城市", "city"),
                ("当前公司", "company"),
                ("职位", "title"),
                ("学历", "degree"),
                ("技能", "skills"),
            )
        ]
        blocks = [
            {
                "type": "profile",
                "title": name,
                "href": f"/candidates/{c['id']}",
                "tags": [
                    t
                    for t in (
                        "已授权" if c["consent"] == "granted" else "未授权",
                        "重点候选人" if c["key_candidate"] else "",
                        "不再联系" if c["do_not_contact"] else "",
                        *c["tags"],
                    )
                    if t
                ],
                "items": facts,
            },
            {
                "type": "list",
                "title": "应聘记录",
                "items": [
                    item(
                        a["id"],
                        a["position_name"],
                        f"进入时间 {a['started_at'][:10]}",
                        "",
                        f"/positions/{a['position_id']}",
                        STAGES.get(a["stage"], a["stage"]) if not a["outcome"] else "已结束",
                        "brand" if not a["outcome"] else "",
                    )
                    for a in apps
                ],
            }
            if apps
            else None,
            {
                "type": "list",
                "title": "面试",
                "items": [
                    item(
                        iv["id"],
                        f"{iv['position_name']} · {iv['round_name']}",
                        short_time(iv["start"]) or "时间待定",
                        "",
                        f"/interviews/{iv['id']}",
                        INTERVIEW_STATES.get(iv["status"], iv["status"]),
                    )
                    for iv in ivs[:5]
                ],
            }
            if ivs
            else None,
        ]
        for a in active[:2]:
            blocks.insert(
                1,
                {
                    "type": "timeline",
                    "title": f"{a['position_name']} · 应聘进程",
                    "items": self.journey(self.s.application.get(self.ctx, a["id"])),
                },
            )
        suggestions = []
        if any(a["stage"] == "ai_eval" for a in active):
            suggestions.append(f"评估一下{name}")
        if any(a["stage"] in NEXT_STAGE for a in active):
            suggestions.append(f"推进{name}")
        if not active and self.positions:
            suggestions.append(f"把{name}加到{self.positions[0]['name']}岗位")
        suggestions += [f"帮我回复{name}的消息", f"提取{name}的简历信息"]
        return self.answer("candidate", reply, blocks, suggestions)

    def period(self):
        """(from, to, label) for 今天/明天/本周/下周 in the sentence or keyword."""
        word = self.route.keyword + self.text
        today = self.today()
        monday = today - timedelta(days=today.weekday())
        for keys, lo, hi, label in (
            (("今天", "今日"), today, today + timedelta(days=1), "今天"),
            (("明天",), today + timedelta(days=1), today + timedelta(days=2), "明天"),
            (("后天",), today + timedelta(days=2), today + timedelta(days=3), "后天"),
            (("下周",), monday + timedelta(days=7), monday + timedelta(days=14), "下周"),
            (("本周", "这周", "这个星期"), monday, monday + timedelta(days=7), "本周"),
        ):
            if any(k in word for k in keys):
                return lo, hi, label
        return None

    def interviews(self):
        mine = bool(re.search(r"我的|我要面|我面试", self.text))
        rows = self.s.interview.list(self.ctx, mine=mine)
        if self.cand_hits:
            ids = {c["id"] for c in self.cand_hits}
            rows = [iv for iv in rows if iv.get("candidate_id") in ids]
        if self.pos_hits and self.mentions_position():
            pids = {p["id"] for p in self.pos_hits}
            rows = [iv for iv in rows if iv["position_id"] in pids]
        active = [iv for iv in rows if iv["status"] not in {"cancelled", "completed", "no_show"}]
        period = self.period()
        if period:
            lo, hi, label = period
            active = [
                iv
                for iv in active
                if iv["start"] and lo <= datetime.fromisoformat(iv["start"]).date() < hi
            ]
        scheduled = [iv for iv in active if iv["status"] == "scheduled"]
        waiting = [iv for iv in active if iv["status"] in {"waiting", "offered"}]
        feedback = [iv for iv in active if iv["status"] == "awaiting_feedback"]
        when = period[2] if period else ""
        reply = (
            f"{when}共有 {len(active)} 场进行中的面试：已约定 {len(scheduled)} 场，待约时间 {len(waiting)} 场，待提交面评 {len(feedback)} 场。"
            if active
            else f"{when}没有进行中的面试。"
            + ("" if when else "候选人推进到“面试”阶段后会自动生成面试轮次。")
        )
        today = self.today()
        days = [today + timedelta(days=i) for i in range(7)]
        per_day = [
            sum(
                1
                for iv in active
                if iv["start"] and datetime.fromisoformat(iv["start"]).date() == d
            )
            for d in days
        ]
        chart = (
            {
                "type": "bar",
                "title": "未来 7 天已约定的面试",
                "unit": "场",
                "items": [
                    {"label": d.strftime("%m-%d") + ("（今天）" if i == 0 else ""), "value": n}
                    for i, (d, n) in enumerate(zip(days, per_day, strict=True))
                ],
            }
            if any(per_day)
            else None
        )
        items = [
            item(
                iv["id"],
                f"{iv.get('candidate_name', '')} · {iv['round_name']}",
                iv["position_name"],
                short_time(iv["start"]) or "时间待定",
                f"/interviews/{iv['id']}",
                INTERVIEW_STATES.get(iv["status"], iv["status"]),
                "warning" if iv["status"] in {"waiting", "awaiting_feedback"} else "brand",
            )
            for iv in active[:10]
        ]
        return self.answer(
            "interviews",
            reply,
            [chart, {"type": "list", "title": "面试", "items": items, "more_href": "/interviews"}]
            if items
            else [],
            ["整理面试记录：（粘贴记录原文）"] if feedback else ["今天有什么要处理"],
        )

    def hires(self):
        rows = self.s.hiring.listing(self.ctx)
        if self.cand_hits:
            ids = {c["id"] for c in self.cand_hits}
            rows = [h for h in rows if h["candidate_id"] in ids]
        todo = [h for h in rows if h["can_handover"] or h["can_result"] or h["can_approve"]]
        reply = (
            f"录用流程中共 {len(rows)} 条记录，其中 {len(todo)} 条需要你处理。"
            "录用决定、审批和移交需要在录用详情里核对面评后完成，我不会替你做录用决定。"
            if rows
            else "目前还没有进入录用环节的候选人。面试全部完成后会自动进入录用评估。"
        )
        items = [
            item(
                h["id"],
                f"{h['candidate_name']} · {h['position_name']}",
                "面评均分 " + "，".join(f"{k} {v}" for k, v in h["averages"].items())
                if h["averages"]
                else "",
                "",
                f"/hiring/{h['id']}",
                HIRE_STATES.get(h["status"], h["status"]),
                "warning" if h in todo else "",
            )
            for h in rows[:10]
        ]
        blocks = (
            [{"type": "list", "title": "录用", "items": items, "more_href": "/hiring"}]
            if items
            else []
        )
        if len(rows) == 1 and self.cand_hits:
            h = rows[0]
            states = {"approved": "done", "rejected": "bad", "pending": "current"}
            steps = [
                {
                    "time": "",
                    "title": "用人经理录用决定",
                    "subtitle": "",
                    "state": "current" if h["status"] == "deciding" else "done",
                }
            ]
            steps += [
                {
                    "time": "",
                    "title": f"审批：{n['name']}",
                    "subtitle": {"approved": "已通过", "rejected": "已驳回"}.get(
                        n["status"], "待审批"
                    ),
                    "state": states.get(n["status"], "todo")
                    if h["status"] == "pending" or n["status"] != "pending"
                    else "todo",
                }
                for n in h["chain"]
            ]
            for status, title in (("handed_over", "移交入职"), ("joined", "已入职")):
                steps.append(
                    {
                        "time": "",
                        "title": title,
                        "subtitle": "",
                        "state": "done"
                        if list(HIRE_STATES).index(h["status"]) >= list(HIRE_STATES).index(status)
                        and h["status"] not in {"declined", "no_show", "rejected", "cancelled"}
                        else "todo",
                    }
                )
            blocks.insert(
                0,
                {
                    "type": "timeline",
                    "title": f"{h['candidate_name']} · {h['position_name']} 录用进程",
                    "items": steps,
                },
            )
        return self.answer("hires", reply, blocks, ["今天有什么要处理"])

    def reviews(self):
        jobs = self.review_jobs()
        review = [j for j in jobs if j["status"] == "review"]
        running = [j for j in jobs if j["status"] != "review"]
        reply = (
            f"有 {len(review)} 个 AI 结果等你复核"
            + (f"，另有 {len(running)} 个正在生成" if running else "")
            + "。点开即可在对话里核对证据并确认。"
            if review or running
            else "没有待复核的 AI 结果。"
        )
        return self.answer(
            "reviews",
            reply,
            [
                {
                    "type": "list",
                    "title": "AI 任务",
                    "items": self.job_items((review + running)[:10]),
                    "more_href": "/ai-jobs",
                }
            ]
            if jobs
            else [],
            HELP_SUGGESTIONS[:2],
        )

    def requisitions(self):
        try:
            result = self.s.requisition.search(self.ctx, {}, (1, 10))
        except DomainError as exc:
            return self.answer("requisitions", f"暂时不能查看招聘需求：{exc.message}")
        rows = result["items"]
        sentence = norm(self.text)
        named = [
            r
            for r in rows
            if norm(r["title"]) in sentence
            or (self.route.keyword and self.route.keyword in r["title"])
        ]
        if len(named) == 1:
            return self.requisition_detail(named[0]["id"])
        waiting = [r for r in rows if r["status"] == "in_approval"]
        reply = (
            f"最近 {len(rows)} 条招聘需求中，{len(waiting)} 条在审批中。"
            if rows
            else "还没有招聘需求。"
        )
        items = [
            item(
                r["id"],
                f"{r['title']} · {r['headcount']} 人",
                r["dept"],
                f"等待 {r['waitingFor']} {r['waitingDays']} 天" if r["waitingFor"] else "",
                f"/requisitions/{r['id']}",
                REQUISITION_STATES.get(r["status"], r["status"]),
                "warning" if r["status"] == "in_approval" else "",
            )
            for r in rows
        ]
        return self.answer(
            "requisitions",
            reply,
            [
                {
                    "type": "stack",
                    "title": "需求状态",
                    "items": [
                        {
                            "label": REQUISITION_STATES.get(k, k),
                            "value": sum(r["status"] == k for r in rows),
                            "tone": "warning"
                            if k == "in_approval"
                            else "success"
                            if k == "approved"
                            else "",
                        }
                        for k in dict.fromkeys(r["status"] for r in rows)
                    ],
                },
                {
                    "type": "list",
                    "title": "招聘需求",
                    "items": items,
                    "more_href": "/requisitions",
                },
            ]
            if items
            else [],
            [f"{waiting[0]['title']}审批到哪了"] if waiting else ["岗位招聘进度"],
        )

    def requisition_detail(self, rid):
        r = self.s.requisition.get(self.ctx, rid)
        status = REQUISITION_STATES.get(r["status"], r["status"])
        steps = [
            {
                "time": (r.get("submittedAt") or "")[:10],
                "title": "提交需求",
                "subtitle": r["initiator"],
                "state": "done" if r["status"] != "draft" else "current",
            }
        ]
        for i, node in enumerate(r["chain"]):
            if r["status"] == "approved" or i < r["currentNode"]:
                state = "done"
            elif i == r["currentNode"] and r["status"] == "in_approval":
                state = "current"
            elif i == r["currentNode"] and r["status"] == "rejected":
                state = "bad"
            else:
                state = "todo"
            steps.append(
                {
                    "time": "",
                    "title": f"{node['name']}：{node['approver']}",
                    "subtitle": (
                        f"已等待 {r['waitingDays']} 天"
                        if state == "current" and r["waitingDays"]
                        else ""
                    ),
                    "state": state,
                }
            )
        steps.append(
            {
                "time": "",
                "title": "生成岗位",
                "subtitle": "",
                "state": "done" if r["status"] == "approved" else "todo",
            }
        )
        reply = f"“{r['title']}”（{r['dept']}，{r['headcount']} 人）当前{status}。"
        if r["status"] == "in_approval" and r.get("waitingFor"):
            reply += f"正在等 {r['waitingFor']} 审批，已等待 {r['waitingDays']} 天。"
        return self.answer(
            "requisitions",
            reply,
            [
                {
                    "type": "timeline",
                    "title": f"{r['title']} · 审批进程",
                    "href": f"/requisitions/{r['id']}",
                    "items": steps,
                }
            ],
            ["岗位招聘进度"],
        )

    # ----- actions (confirmation cards only) ---------------------------------------------

    def active_apps(self, candidate):
        rows = []
        for app in self.s.application.for_candidates(self.s.candidate.family(candidate["id"])):
            if app["outcome"]:
                continue
            try:
                self.s.application.authorize(self.ctx, app["id"])
            except DomainError:
                continue
            rows.append(app)
        if self.pos_hits and self.mentions_position():
            ids = {p["id"] for p in self.pos_hits}
            rows = [a for a in rows if a["position_id"] in ids] or rows
        return rows

    def attach(self):
        hit, reply = self.which_candidate("attach", "关联岗位：把")
        if reply:
            return reply
        if len(self.pos_hits) != 1 or not self.mentions_position():
            return self.answer(
                "attach",
                f"要把{hit['name']}加到哪个岗位？",
                [
                    {
                        "type": "list",
                        "title": "可选岗位",
                        "items": [
                            item(p["id"], p["name"], ask=f"把{hit['name']}加到{p['name']}岗位")
                            for p in (self.pos_hits or self.positions)[:10]
                        ],
                    }
                ],
            )
        pos = self.pos_hits[0]
        return self.answer(
            "attach",
            f"确认把{hit['name']}关联到“{pos['name']}”吗？关联后从“触达”阶段开始，同岗位冷却期等规则照常校验。",
            [
                {
                    "type": "confirm",
                    "title": f"关联岗位：{hit['name']} → {pos['name']}",
                    "lines": ["来源记为 HR 添加", "需要填写关联原因，会写入审计记录"],
                    "action": {
                        "kind": "attach",
                        "candidate_id": hit["id"],
                        "position_id": pos["id"],
                    },
                    "reason": "通过 AI 助手关联岗位",
                }
            ],
            [f"推进{hit['name']}", f"{hit['name']}到哪一步了"],
        )

    def stage_action(self, intent):
        verb = "推进" if intent == "advance" else "淘汰"
        hit, reply = self.which_candidate(intent, verb)
        if reply:
            return reply
        apps = self.active_apps(hit)
        if not apps:
            return self.answer(
                intent,
                f"{hit['name']}没有你可以操作的在途应聘记录。"
                + ("可以先把候选人关联到岗位。" if intent == "advance" else ""),
                [],
                [f"把{hit['name']}加到{self.positions[0]['name']}岗位"]
                if self.positions and intent == "advance"
                else [],
            )
        blocks = []
        notes = []
        for app in apps[:5]:
            stage = STAGES.get(app["stage"], app["stage"])
            if intent == "advance":
                target = NEXT_STAGE.get(app["stage"])
                if not target:
                    notes.append(
                        f"{app['position_name']}当前在“{stage}”，下一步需由面试完成或录用审批流程推进。"
                    )
                    continue
                lines = [f"{stage} → {STAGES[target]}"]
                if target == "ai_eval":
                    lines.append("进入 AI 评估前会校验候选人授权与简历信息")
                if target == "interview":
                    lines.append("进入面试后会按岗位面试流程自动生成第一轮面试")
                blocks.append(
                    {
                        "type": "confirm",
                        "title": f"推进 {hit['name']} · {app['position_name']}",
                        "lines": lines,
                        "action": {
                            "kind": "advance",
                            "application_id": app["id"],
                            "expected_version": app["version"],
                            "target_stage": target,
                        },
                        "reason": "通过 AI 助手推进",
                    }
                )
            else:
                blocks.append(
                    {
                        "type": "confirm",
                        "title": f"淘汰 {hit['name']} · {app['position_name']}",
                        "lines": [f"当前阶段：{stage}", "请选择淘汰原因；可选择是否通知候选人"],
                        "action": {
                            "kind": "reject",
                            "application_id": app["id"],
                            "expected_version": app["version"],
                        },
                        "reason": "",
                        "danger": True,
                    }
                )
        if not blocks:
            return self.answer(intent, " ".join(notes), [], [f"{hit['name']}到哪一步了"])
        reply = (
            f"请确认要{verb}的应聘记录。" if len(blocks) > 1 else f"请确认{verb}{hit['name']}："
        ) + " ".join(notes)
        follow = (
            [f"评估一下{hit['name']}", f"{hit['name']}到哪一步了"]
            if intent == "advance"
            else [f"{hit['name']}到哪一步了"]
        )
        return self.answer(intent, reply, blocks, follow)

    def advance(self):
        return self.stage_action("advance")

    def reject(self):
        return self.stage_action("reject")

    def message(self):
        hit, reply = self.which_candidate("message", "发消息：给")
        if reply:
            return reply
        # Read the words from the original sentence: the router only saw a redacted copy.
        content = (message_content(self.text) or self.route.content).strip()[:2000]
        if not content:
            return self.answer(
                "message",
                f"要给{hit['name']}发什么内容？可以直接说“给{hit['name']}发消息：……”，或者让 AI 先起草一版回复。",
                [],
                [f"帮我回复{hit['name']}的消息"],
            )
        if not hit["usable"]:
            return self.answer(
                "message",
                f"{hit['name']}还没有授权或已要求不再联系，不能发送消息。",
                [],
                [f"{hit['name']}到哪一步了"],
            )
        apps = self.active_apps(hit)
        if not apps:
            return self.answer(
                "message",
                f"{hit['name']}没有你负责的在途应聘记录，暂时不能以岗位名义发消息。",
            )
        return self.answer(
            "message",
            f"确认后我会以你的身份把这条消息发给{hit['name']}：",
            [
                {
                    "type": "confirm",
                    "title": f"发消息给 {hit['name']}",
                    "quote": content,
                    "lines": [
                        "关联岗位：" + "、".join(a["position_name"] for a in apps),
                        "发送前会由你接管会话，AI 自动回复随之暂停；夜间发送会排到可联系时段",
                    ],
                    "action": {
                        "kind": "message",
                        "candidate_id": hit["id"],
                        "application_ids": [a["id"] for a in apps],
                        "content": content,
                    },
                }
            ],
            [f"{hit['name']}到哪一步了"],
        )

    # ----- AI tasks ---------------------------------------------------------------------

    def task(self, component):
        route = Route(
            component=component,
            position=self.route.position,
            candidate=self.route.candidate,
            transcript=self.route.content if component == "A6" else "",
            reason=self.route.reason,
        )
        result = Planner(self.s, self.ctx, self.text, route, self.source).plan()
        blocks = []
        if result.get("job_id"):
            blocks.append({"type": "job", "job": self.s.engine.detail(self.ctx, result["job_id"])})
        elif result["status"] == "choose":
            blocks.append(
                {
                    "type": "choose",
                    "component": component,
                    "prompt": result["prompt"],
                    "options": result["options"],
                }
            )
        suggestions = []
        if component == "A5" and result["status"] == "blocked" and len(self.cand_hits) == 1:
            suggestions.append(f"推进{self.cand_hits[0]['name']}")
        return self.answer(component, result["message"], blocks, suggestions)


def reroute_without_names(s, ctx, text, route):
    """Re-run the keyword rules with record names masked.

    A position called "数据分析专员" must not turn "数据分析专员还差几人" into a data question,
    so the rules read the sentence with every visible position and candidate name replaced.
    """
    names = [p["name"] for p in s.position.editable(ctx) if p["name"]]
    names += [c["name"] for c in s.candidate.directory(ctx) if len(c["name"]) >= 2]
    masked = text
    for name in sorted(set(names), key=len, reverse=True):
        masked = masked.replace(name, "某某")
    if masked == text or route.intent in {"message", "A6"}:
        return route
    again = agent_rule_route(masked)
    return route if again.intent in {"message", "A6"} else again


def respond(s, ctx, text, route, source, focus=None):
    """Run the routed tool calls in order and merge their answers into one chat reply."""
    s.candidate.authorize(ctx)
    focus = dict(focus or {})
    if source == "rules":
        route = reroute_without_names(s, ctx, text, route)
    steps = [route, *[AgentRoute(**st.model_dump(), reason=route.reason) for st in route.then]]
    steps = steps[:3]
    # Each tool call reads its own clause, so "客服专员还差几人，再看看张三" does not hand
    # 张三 to the position question. When the clauses do not line up, every call reads it all.
    clauses = [p.strip() for p in CLAUSE.split(text) if p and p.strip()]
    texts = clauses if len(steps) > 1 and len(clauses) == len(steps) else [text] * len(steps)
    answers = []
    for step, part in zip(steps, texts, strict=True):
        step = step.model_copy(update={"then": []})
        answers.append(Assistant(s, ctx, part, step, source, focus).run())
        focus.update({k: v for k, v in answers[-1]["focus"].items() if v})
        if answers[0]["intent"] == "none":
            break  # A refusal is never followed by the rest of the plan.
    if len(answers) == 1:
        return answers[0]
    first = answers[0]
    return {
        **first,
        "reply": "\n\n".join(a["reply"] for a in answers if a["reply"]),
        "blocks": [b for a in answers for b in a["blocks"]],
        "suggestions": list(dict.fromkeys(x for a in answers for x in a["suggestions"]))[:4],
        "focus": answers[-1]["focus"] or first["focus"],
        "steps": [a["intent"] for a in answers],
    }
