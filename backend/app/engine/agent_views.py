"""More assistant tools: pipeline and data views, settings look-ups and small direct changes.

Mixed into ``agent.Assistant``. Every read goes through the same facade the page uses, with
the requester's context, so the assistant never shows more than the HR could open. Numbers
in charts are counted from the records; no model writes them.
"""

import re
from datetime import datetime, timedelta

from app.engine.intent import STAGES, after_separator
from app.kernel.types import DomainError
from app.modules.candidate.contracts import CandidateCommand
from app.modules.conversation.contracts import Command as ConversationCommand

FLOW = ("reach", "talking", "ai_eval", "interview", "manager_eval", "hired")
STAGE_WORDS = {
    "触达": "reach",
    "沟通": "talking",
    "评估": "ai_eval",
    "初筛": "ai_eval",
    "经理": "manager_eval",
    "面试": "interview",
    "录用": "hired",
}
OUTCOMES = {
    "rejected": "淘汰",
    "withdrawn": "候选人撤回",
    "joined": "已入职",
    "no_show": "未入职",
    "declined": "未接受",
    "transferred": "转岗位",
    "closed": "岗位关闭",
}
REASONS = {
    "requirements": "不符合职业要求",
    "experience": "经验不足",
    "skills": "技能不匹配",
    "salary": "薪资不匹配",
    "location": "地点不匹配",
    "other": "其他",
}
SOURCES = {"hr": "HR 添加", "candidate": "候选人投递", "referral": "内推", "headhunter": "猎头"}
SENDERS = {"candidate": "候选人", "hr": "HR", "ai": "AI", "system": "系统"}
ACTIONS = {
    "open": "进入岗位",
    "advance": "推进",
    "reject": "淘汰",
    "withdraw": "撤回",
    "rollback": "回退",
    "undo_reject": "撤销淘汰",
    "transfer": "转岗位",
    "interview": "进入面试",
    "hire": "录用",
}
LEVELS = {1: "L1 只建议", 2: "L2 需确认", 3: "L3 自动"}
MODES = {"normal": "正常", "shadow": "影子模式（只记录不执行）", "manual": "全部人工"}
COMPONENTS = {
    "A1": "JD 与画像",
    "A2": "人才搜索",
    "A3": "简历提取",
    "A4": "沟通回复",
    "A5": "候选人评估",
    "A6": "面试记录整理",
    "A7": "数据洞察",
}
WEEKS = 8


def day(value):
    return datetime.fromisoformat(value).date() if value else None


