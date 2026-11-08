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

from app.engine.context import sanitize
from app.engine.contracts import AgentRoute, Route
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

CAPABILITIES = [
    ("查进展", "今天有什么要处理 / 客服专员还差几个人 / 张三到哪一步了"),
    ("找人", "找会 Python 的候选人 / 最近的面试安排 / 录用待办"),
    ("让 AI 干活", "帮客服专员写一版 JD / 评估一下张三 / 帮我回复张三的消息"),
    ("推进流程", "把张三加到客服专员岗位 / 推进张三 / 淘汰张三"),
    ("沟通", "给张三发消息：明天上午 10 点电话沟通"),
]
HELP_SUGGESTIONS = ["今天有什么要处理", "岗位招聘进度", "待我复核的 AI 结果", "最近的面试安排"]

# Assistant-only intents. PRE rules run before the A1–A5 task rules, POST rules after
# them, so "整理进档案" stays an extraction task while "张三到哪一步了" is answered
# from the records. Within each list the first matching rule wins.
PRE_RULES = [
    (
        "help",
        r"^(你好|您好|hi|hello|在吗)|你能(做|干)什么|能帮我(做|干)?什么|怎么用|使用说明|^帮助$",
    ),
    ("A6", r"面评|面试(记录|纪要|笔记)|整理.{0,8}面试"),
    (
        "message",
        r"(给|跟|和|向).{1,16}(发|留|说).{0,3}(消息|信息|短信|一声|个话|一句)|发消息给|发信息给|(告诉|通知)[^，。]{1,12}[：:]",
    ),
    ("reject", r"淘汰|刷掉|拒掉|不再推进|终止.{0,4}(流程|应聘)"),
    ("attach", r"(加到|加入|关联到|挂到|投递到|放到|添加到|推荐到).{0,16}"),
    ("advance", r"推进|推到|往前推|下一(阶段|步)|进入下一|约面|进面试|进入面试|安排.{0,6}面试"),
    ("reviews", r"复核|待审核|待确认的(建议|结果)|AI.{0,6}(结果|任务)"),
    (
        "interviews",
        r"面试(安排|日程|计划|列表)|(今天|明天|本周|这周|下周|最近|我的|有哪些|有几场|几场).{0,6}面试",
    ),
    ("hires", r"录用|offer|入职|移交"),
    ("requisitions", r"招聘需求|需求单|需求审批|用人需求|编制申请"),
    (
        "overview",
        r"今天.{0,4}(要|有什么|有啥|待|该|做|安排|干|忙)|待办|要处理|待决策|概览|总览|日报|汇总|工作台|有什么事|忙什么|该做什么",
    ),
    (
        "candidates",
        r"找.{0,12}(的候选人|的人)|有没有.{0,12}(候选人|的人)|候选人(列表|库)|人才库里|最近.{0,4}(的)?候选人",
    ),
]
# Offers and pay are decided by people in the hiring flow; the assistant declines them before
# the "录用|offer" read rule can turn "给张三发offer，月薪两万" into a hires listing.
OUT_OF_SCOPE = re.compile(
    r"(发|给|开|谈|出).{0,8}(offer|录用通知)|定薪|谈薪|调薪|涨薪|(月薪|年薪|薪资|工资)(定|开|给|谈|是|为|\d|[一二两三四五六七八九十]|多少)",
    re.I,
)
REFUSAL = (
    "发 offer 和定薪资要由 HR 在录用流程里亲自操作，我不能代办。我可以帮你看录用待办或候选人进展。"
)
POST_RULES = [
    ("A7", r"为什么|瓶颈|分析|洞察|转化|漏斗|卡在|怎么办|改进|太慢|很慢"),
    (
        "positions",
        r"还差|缺几|差几|多少人|几个人|几人|招满|到岗|进度|岗位(列表|情况)|哪些岗位|在招",
    ),
    ("candidate", r"到哪(一步|了)|什么阶段|哪个阶段|进展|状态|情况|怎么样|是谁|简介"),
]
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


def agent_rule_route(text):
    if OUT_OF_SCOPE.search(text):
        return AgentRoute(intent="none", reason=REFUSAL)
    for intent, pattern in [*PRE_RULES, *TASK_RULES, *POST_RULES]:
        if re.search(pattern, text, re.I):
            content = ""
            if intent == "A6":
                content = after_separator(text)
            elif intent == "message":
                content = message_content(text)
            return AgentRoute(intent=intent, content=content, reason="按关键词识别")
    return AgentRoute(intent="none", reason="没有识别到对应的操作")


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
    updates = {}
    for key in ("position", "candidate", "keyword", "content"):
        value = getattr(route, key)
        if value and norm(value) not in sentence:
            updates[key] = ""
    return route.model_copy(update=updates)


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


class Assistant:
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
            return self.answer(
                "positions",
                reply,
                self.position_card(p),
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
            [{"type": "list", "title": "岗位进度", "items": items, "more_href": "/positions"}],
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
        suggestions = []
        if any(a["stage"] == "ai_eval" for a in active):
            suggestions.append(f"评估一下{name}")
        if any(a["stage"] in NEXT_STAGE for a in active):
            suggestions.append(f"推进{name}")
        if not active and self.positions:
            suggestions.append(f"把{name}加到{self.positions[0]['name']}岗位")
        suggestions += [f"帮我回复{name}的消息", f"提取{name}的简历信息"]
        return self.answer("candidate", reply, blocks, suggestions)

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
        scheduled = [iv for iv in active if iv["status"] == "scheduled"]
        waiting = [iv for iv in active if iv["status"] in {"waiting", "offered"}]
        feedback = [iv for iv in active if iv["status"] == "awaiting_feedback"]
        reply = (
            f"共有 {len(active)} 场进行中的面试：已约定 {len(scheduled)} 场，待约时间 {len(waiting)} 场，待提交面评 {len(feedback)} 场。"
            if active
            else "目前没有进行中的面试。候选人推进到“面试”阶段后会自动生成面试轮次。"
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
            [{"type": "list", "title": "面试", "items": items, "more_href": "/interviews"}]
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
        return self.answer(
            "hires",
            reply,
            [{"type": "list", "title": "录用", "items": items, "more_href": "/hiring"}]
            if items
            else [],
            ["今天有什么要处理"],
        )

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
                    "type": "list",
                    "title": "招聘需求",
                    "items": items,
                    "more_href": "/requisitions",
                }
            ]
            if items
            else [],
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


def respond(s, ctx, text, route, source, focus=None):
    s.candidate.authorize(ctx)
    return Assistant(s, ctx, text, route, source, focus).run()
