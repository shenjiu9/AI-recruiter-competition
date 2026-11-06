from datetime import UTC, datetime, timedelta, timezone

import jwt

from app.kernel.types import Ctx, DomainError, Principal, new_id

SHANGHAI = timezone(timedelta(hours=8))


class ConversationFacade:
    def __init__(self, store, candidates, applications, org, clock, journal, settings):
        self.store, self.candidates, self.applications, self.org = (
            store,
            candidates,
            applications,
            org,
        )
        self.clock, self.journal, self.settings = clock, journal, settings

    def touch(self, ctx, c, action):
        c["version"] += 1
        self.store.save(c)
        self.journal.record(
            ctx, "conversation." + action, c["id"], c["version"], None, {"version": c["version"]}
        )

    def authorize(self, ctx, cid):
        return self.candidates.authorize(ctx, cid)

    def apps(self, cid):
        return self.applications.for_candidates(self.candidates.family(cid))

    def readable(self, ctx, cid, ids):
        apps = self.apps(cid)
        selected = [a for a in apps if a["id"] in ids] if ids else apps
        return all(self.applications.visible(ctx, a) for a in selected) and (
            not ids or len(selected) == len(set(ids))
        )

    def writable(self, ctx, cid, ids):
        apps = self.apps(cid)
        selected = [a for a in apps if a["id"] in ids] if ids else apps
        if ids and len(selected) != len(set(ids)):
            raise DomainError("APPLICATION_INVALID", "关联应聘记录不属于当前候选人", 422)
        for a in selected:
            _, pos = self.applications.authorize(ctx, a["id"])
            if pos["status"] == "closed":
                raise DomainError("POSITION_CLOSED", "关联岗位已关闭", 409)
            if pos["status"] == "paused":
                raise DomainError("POSITION_PAUSED", "关联岗位已暂停，请先恢复或切换关联岗位", 409)

    def snapshot(self, cid, ctx=None):
        candidate = self.candidates.canonical(cid)
        if ctx:
            candidate = self.authorize(ctx, cid)
        if not candidate:
            raise DomainError("LINK_INVALID", "链接已失效，请联系招聘 HR", 401)
        cid = candidate["id"]
        c = self.store.get(cid)
        messages = []
        for member in self.candidates.family(cid):
            for m in self.store.get(member)["messages"]:
                if ctx and not self.readable(ctx, cid, m["application_ids"]):
                    continue
                if not ctx and m["status"] != "sent":
                    continue
                keys = ("id", "content", "sender", "channel", "created_at", "application_ids")
                item = {k: m[k] for k in keys}
                if ctx:
                    item.update(status=m["status"], due_at=m["due_at"], reason=m.get("reason", ""))
                messages.append(item)
        messages.sort(key=lambda m: (m["created_at"], m["id"]))
        result = {
            "id": cid,
            "version": c["version"],
            "candidate_version": candidate["version"],
            "mode": c["mode"],
            "ai_paused": c.get("ai_paused", False),
            "owner_id": c["owner_id"] if ctx else None,
            "messages": messages,
            "consent": candidate["consent"],
            "do_not_contact": candidate["do_not_contact"],
            "requests": candidate.get("self_requests", [])
            if not ctx or self.readable(ctx, cid, [])
            else [],
        }
        if not ctx:
            result.update(
                profile=candidate["profile"],
                retention_until=candidate["retention_until"],
                applications=self.applications.public_statuses(cid),
            )
        return result

    def token(self, cid, link):
        return jwt.encode(
            {
                "sub": cid,
                "jti": link["id"],
                "iat": link["iat"],
                "exp": link["exp"],
                "aud": "candidate-portal",
                "iss": "recruiter-api",
            },
            self.settings.signing_key,
            algorithm="HS256",
        )

    def link_result(self, cid, lid):
        link = next((x for x in self.store.get(cid)["links"] if x["id"] == lid), None)
        if not link or link["revoked"] or link["exp"] <= self.clock.now().timestamp():
            raise DomainError("LINK_INVALID", "链接已撤销或过期，请重新生成", 409)
        return {
            "url": self.settings.candidate_portal_url.rstrip("/") + "/#t=" + self.token(cid, link),
            "expires_at": datetime.fromtimestamp(link["exp"], UTC).isoformat(),
        }

    def verify(self, token):
        try:
            claims = jwt.decode(
                token,
                self.settings.signing_key,
                algorithms=["HS256"],
                audience="candidate-portal",
                issuer="recruiter-api",
                options={
                    "require": ["sub", "jti", "iat", "exp"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            c = self.candidates.canonical(claims["sub"])
            link = next(
                (x for x in self.store.get(claims["sub"])["links"] if x["id"] == claims["jti"]),
                None,
            )
            if (
                not c
                or c["id"] != claims["sub"]
                or not link
                or link["revoked"]
                or link["exp"] <= self.clock.now().timestamp()
            ):
                raise ValueError()
            return c["id"], Ctx(Principal("candidate:" + c["id"], "候选人", (), ()), link["id"])
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise DomainError("LINK_INVALID", "链接已失效，请联系招聘 HR 获取新链接", 401) from None

    def command(self, ctx, cid, command, portal=False):
        if portal:
            self.org.lock_configuration()
        else:
            cid = self.authorize(ctx, cid)["id"]
        c = self.store.get(cid)
        if c["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "会话已更新，请刷新后核对", 409)
        action = command.action
        allowed = (
            {
                "send",
                "consent",
                "revoke",
                "do_not_contact",
                "ask_human",
                "correction_request",
                "deletion_request",
            }
            if portal
            else {"send", "take_over", "hand_back", "issue_link", "revoke_links", "resolve_request"}
        )
        if action not in allowed:
            raise DomainError("FORBIDDEN", "当前身份不能执行此操作", 403)
        result = {"id": cid}
        if action in {"issue_link", "revoke_links"}:
            # A portal link grants the candidate access to all their applications.
            # Only an HR with access to all of them may issue it.
            if not self.readable(ctx, cid, []):
                raise DomainError("FORBIDDEN", "请由能够核对完整应聘范围的 HR 生成链接", 403)
            for link in c["links"]:
                link["revoked"] = True
            if action == "issue_link":
                now = self.clock.now()
                link = {
                    "id": new_id("LINK"),
                    "iat": int(now.timestamp()),
                    "exp": int((now + timedelta(hours=72)).timestamp()),
                    "revoked": False,
                }
                c["links"].append(link)
                result["link_id"] = link["id"]
        elif action == "resolve_request":
            for app in self.apps(cid):
                self.applications.authorize(ctx, app["id"])
            self.candidates.resolve_request(ctx, cid, command.request_id, command.content)
        elif action in {"take_over", "hand_back"}:
            c["ai_paused"] = action == "take_over"
            if action == "take_over":
                self.writable(ctx, cid, [])
            if c["owner_id"] and c["owner_id"] != ctx.principal.user_id:
                if "recruiting_lead" not in ctx.principal.roles or not command.content:
                    raise DomainError(
                        "OWNED_BY_OTHER", "请由当前 HR 交还，或由招聘负责人填写交接说明后处理", 409
                    )
                c.setdefault("handoffs", []).append(
                    {
                        "from": c["owner_id"],
                        "to": ctx.principal.user_id,
                        "reason": command.content,
                        "at": self.clock.now().isoformat(),
                    }
                )
            c.update(
                mode="hr" if action == "take_over" else "waiting_human",
                owner_id=ctx.principal.user_id if action == "take_over" else None,
                debounce_at=None,
            )
        elif action == "ask_human":
            c["ai_paused"] = True
            if c["mode"] != "hr":
                c.update(mode="waiting_human", debounce_at=None)
        elif action == "send":
            if not command.content:
                raise DomainError("CONTENT_REQUIRED", "请输入消息内容")
            ids = list(dict.fromkeys(command.application_ids))
            if portal:
                if set(ids) - {a["id"] for a in self.apps(cid)}:
                    raise DomainError("APPLICATION_INVALID", "应聘记录不存在", 422)
            else:
                self.writable(ctx, cid, ids)
                if c["mode"] != "hr" or c["owner_id"] != ctx.principal.user_id:
                    raise DomainError("TAKEOVER_REQUIRED", "请先接管会话再发送消息", 409)
                if not self.candidates.contactable(cid):
                    raise DomainError("NOT_CONTACTABLE", "候选人已撤回授权或要求不再联系", 409)
            now = self.clock.now()
            latest = self.latest_inbound(cid)
            if command.reply_to_id and (not latest or latest["id"] != command.reply_to_id):
                raise DomainError("REPLY_STALE", "候选人已发来新消息，请核对后回复", 409)
            recent = bool(
                command.reply_to_id
                and latest
                and now - datetime.fromisoformat(latest["created_at"]) <= timedelta(minutes=30)
            )
            due = now if portal else self.delivery_time(now, recent)
            m = {
                "id": new_id("MSG"),
                "content": command.content,
                "sender": "candidate" if portal else "hr",
                "author_id": ctx.principal.user_id,
                "channel": "h5",
                "application_ids": ids,
                "created_at": now.isoformat(),
                "due_at": due.isoformat(),
                "status": "sent" if portal or due <= now else "queued",
                "reply_to_id": command.reply_to_id,
                "notice_id": None,
            }
            c["messages"].append(m)
            if portal:
                for old in c["messages"]:
                    if old["status"] == "queued" and old["reply_to_id"]:
                        old.update(status="cancelled", reason="候选人新增消息，请重新核对回复")
                c["debounce_at"] = (
                    (now + timedelta(seconds=10)).isoformat() if c["mode"] != "hr" else None
                )
                if any(word in command.content for word in ("不再联系", "不要联系", "停止联系")):
                    self.candidates.self_service(
                        ctx, cid, "do_not_contact", "候选人消息明确要求停止联系"
                    )
                    c = self.merge_privacy(ctx, c)
                elif any(word in command.content for word in ("转人工", "找人工", "人工客服")):
                    c["ai_paused"] = True
                    c.update(mode="waiting_human", debounce_at=None)
        else:
            self.candidates.self_service(ctx, cid, action, command.content)
            c = self.merge_privacy(ctx, c)
        self.touch(ctx, c, action)
        return result

    def merge_privacy(self, ctx, c):
        if not self.candidates.contactable(c["id"]):
            c["debounce_at"] = None
            for m in c["messages"]:
                if m["status"] == "queued":
                    m.update(status="cancelled", reason="候选人撤回授权或不再联系")
                    if m["notice_id"]:
                        self.applications.cancel_delivery(ctx, m["notice_id"])
        return c

    def invalidate(self, ctx, ids, revoke=False, erase=False):
        if erase:
            self.store.erase(ids)
            return
        for cid in ids:
            c = self.store.get(cid)
            for m in c["messages"]:
                if m["status"] == "queued":
                    m.update(status="cancelled", reason="候选人隐私或身份状态变更")
                    if m["notice_id"]:
                        self.applications.cancel_delivery(ctx, m["notice_id"])
            if revoke:
                for link in c["links"]:
                    link["revoked"] = True
                c.update(mode="waiting_human", owner_id=None)
            c["debounce_at"] = None
            self.touch(ctx, c, "invalidated")

    def latest_inbound(self, cid):
        messages = [
            m
            for member in self.candidates.family(cid)
            for m in self.store.get(member)["messages"]
            if m["sender"] == "candidate"
        ]
        return max(messages, key=lambda m: (m["created_at"], m["id"])) if messages else None

    def ai_reply(self, ctx, cid, text, reply_to_id, action_id):
        """Called after engine evidence/policy checks, in the same transaction."""
        candidate = self.authorize(ctx, cid)
        self.writable(ctx, cid, [])
        if candidate["consent"] != "granted" or candidate["do_not_contact"]:
            raise DomainError("CONSENT_REQUIRED", "候选人授权已变化", 409)
        c = self.store.get(cid)
        if c["mode"] == "hr" or c.get("ai_paused"):
            raise DomainError("HUMAN_TAKEOVER", "HR 正在接管会话", 409)
        if any(m.get("action_id") == action_id for m in c["messages"]):
            return None
        latest = self.latest_inbound(cid)
        if not latest or latest["id"] != reply_to_id:
            raise DomainError("REPLY_STALE", "候选人已发来新消息", 409)
        now = self.clock.now()
        recent = now - datetime.fromisoformat(latest["created_at"]) <= timedelta(minutes=30)
        due = self.delivery_time(now, recent)
        sent = [m for m in c["messages"] if m["sender"] == "ai" and m["status"] == "sent"]
        today = [
            m
            for m in sent
            if datetime.fromisoformat(m["created_at"]).astimezone(SHANGHAI).date()
            == now.astimezone(SHANGHAI).date()
        ]
        if len(today) >= 20 or any(
            now - datetime.fromisoformat(m["created_at"]) < timedelta(seconds=10) for m in sent
        ):
            raise DomainError("AI_FREQUENCY_LIMIT", "AI 回复已达到频率限制，请由 HR 核对", 409)
        if due > now:
            return due.isoformat()
        c["messages"].append(
            {
                "id": new_id("MSG"),
                "content": text,
                "sender": "ai",
                "author_id": ctx.principal.user_id,
                "channel": "h5",
                "application_ids": [],
                "created_at": now.isoformat(),
                "due_at": now.isoformat(),
                "status": "sent",
                "reply_to_id": reply_to_id,
                "notice_id": None,
                "action_id": action_id,
            }
        )
        c["debounce_at"] = None
        self.touch(ctx, c, "ai_replied")
        return None

    def ai_settled(self, cid):
        return self.store.get(cid)["debounce_at"] is None

    def ai_requests(self):
        result = []
        now = self.clock.now()
        for c in self.store.all():
            if (
                c["debounce_at"]
                or c["mode"] == "hr"
                or c.get("ai_paused")
                or not self.candidates.contactable(c["id"])
            ):
                continue
            latest = self.latest_inbound(c["id"])
            if not latest or now - datetime.fromisoformat(latest["created_at"]) < timedelta(
                seconds=10
            ):
                continue
            if any(
                m["sender"] != "candidate"
                and m["status"] == "sent"
                and m["created_at"] >= latest["created_at"]
                for m in c["messages"]
            ):
                continue
            apps = [a for a in self.apps(c["id"]) if not a["outcome"]]
            if apps:
                result.append(
                    {
                        "candidate_id": c["id"],
                        "message_id": latest["id"],
                        "position_id": apps[0]["position_id"],
                    }
                )
        return result

    @staticmethod
    def delivery_time(now, recent=False):
        local = now.astimezone(SHANGHAI)
        start, end = (7, 23) if recent else (9, 21)
        if start <= local.hour < end:
            return now
        next_day = local + timedelta(days=1) if local.hour >= end else local
        return next_day.replace(hour=9, minute=0, second=0, microsecond=0).astimezone(UTC)

    def queue_notice(self, ctx, app):
        cid = app["canonical_id"]
        if not self.candidates.contactable(cid):
            raise DomainError("NOT_CONTACTABLE", "候选人已撤回授权或要求不再联系", 409)
        day = self.clock.now().astimezone(SHANGHAI)
        while True:
            day += timedelta(days=1)
            if day.date() in self.settings.position_workdays or (
                day.weekday() < 5 and day.date() not in self.settings.position_holidays
            ):
                break
        due = day.replace(hour=10, minute=0, second=0, microsecond=0).astimezone(UTC)
        c = self.store.get(cid)
        c["messages"].append(
            {
                "id": new_id("MSG"),
                "content": f"感谢您关注{app['position_name']}，本次应聘流程已结束。感谢您的时间，祝求职顺利。",
                "sender": "hr",
                "author_id": ctx.principal.user_id,
                "channel": "h5",
                "application_ids": [app["id"]],
                "created_at": self.clock.now().isoformat(),
                "due_at": due.isoformat(),
                "status": "queued",
                "reply_to_id": "",
                "notice_id": app["id"],
            }
        )
        self.touch(ctx, c, "notice_queued")
        return due.isoformat()

    def cancel_notice(self, ctx, cid, aid):
        c = self.store.get(cid)
        for m in c["messages"]:
            if m["notice_id"] == aid and m["status"] == "queued":
                m.update(status="cancelled", reason="淘汰已撤销")
        self.touch(ctx, c, "notice_cancelled")

    def tick(self):
        self.org.lock_configuration()
        now = self.clock.now()
        system = Ctx(Principal("system", "调度器", (), ()), "conversation-worker")
        for c in self.store.all():
            changed = False
            if c["debounce_at"] and datetime.fromisoformat(c["debounce_at"]) <= now:
                c.update(debounce_at=None, mode="waiting_human")
                changed = True
            for m in c["messages"]:
                if m["status"] != "queued" or datetime.fromisoformat(m["due_at"]) > now:
                    continue
                changed = True
                try:
                    if not self.candidates.contactable(c["id"]):
                        raise DomainError("NOT_CONTACTABLE", "候选人已撤回授权或不再联系")
                    user = self.org.get_user(m["author_id"])
                    ctx = Ctx(
                        Principal(
                            user.id,
                            user.name,
                            user.roles,
                            user.departments,
                            user.permission_version,
                        ),
                        "conversation-worker",
                    )
                    self.authorize(ctx, c["id"])
                    self.writable(ctx, c["id"], m["application_ids"])
                    if not m["notice_id"] and (c["mode"] != "hr" or c["owner_id"] != user.id):
                        raise DomainError("TAKEOVER_REQUIRED", "接管状态已变更")
                    if (
                        m["reply_to_id"]
                        and (latest := self.latest_inbound(c["id"]))
                        and latest["id"] != m["reply_to_id"]
                    ):
                        raise DomainError("REPLY_STALE", "候选人新增消息")
                    # A late/restarted worker must still observe the current quiet window.
                    due = self.delivery_time(now)
                    if due > now:
                        m["due_at"] = due.isoformat()
                    else:
                        if m["notice_id"]:
                            self.applications.deliver_notice(ctx, m["notice_id"])
                        m["status"] = "sent"
                except DomainError as exc:
                    m.update(status="cancelled", reason=exc.message)
                    if m["notice_id"]:
                        self.applications.cancel_delivery(system, m["notice_id"])
            if changed:
                self.touch(system, c, "dispatched")