def week_trend(dates, today):
    """New items per week for the last WEEKS weeks, oldest first."""
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=WEEKS - 1)
    counts = [0] * WEEKS
    for d in dates:
        if d and d >= start:
            counts[min(WEEKS - 1, (d - start).days // 7)] += 1
    return [
        {"label": (start + timedelta(weeks=i)).strftime("%m-%d"), "value": n}
        for i, n in enumerate(counts)
    ]


class MoreViews:
    # ----- helpers ----------------------------------------------------------------------

    def today(self):
        return self.s.application.clock.now().date()

    def one_position(self):
        """The single position the sentence (or the previous turn) is about, or None."""
        if len(self.pos_hits) == 1 and self.mentions_position():
            return self.pos_hits[0]
        return None

    def ask_position(self, intent, verb):
        return self.answer(
            intent,
            f"要{verb}哪个岗位？",
            [
                {
                    "type": "list",
                    "title": "可选岗位",
                    "items": [
                        self.item(p["id"], p["name"], ask=f"{p['name']}{verb}")
                        for p in (self.pos_hits or self.positions)[:10]
                    ],
                }
            ],
        )

    def stage_filter(self):
        word = self.route.keyword + self.text
        return next((v for k, v in STAGE_WORDS.items() if k in word), "")

    # ----- pipeline: who is where in one position -----------------------------------------

    def pipeline(self):
        pos = self.one_position()
        if not pos:
            return self.ask_position("pipeline", "有哪些候选人")
        apps = [a for a in self.s.application.for_position(self.ctx, pos["id"]) if not a["outcome"]]
        stage = self.stage_filter()
        today = self.today()
        rows = [a for a in apps if not stage or a["stage"] == stage]

        def idle(a):
            last = a["history"][-1]["at"] if a.get("history") else a["started_at"]
            return (today - day(last)).days

        counts = {s: sum(a["stage"] == s for a in apps) for s in FLOW}
        label = STAGES.get(stage, "")
        reply = (
            f"{pos['name']}{'“' + label + '”阶段' if stage else ''}有 {len(rows)} 位在途候选人"
            + (f"（全部在途 {len(apps)} 位）" if stage else "")
            + "。"
            if rows
            else f"{pos['name']}{'“' + label + '”阶段' if stage else ''}目前没有在途候选人。"
        )
        stale = [a for a in rows if idle(a) >= 7]
        if stale:
            reply += f"其中 {len(stale)} 位超过 7 天没有进展。"
        blocks = [
            {
                "type": "stack",
                "title": f"{pos['name']} · 在途候选人分布",
                "items": [
                    {"label": STAGES[s], "value": counts[s], "tone": "brand"}
                    for s in FLOW
                    if counts[s]
                ],
            }
            if apps
            else None,
            {
                "type": "list",
                "title": "候选人",
                "items": [
                    self.item(
                        a["id"],
                        a["candidate_name"],
                        f"进入时间 {a['started_at'][:10]}",
                        f"{idle(a)} 天无进展"
                        if idle(a) >= 7
                        else (f"{idle(a)} 天前更新" if idle(a) else "今天有更新"),
                        f"/candidates/{a['candidate_id']}",
                        STAGES.get(a["stage"], a["stage"]),
                        "warning" if idle(a) >= 7 else "brand",
                        ask=f"{a['candidate_name']}到哪一步了",
                    )
                    for a in sorted(rows, key=lambda a: (FLOW.index(a["stage"]), -idle(a)))[:12]
                ],
                "more_href": f"/positions/{pos['id']}",
            }
            if rows
            else None,
        ]
        first = rows[0]["candidate_name"] if rows else ""
        return self.answer(
            "pipeline",
            reply,
            blocks,
            [f"推进{first}", f"评估一下{first}"]
            if first
            else [f"给{pos['name']}出一份人才搜索关键词"],
        )

    # ----- stats: charts counted from the records -------------------------------------------

    def stats(self):
        pos = self.one_position()
        targets = (
            [pos]
            if pos
            else [p for p in self.positions if p["status"] in {"open", "paused", "to_publish"}]
        )
        metrics, created = [], []
        for p in targets:
            try:
                self.s.position.get(self.ctx, p["id"])  # visibility, as on the page
            except DomainError:
                continue
            metrics.append((p, self.s.application.insight_metrics(p["id"])))
            created += [
                day(a["started_at"]) for a in self.s.application.for_position(self.ctx, p["id"])
            ]
        if not metrics:
            return self.answer("stats", "你名下还没有可统计的岗位。", [], ["查看招聘需求"])
        total = {k: sum(m[k] for _, m in metrics) for k in ("total", "active")}

        def merge(key):
            out = {}
            for _, m in metrics:
                for k, v in m[key].items():
                    out[k] = out.get(k, 0) + v
            return out

        reached, outcomes, reasons = merge("reached"), merge("outcomes"), merge("reasons")
        sources, stale = merge("sources"), merge("stale")
        name = pos["name"] if pos else f"{len(metrics)} 个岗位"
        funnel = [{"label": STAGES[s], "value": reached.get(s, 0)} for s in FLOW]
        top = reached.get("reach", 0)
        hired = reached.get("hired", 0)
        drop = max(
            ((FLOW[i], FLOW[i + 1]) for i in range(len(FLOW) - 1)),
            key=lambda pair: reached.get(pair[0], 0) - reached.get(pair[1], 0),
        )
        reply = (
            f"{name}累计 {total['total']} 人进入流程，在途 {total['active']} 人，已录用 {hired} 人"
            + (f"（整体转化 {round(hired * 100 / top)}%）" if top else "")
            + "。"
        )
        if top and reached.get(drop[0], 0) > reached.get(drop[1], 0):
            reply += (
                f"流失最多的一步是“{STAGES[drop[0]]} → {STAGES[drop[1]]}”"
                f"（{reached.get(drop[0], 0)} → {reached.get(drop[1], 0)}）。"
            )
        stuck = sum(stale.values())
        if stuck:
            reply += f"有 {stuck} 人超过 7 天没有进展。"
        today = self.today()
        blocks = [
            {
                "type": "funnel",
                "title": f"{name} · 招聘漏斗（到达过该阶段的人数）",
                "items": funnel,
            },
            {
                "type": "trend",
                "title": "每周新进入流程的人数",
                "unit": "人",
                "items": week_trend(created, today),
            },
            {
                "type": "stack",
                "title": "已结束的流程",
                "items": [
                    {
                        "label": OUTCOMES.get(k, k),
                        "value": v,
                        "tone": "success" if k == "joined" else "danger" if k == "rejected" else "",
                    }
                    for k, v in outcomes.items()
                    if v
                ],
            }
            if any(outcomes.values())
            else None,
            {
                "type": "bar",
                "title": "淘汰原因",
                "unit": "人",
                "items": [
                    {"label": REASONS.get(k, k), "value": v}
                    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])
                ],
            }
            if reasons
            else None,
            {
                "type": "bar",
                "title": "候选人来源",
                "unit": "人",
                "items": [
                    {"label": SOURCES.get(k, k), "value": v}
                    for k, v in sorted(sources.items(), key=lambda kv: -kv[1])
                ],
            }
            if sources
            else None,
            {
                "type": "bar",
                "title": "超过 7 天没有进展",
                "unit": "人",
                "items": [
                    {"label": STAGES[s], "value": stale[s], "tone": "warning"}
                    for s in FLOW
                    if stale.get(s)
                ],
            }
            if stuck
            else None,
        ]
        if not pos:
            blocks.insert(1, self.progress_block([p for p, _ in metrics]))
        follow = [f"分析{pos['name']}的招聘瓶颈"] if pos else ["岗位招聘进度"]
        if pos:
            follow.append(f"{pos['name']}有哪些候选人")
        return self.answer("stats", reply, blocks, follow)

    def progress_block(self, positions, title="岗位招聘进度"):
        rows = []
        for p in positions:
            planned = p.get("planned", 0)
            hired = p.get("hired", 0)
            rows.append(
                {
                    "label": p["name"],
                    "value": hired,
                    "total": planned,
                    "note": f"还差 {max(0, planned - hired)} 人" if planned > hired else "已招满",
                    "tone": "success" if planned and hired >= planned else "brand",
                    "ask": f"{p['name']}还差几个人",
                }
            )
        return {"type": "progress", "title": title, "items": rows} if rows else None

    # ----- conversation ------------------------------------------------------------------------

    def conversation(self):
        hit, reply = self.which_candidate("conversation", "查看沟通记录：")
        if reply:
            return reply
        try:
            snap = self.s.conversation.snapshot(hit["id"], self.ctx)
        except DomainError as exc:
            return self.answer(
                "conversation", f"暂时不能查看{hit['name']}的沟通记录：{exc.message}"
            )
        messages = snap["messages"]
        last_in = next((m for m in reversed(messages) if m["sender"] == "candidate"), None)
        mode = "由你接管" if snap["mode"] == "hr" else "AI 自动回复中"
        if snap.get("ai_paused") and snap["mode"] != "hr":
            mode = "AI 已暂停"
        reply = (
            f"和{hit['name']}共有 {len(messages)} 条消息，当前{mode}。"
            + (
                f"候选人最近一条在 {self.short(last_in['created_at'])}：“{last_in['content'][:60]}”"
                if last_in
                else "候选人还没有发过消息。"
            )
            if messages
            else f"还没有和{hit['name']}的沟通记录（当前{mode}）。"
        )
        if messages and messages[-1]["sender"] == "candidate":
            reply += "最后一条是候选人发的，还没有回复。"
        blocks = [
            {
                "type": "chat",
                "title": f"与 {hit['name']} 的沟通",
                "href": f"/candidates/{hit['id']}",
                "mode": mode,
                "items": [
                    {
                        "id": m["id"],
                        "sender": m["sender"],
                        "label": SENDERS.get(m["sender"], m["sender"]),
                        "content": m["content"],
                        "time": self.short(m["created_at"]),
                        "status": m.get("status", "sent"),
                    }
                    for m in messages[-8:]
                ],
            }
        ]
        follow = [f"帮我回复{hit['name']}的消息"]
        follow.append(
            f"把{hit['name']}的会话交还给 AI"
            if snap["mode"] == "hr"
            else f"接管{hit['name']}的会话"
        )
        return self.answer("conversation", reply, blocks, follow)

    # ----- decision cards ----------------------------------------------------------------------

    def cards(self):
        cards = self.s.query.workbench(self.ctx)["cards"]
        overdue = [c for c in cards if c["overdue"]]
        reply = (
            f"有 {len(cards)} 张决策卡等你处理"
            + (f"，其中 {len(overdue)} 张已超时" if overdue else "")
            + "。"
            if cards
            else "没有等你处理的决策卡。"
        )
        return self.answer(
            "cards",
            reply,
            [
                {
                    "type": "list",
                    "title": "等你决定",
                    "items": self.card_items(cards[:10]),
                    "more_href": "/workbench",
                }
            ]
            if cards
            else [],
            ["今天有什么要处理"],
        )

    # ----- settings look-ups (each facade enforces its own permission) ---------------------

    def denied(self, intent, what, exc):
        return self.answer(
            intent, f"你当前的权限不能查看{what}：{exc.message}", [], ["今天有什么要处理"]
        )

    def headcount(self):
        year = self.today().year
        try:
            result = self.s.org.headcount_list(self.ctx, year)
        except DomainError as exc:
            return self.denied("headcount", "编制", exc)
        rows = result["items"]
        if not rows:
            return self.answer("headcount", f"{year} 年还没有维护编制。")
        planned = sum(r["planned"] for r in rows)
        available = sum(r["available"] for r in rows)
        reply = f"{year} 年你负责的 {len(rows)} 个部门共有编制 {planned} 个，可用 {available} 个。"
        frozen = [r["dept"] for r in rows if r["frozen"]]
        if frozen:
            reply += f"已冻结：{'、'.join(frozen)}。"
        return self.answer(
            "headcount",
            reply,
            [
                {
                    "type": "progress",
                    "title": f"{year} 年编制使用",
                    "items": [
                        {
                            "label": r["dept"],
                            "value": r["used"] + r["reserved"],
                            "total": r["planned"],
                            "note": "已冻结"
                            if r["frozen"]
                            else f"已用 {r['used']} · 占用 {r['reserved']} · 可用 {r['available']}",
                            "tone": "danger"
                            if r["frozen"] or not r["available"]
                            else "warning"
                            if r["stale"]
                            else "brand",
                        }
                        for r in rows
                    ],
                    "more_href": "/settings/headcount",
                }
            ],
            ["招聘需求审批到哪了"],
        )

    def salary(self):
        try:
            result = self.s.org.salary_list(self.ctx, 1, 100)
        except DomainError as exc:
            return self.denied("salary", "薪资带宽", exc)
        rows = result["items"]
        word = self.route.keyword or ""
        if not word:
            sentence = self.text
            word = next(
                (
                    k
                    for r in rows
                    for k in (r["series"], r["city"], r["grade"])
                    if k and k in sentence
                ),
                "",
            )
        if word:
            rows = [r for r in rows if word in f"{r['series']}{r['grade']}{r['city']}"] or rows
        live = [r for r in rows if r["active"]]
        reply = (
            f"找到 {len(live)} 条生效中的薪资带宽" + (f"（与“{word}”相关）" if word else "") + "。"
            "这里只供查看，具体定薪要在录用流程里由 HR 填写并审批。"
            if live
            else "还没有生效中的薪资带宽。"
        )
        return self.answer(
            "salary",
            reply,
            [
                {
                    "type": "table",
                    "title": "薪资带宽（月薪）",
                    "columns": ["序列", "职级", "城市", "下限", "上限", "月数"],
                    "rows": [
                        [
                            r["series"],
                            r["grade"],
                            r["city"],
                            r["active"]["lower"],
                            r["active"]["upper"],
                            r["active"]["months"],
                        ]
                        for r in live[:20]
                    ],
                    "more_href": "/settings/salary",
                }
            ]
            if live
            else [],
        )

    def automation(self):
        try:
            cfg = self.s.automation.get(self.ctx)
        except DomainError as exc:
            return self.denied("automation", "自动化设置", exc)
        on = [COMPONENTS.get(k, k) for k, v in cfg["components"].items() if v]
        off = [COMPONENTS.get(k, k) for k, v in cfg["components"].items() if not v]
        reply = f"当前自动化模式：{MODES.get(cfg['mode'], cfg['mode'])}。" + (
            f"已开启的 AI 能力：{'、'.join(on)}。" if on else "AI 能力都还没有开启。"
        )
        if off:
            reply += f"未开启：{'、'.join(off)}。"
        return self.answer(
            "automation",
            reply,
            [
                {
                    "type": "table",
                    "title": "各环节自动化程度",
                    "columns": ["环节", "当前级别"],
                    "rows": [
                        [n["name"], LEVELS.get(cfg["levels"].get(n["key"]), "未设置")]
                        for n in cfg["nodes"]
                    ],
                    "more_href": "/settings/automation",
                }
            ],
        )

    def org(self):
        try:
            rows = self.s.org.configuration.departments(self.ctx)
        except DomainError as exc:
            return self.denied("org", "组织架构", exc)
        return self.answer(
            "org",
            f"你能查看 {len(rows)} 个部门的配置。",
            [
                {
                    "type": "table",
                    "title": "部门与审批人",
                    "columns": ["部门", "审批人"],
                    "rows": [
                        [
                            r.get("name") or r.get("id", ""),
                            "、".join(v for v in r.get("approver_names", {}).values() if v) or "—",
                        ]
                        for r in rows
                    ],
                    "more_href": "/settings/organization",
                }
            ]
            if rows
            else [],
        )

    # ----- direct, reversible changes ----------------------------------------------------------

    def done(self, intent, reply, title, lines, undo, suggestions=()):
        block = {"type": "done", "title": title, "lines": lines}
        if undo:
            block["undo"] = undo
        return self.answer(intent, reply, [block], suggestions)

    def candidate_record(self, hit):
        return self.s.candidate.get(self.ctx, hit["id"])

    def key(self):
        hit, reply = self.which_candidate("key", "设为重点：把")
        if reply:
            return reply
        c = self.candidate_record(hit)
        want = not re.search(r"取消|去掉|不再|不是", self.route.keyword + self.text)
        if c["key_candidate"] == want:
            return self.answer(
                "key",
                f"{hit['name']}{'已经是' if want else '本来就不是'}重点候选人，不需要修改。",
                [],
                [f"{hit['name']}到哪一步了"],
            )
        self.s.candidate.command(
            self.ctx,
            c["id"],
            CandidateCommand(action="key", expected_version=c["version"], key_candidate=want),
        )
        after = self.candidate_record(hit)
        return self.done(
            "key",
            f"已{'把' + hit['name'] + '设为' if want else '取消' + hit['name'] + '的'}重点候选人。",
            f"{'设为' if want else '取消'}重点候选人：{hit['name']}",
            ["已写入候选人档案和审计记录"],
            {
                "label": "撤销",
                "action": {
                    "kind": "command",
                    "target": "candidate",
                    "id": c["id"],
                    "body": {
                        "action": "key",
                        "expected_version": after["version"],
                        "key_candidate": not want,
                    },
                },
            },
            [f"{hit['name']}到哪一步了", "找重点候选人"],
        )

    def tag_text(self):
        if self.route.keyword:
            return self.route.keyword
        quoted = re.search(r"[“\"「](.{1,40}?)[”\"」]", self.text)
        if quoted:
            return quoted.group(1)
        return after_separator(self.text)[:40]

    def tag(self):
        hit, reply = self.which_candidate("tag", "打标签：给")
        if reply:
            return reply
        text = self.tag_text().strip(" 。，,")
        if not text:
            return self.answer(
                "tag",
                f"要给{hit['name']}打什么标签？可以说“给{hit['name']}打个标签：沟通好”。",
            )
        c = self.candidate_record(hit)
        if text in c["tags"]:
            return self.answer("tag", f"{hit['name']}已经有“{text}”这个标签了。")
        self.s.candidate.command(
            self.ctx,
            c["id"],
            CandidateCommand(action="tags", expected_version=c["version"], tags=[*c["tags"], text]),
        )
        after = self.candidate_record(hit)
        return self.done(
            "tag",
            f"已给{hit['name']}加上标签“{text}”。",
            f"打标签：{hit['name']}",
            ["标签：" + "、".join(after["tags"])],
            {
                "label": "撤销",
                "action": {
                    "kind": "command",
                    "target": "candidate",
                    "id": c["id"],
                    "body": {
                        "action": "tags",
                        "expected_version": after["version"],
                        "tags": c["tags"],
                    },
                },
            },
            [f"{hit['name']}到哪一步了"],
        )

    def handler_mode(self, intent, want):
        verb = "接管会话：" if want == "hr" else "交还 AI："
        hit, reply = self.which_candidate(intent, verb)
        if reply:
            return reply
        try:
            snap = self.s.conversation.snapshot(hit["id"], self.ctx)
        except DomainError as exc:
            return self.answer(intent, f"暂时不能操作{hit['name']}的会话：{exc.message}")
        mine = snap["owner_id"] == self.ctx.principal.user_id
        if want == "hr" and snap["mode"] == "hr" and mine:
            return self.answer(
                intent, f"{hit['name']}的会话已经由你接管了。", [], [f"{hit['name']}最近说了什么"]
            )
        if want == "ai" and snap["mode"] != "hr":
            return self.answer(intent, f"{hit['name']}的会话本来就由 AI 自动回复。")
        action = "take_over" if want == "hr" else "hand_back"
        self.s.conversation.command(
            self.ctx,
            hit["id"],
            ConversationCommand(action=action, expected_version=snap["version"]),
        )
        after = self.s.conversation.snapshot(hit["id"], self.ctx)
        return self.done(
            intent,
            f"已{'接管' if want == 'hr' else '把会话交还给 AI'}：{hit['name']}。"
            + (
                "AI 自动回复已暂停，之后的消息由你来回。"
                if want == "hr"
                else "AI 会按自动化设置继续回复。"
            ),
            f"{'接管会话' if want == 'hr' else '会话交还 AI'}：{hit['name']}",
            ["已写入审计记录"],
            {
                "label": "撤销",
                "action": {
                    "kind": "command",
                    "target": "conversation",
                    "id": hit["id"],
                    "body": {
                        "action": "hand_back" if want == "hr" else "take_over",
                        "expected_version": after["version"],
                    },
                },
            },
            [f"{hit['name']}最近说了什么", f"帮我回复{hit['name']}的消息"],
        )

    def take_over(self):
        return self.handler_mode("take_over", "hr")

    def hand_back(self):
        return self.handler_mode("hand_back", "ai")

    # ----- changes confirmed by the HR ----------------------------------------------------------

    def restore(self):
        hit, reply = self.which_candidate("restore", "撤销淘汰：")
        if reply:
            return reply
        rows = []
        for app in self.s.application.for_candidates(self.s.candidate.family(hit["id"])):
            if app["outcome"] != "rejected":
                continue
            try:
                self.s.application.authorize(self.ctx, app["id"])
            except DomainError:
                continue
            rows.append(app)
        if self.one_position():
            rows = [a for a in rows if a["position_id"] == self.one_position()["id"]] or rows
        if not rows:
            return self.answer("restore", f"{hit['name']}没有你可以撤销的淘汰记录。")
        return self.answer(
            "restore",
            f"请确认撤销{hit['name']}的淘汰：",
            [
                {
                    "type": "confirm",
                    "title": f"撤销淘汰 {hit['name']} · {a['position_name']}",
                    "lines": [
                        f"淘汰前阶段：{STAGES.get(a['stage'], a['stage'])}",
                        "撤销后恢复到原阶段，冷却期和授权规则照常校验",
                    ],
                    "action": {
                        "kind": "command",
                        "target": "application",
                        "id": a["id"],
                        "body": {"action": "undo_reject", "expected_version": a["version"]},
                    },
                    "reason": "通过 AI 助手撤销淘汰",
                }
                for a in rows[:5]
            ],
            [f"{hit['name']}到哪一步了"],
        )

    def position_switch(self, intent):
        pos = self.one_position()
        verb = "暂停招聘" if intent == "pause" else "恢复招聘"
        if not pos:
            return self.ask_position(intent, "的招聘" + ("暂停" if intent == "pause" else "恢复"))
        p = self.s.position.get(self.ctx, pos["id"])
        need = "open" if intent == "pause" else "paused"
        if p["status"] != need:
            return self.answer(
                intent,
                f"{p['name']}当前是“{self.position_state(p['status'])}”，不能{verb}。",
                [],
                [f"{p['name']}还差几个人"],
            )
        body = {"action": intent, "expected_version": p["version"]}
        if intent == "pause":
            body["handling"] = "continue"
        return self.answer(
            intent,
            f"请确认{verb}：{p['name']}",
            [
                {
                    "type": "confirm",
                    "title": f"{verb}：{p['name']}",
                    "lines": [
                        "暂停后不再接收新投递，在途候选人继续推进"
                        if intent == "pause"
                        else "恢复后重新接收投递，招聘渠道按原配置发布",
                        "需要填写原因，会写入审计记录",
                    ],
                    "action": {
                        "kind": "command",
                        "target": "position",
                        "id": p["id"],
                        "body": body,
                    },
                    "reason": "",
                    "danger": intent == "pause",
                }
            ],
            [f"{p['name']}还差几个人"],
        )

    def pause(self):
        return self.position_switch("pause")

    def resume(self):
        return self.position_switch("resume")

    # ----- timelines used by the existing answers --------------------------------------------

    def journey(self, app):
        steps = [
            {
                "time": app["started_at"][:10],
                "title": "进入岗位",
                "subtitle": SOURCES.get(app.get("source", ""), ""),
                "state": "done",
            }
        ]
        for h in app.get("history") or []:
            if h["action"] == "open":
                continue
            to = STAGES.get(h.get("to_stage"), h.get("to_stage") or "")
            title = ACTIONS.get(h["action"], h["action"])
            if h["action"] in {"advance", "rollback", "interview"} and to:
                title += f"到“{to}”"
            steps.append(
                {
                    "time": h["at"][:10],
                    "title": title,
                    "subtitle": (h.get("reason") or "")[:60],
                    "state": "bad" if h["action"] == "reject" else "done",
                }
            )
        if not app["outcome"]:
            steps[-1]["state"] = "current"
            nxt = FLOW[FLOW.index(app["stage"]) + 1] if app["stage"] in FLOW[:-1] else ""
            if nxt:
                steps.append(
                    {"time": "", "title": f"下一步：{STAGES[nxt]}", "subtitle": "", "state": "todo"}
                )
        return steps
