from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlparse

from app.kernel.types import Ctx, DomainError, Principal, new_id
from app.modules.interview.integration import step

TZ = timezone(timedelta(hours=8))
ACTIVE = {"needs_configuration", "waiting", "offered", "scheduled", "awaiting_feedback", "no_show"}
TERMINAL = {"completed", "cancelled"}
SYSTEM = Ctx(Principal("system:interview", "面试调度", (), ()), "interview-worker")


class InterviewFacade:
    def __init__(
        self,
        store,
        candidates,
        applications,
        positions,
        org,
        clock,
        journal,
        settings,
        gateway=None,
    ):
        self.store, self.candidates, self.applications, self.positions = (
            store,
            candidates,
            applications,
            positions,
        )
        self.org, self.clock, self.journal, self.settings, self.gateway = (
            org,
            clock,
            journal,
            settings,
            gateway,
        )

    def save(self, ctx, iv, action):
        old = iv["version"]
        iv["version"] += 1
        iv["history"].append(
            {"action": action, "actor": ctx.principal.user_id, "at": self.clock.now().isoformat()}
        )
        self.store.save(iv, old)
        self.journal.record(
            ctx, "interview." + action, iv["id"], iv["version"], None, {"status": iv["status"]}
        )

    def enter(self, ctx, app, pos):
        plans = pos["interviewPlans"]
        plan = deepcopy(plans[-1]) if plans else {"version": 0, "rounds": []}
        must_ask = (
            pos.get("activeProfile", {}).get("must_ask", "") if pos.get("activeProfile") else ""
        )
        return self.create_round(ctx, app, plan, 0, new_id("CYCLE"), must_ask)

    def create_round(self, ctx, app, plan, index, cycle, must_ask=""):
        iv = {
            "id": new_id("IV"),
            "version": 1,
            "application_id": app["id"],
            "candidate_id": app["candidate_id"],
            "position_id": app["position_id"],
            "position_name": app["position_name"],
            "cycle": cycle,
            "round_no": index + 1,
            "plan": deepcopy(plan),
            "spec": deepcopy(plan["rounds"][index]) if plan["rounds"] else None,
            "must_ask": must_ask,
            "status": "waiting" if plan["rounds"] else "needs_configuration",
            "created_at": self.clock.now().isoformat(),
            "slots": [],
            "start": None,
            "end": None,
            "location": "",
            "meeting_url": "",
            "recording_consent": False,
            "feedback": {},
            "feedback_history": [],
            "history": [],
            "requests": [],
            "candidate_reschedules": 0,
            "result": None,
            "ended_at": None,
            "integration": {
                "state": "not_requested",
                "generation": 0,
                "meeting": None,
                "calendar": None,
            },
            "reminders": [],
        }
        self.store.save(iv)
        self.journal.record(ctx, "interview.created", iv["id"], 1, None, {"status": iv["status"]})
        return iv

    def get_record(self, iid):
        iv = self.store.get(iid)
        if not iv:
            raise DomainError("NOT_FOUND", "面试不存在或无权查看", 404)
        return iv

    def authorize(self, ctx, iid, edit=False):
        self.candidates.lock(ctx)
        iv = self.get_record(iid)
        assigned = self.assigned(iv, ctx.principal)
        allowed = False
        try:
            pos = self.positions.get(ctx, iv["position_id"])
            allowed = pos["canEdit"] if edit else True
        except DomainError:
            pass
        if edit:
            allowed = allowed and self.candidates.hr(ctx)
        if not allowed and not (assigned and not edit):
            raise DomainError("NOT_FOUND", "面试不存在或无权查看", 404)
        return iv

    def assigned(self, iv, user):
        return bool(
            iv["spec"]
            and user.user_id in iv["spec"]["interviewers"]
            and self.positions.interview_state(iv["position_id"])["dept"] in user.departments
            and set(user.roles).intersection(
                {"interviewer", "hiring_manager", "recruiter", "recruiting_lead"}
            )
        )

    def candidate_authorize(self, cid, iid):
        iv = self.get_record(iid)
        if iv["candidate_id"] not in self.candidates.family(cid):
            raise DomainError("NOT_FOUND", "面试不存在", 404)
        return iv

    def current(self, iv):
        app = self.applications.interview_context(iv["application_id"])
        if not app or app["outcome"] or app["stage"] != "interview":
            raise DomainError("APPLICATION_ENDED", "应聘流程已结束或不在面试阶段", 409)
        state = self.positions.interview_state(iv["position_id"])
        if state["status"] == "closed" or state["frozen"]:
            raise DomainError("POSITION_FROZEN", "岗位已关闭或冻结，请联系 HR", 409)
        return app

    def dto(self, iv, ctx=None, candidate=False):
        c = self.candidates.canonical(iv["candidate_id"])
        result = {
            k: iv[k]
            for k in (
                "id",
                "version",
                "application_id",
                "position_id",
                "position_name",
                "round_no",
                "status",
                "start",
                "end",
                "location",
                "meeting_url",
                "recording_consent",
                "created_at",
            )
        }
        result["slots"] = (
            [s for s in iv["slots"] if datetime.fromisoformat(s["expires_at"]) > self.clock.now()]
            if iv["status"] == "offered"
            else []
        )
        result["round_name"] = iv["spec"]["name"] if iv["spec"] else "待配置面试流程"
        result["format"] = iv["spec"]["format"] if iv["spec"] else ""
        result["integration_state"] = iv["integration"]["state"]
        result["recording_enabled"] = False  # No recording integration is enabled by this release.
        if candidate:
            result["requests"] = [
                {"reason": r["reason"], "status": r["status"]}
                for r in iv["requests"]
                if r["actor"].startswith("candidate:")
            ]
            return result
        uid = ctx.principal.user_id
        assigned = self.assigned(iv, ctx.principal)
        can_edit = False
        try:
            can_edit = (
                self.candidates.hr(ctx) and self.positions.get(ctx, iv["position_id"])["canEdit"]
            )
        except DomainError:
            pass
        own_submitted = uid in iv["feedback"]
        blind = any(
            r["cycle"] == iv["cycle"]
            and r["round_no"] >= iv["round_no"]
            and r["status"] != "cancelled"
            and uid in (r["spec"] or {}).get("interviewers", [])
            and uid not in r["feedback"]
            for r in self.store.all()
        )
        full = (can_edit and not blind) or own_submitted
        # Assigned interviewers see their own feedback only until they have submitted.
        feedback = iv["feedback"] if full else {k: v for k, v in iv["feedback"].items() if k == uid}
        previous = []
        for old in self.store.all():
            if old["cycle"] == iv["cycle"] and old["round_no"] < iv["round_no"]:
                previous.append(
                    {
                        "round_no": old["round_no"],
                        "result": old["result"],
                        **({"feedback": old["feedback"]} if full else {}),
                    }
                )
        profile = self.candidates.mask_tree(c["profile"]) if c else {}
        profile.pop("expected_salary", None)
        result.update(
            candidate_id=c["id"] if c else "",
            candidate_name=profile.get("name", "已删除"),
            profile=profile,
            spec=iv["spec"],
            plan_version=iv["plan"]["version"],
            must_ask=iv["must_ask"],
            feedback=feedback,
            feedback_count=len(iv["feedback"]),
            previous_rounds=previous,
            result=iv["result"],
            can_edit=can_edit,
            can_feedback=assigned,
            my_feedback=iv["feedback"].get(uid),
            interviewers=[
                {"id": u, "name": (self.org.identity(u) or {}).get("name", u)}
                for u in (iv["spec"] or {}).get("interviewers", [])
            ],
            requests=iv["requests"] if can_edit or assigned else [],
            feedback_history=iv["feedback_history"] if full else [],
            reminders=iv["reminders"],
            history=iv["history"],
        )
        return result

    def list(
        self,
        ctx=None,
        cid=None,
        position_id="",
        application_id="",
        candidate_id="",
        state="",
        mine=False,
    ):
        rows = []
        for iv in self.store.all():
            if candidate_id and iv["candidate_id"] not in self.candidates.family(candidate_id):
                continue
            if (
                position_id
                and iv["position_id"] != position_id
                or application_id
                and iv["application_id"] != application_id
            ):
                continue
            try:
                if cid:
                    self.candidate_authorize(cid, iv["id"])
                else:
                    self.authorize(ctx, iv["id"])
                    if mine and ctx.principal.user_id not in (iv["spec"] or {}).get(
                        "interviewers", []
                    ):
                        continue
            except DomainError:
                continue
            if state and iv["status"] != state:
                continue
            rows.append(self.dto(iv, ctx, candidate=bool(cid)))
        return sorted(rows, key=lambda v: (v["start"] or "9999", v["created_at"], v["id"]))

    def availability(self, ctx, command=None):
        self.candidates.lock(ctx)
        if not set(ctx.principal.roles).intersection(
            {"interviewer", "hiring_manager", "recruiter", "recruiting_lead", "hrbp"}
        ):
            raise DomainError("FORBIDDEN", "当前身份不能维护可面时段", 403)
        uid = ctx.principal.user_id
        value = self.store.availability(uid)
        if command:
            if value["version"] != command.expected_version:
                raise DomainError("VERSION_CONFLICT", "可面设置已更新", 409)
            if command.end_hour <= command.start_hour or any(
                d not in range(7) for d in command.weekdays
            ):
                raise DomainError("AVAILABILITY_INVALID", "请填写有效的工作日和起止时间")
            value = {
                **command.model_dump(exclude={"expected_version"}),
                "version": value["version"] + 1,
            }
            self.store.save_availability(uid, value)
            self.journal.record(
                ctx, "interview.availability_updated", uid, value["version"], None, {}
            )
        return value

    def workday(self, day):
        return day in self.settings.position_workdays or (
            day.weekday() < 5 and day not in self.settings.position_holidays
        )

    def resources(self, iv, start, end):
        cid = self.candidates.canonical(iv["candidate_id"])["id"]
        values = [("candidate:" + cid, start, end)]
        for uid in iv["spec"]["interviewers"]:
            user = self.org.get_user(uid)
            if not self.assigned(iv, Principal(uid, user.name, user.roles, user.departments)):
                raise DomainError(
                    "INTERVIEWER_INVALID", "面试官权限或部门范围已变化，请 HR 协调", 409
                )
            padding = timedelta(minutes=self.store.availability(uid)["buffer_minutes"])
            values.append(("user:" + uid, start - padding, end + padding))
        return values

    def validate_slot(self, iv, start, excluding="", proposed=()):
        start = start.astimezone(UTC)
        end = start + timedelta(minutes=iv["spec"]["duration"])
        local, local_end = start.astimezone(TZ), end.astimezone(TZ)
        if start <= self.clock.now() or not self.workday(local.date()):
            raise DomainError("SLOT_INVALID", "请选择未来工作日时段", 409)
        for uid in iv["spec"]["interviewers"]:
            pref = self.store.availability(uid)
            if (
                local.weekday() not in pref["weekdays"]
                or local.hour < pref["start_hour"]
                or local_end.date() != local.date()
                or local_end.hour * 60 + local_end.minute > pref["end_hour"] * 60
            ):
                raise DomainError("OUTSIDE_AVAILABILITY", "不在面试官可面时段内", 409)
            scheduled = [
                r
                for r in self.store.all()
                if r["id"] != iv["id"]
                and r["start"]
                and r["status"] != "cancelled"
                and uid in (r["spec"] or {}).get("interviewers", [])
            ]
            times = [datetime.fromisoformat(r["start"]).astimezone(TZ) for r in scheduled]
            if (
                sum(t.date() == local.date() for t in times) >= pref["daily_limit"]
                or sum(t.isocalendar()[:2] == local.isocalendar()[:2] for t in times)
                >= pref["weekly_limit"]
            ):
                raise DomainError("INTERVIEW_LIMIT", "面试官已达到每日或每周上限", 409)
        resources = self.resources(iv, start, end)
        for resource, low, high in resources:
            if self.store.overlaps(resource, low, high, excluding) or any(
                r == resource and a < high and b > low for r, a, b in proposed
            ):
                raise DomainError("SLOT_CONFLICT", "面试官或候选人的时段已被占用，请刷新选择", 409)
        return end, resources

    def offer(self, iv, verified):
        if not verified:
            raise DomainError(
                "CALENDAR_CONFIRM_REQUIRED", "外部日历未接入，请 HR 核实忙闲后确认生成时段"
            )
        if not iv["spec"] or iv["spec"]["format"] == "ai":
            raise DomainError("PLAN_REQUIRED", "请先配置人工面试流程；AI 初面尚未启用", 409)
        self.current(iv)
        if not self.candidates.contactable(iv["candidate_id"]):
            raise DomainError("NOT_CONTACTABLE", "候选人已停止联系或撤回授权", 409)
        if iv["status"] not in {"waiting", "offered"}:
            raise DomainError("INVALID_TRANSITION", "当前不能生成预约时段", 409)
        self.store.expire(self.clock.now())
        self.store.release(iv["id"])
        slots, proposed = [], []
        day = self.clock.now().astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        workdays = 0
        for delta in range(1, 61):
            target = day + timedelta(days=delta)
            if not self.workday(target.date()):
                continue
            workdays += 1
            if workdays > 7:
                break
            for half in range(18, 36):
                start = (target + timedelta(minutes=half * 30)).astimezone(UTC)
                if start < self.clock.now() + timedelta(hours=26):
                    continue
                try:
                    end, resources = self.validate_slot(iv, start, proposed=proposed)
                except DomainError:
                    continue
                slot = {
                    "id": new_id("SLOT"),
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "expires_at": (self.clock.now() + timedelta(hours=24)).isoformat(),
                }
                slots.append(slot)
                proposed.extend(resources)
                for resource, low, high in resources:
                    self.store.reserve(
                        iv["id"],
                        resource,
                        slot["id"],
                        low,
                        high,
                        datetime.fromisoformat(slot["expires_at"]),
                    )
                break  # Spread alternatives across days.
            if len(slots) == 4:
                break
        if not slots:
            raise DomainError("NO_COMMON_SLOT", "没有共同空闲时段，请调整可面设置或由 HR 协调", 409)
        iv.update(slots=slots, status="offered")

    def book(self, iv, command, candidate):
        self.current(iv)
        if not self.candidates.contactable(iv["candidate_id"]):
            raise DomainError("NOT_CONTACTABLE", "已停止联系或撤回授权，请先处理授权", 409)
        if iv["status"] not in {"waiting", "offered"} or not iv["spec"]:
            raise DomainError("INVALID_TRANSITION", "当前不能确认预约", 409)
        if iv["spec"]["format"] == "ai":
            raise DomainError("AI_NOT_CONFIGURED", "AI 初面尚未启用", 409)
        if candidate or command.slot_id:
            slot = next((s for s in iv["slots"] if s["id"] == command.slot_id), None)
            if not slot or datetime.fromisoformat(slot["expires_at"]) <= self.clock.now():
                raise DomainError("SLOT_EXPIRED", "时段已失效，请联系 HR 重新提供", 409)
            start = datetime.fromisoformat(slot["start"])
        else:
            if not command.start or not command.verified:
                raise DomainError("CALENDAR_CONFIRM_REQUIRED", "请填写时间并确认已核实外部日历")
            start = command.start
        self.store.expire(self.clock.now())
        end, resources = self.validate_slot(iv, start, excluding=iv["id"])
        location = iv["location"] if candidate else command.location
        meeting_url = iv["meeting_url"] if candidate else command.meeting_url
        if iv["spec"]["format"] == "onsite" and not location:
            raise DomainError("LOCATION_REQUIRED", "现场面试须由 HR 填写地址和到访说明")
        if iv["spec"]["format"] == "video" and not self.gateway and not meeting_url:
            raise DomainError("MEETING_REQUIRED", "腾讯会议尚未配置，请 HR 填写已核实的会议链接")
        if meeting_url and (
            urlparse(meeting_url).scheme != "https"
            or not urlparse(meeting_url).hostname
            or urlparse(meeting_url).username
        ):
            raise DomainError("MEETING_URL_INVALID", "会议链接须为有效 HTTPS 地址")
        self.store.release(iv["id"])
        for resource, low, high in resources:
            self.store.reserve(iv["id"], resource, new_id("BOOK"), low, high, None)
        iv.update(
            status="scheduled",
            start=start.isoformat(),
            end=end.isoformat(),
            slots=[],
            location=location,
            meeting_url=meeting_url,
            recording_consent=command.recording_consent if candidate else False,
            integration={
                "state": "pending" if self.gateway else "manual",
                "generation": iv["integration"]["generation"] + 1,
                "meeting": None,
                "calendar": None,
                "attempts": 0,
            },
        )
        for r in iv["requests"]:
            r["status"] = "handled"

    def command(self, ctx, iid, command, cid=None):
        self.org.lock_configuration()
        candidate = cid is not None
        action = command.action
        iv = (
            self.candidate_authorize(cid, iid)
            if candidate
            else self.authorize(
                ctx, iid, edit=action not in {"feedback", "remark", "request_reschedule"}
            )
        )
        if iv["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "面试安排已更新，请刷新核对", 409)
        if candidate and action not in {"book", "request_reschedule"}:
            raise DomainError("FORBIDDEN", "候选人不能执行此操作", 403)
        if not candidate and action in {"feedback", "remark", "request_reschedule"}:
            if not self.assigned(iv, ctx.principal):
                raise DomainError("FORBIDDEN", "当前身份不具备本场面试官权限", 403)
        if action == "configure":
            if iv["status"] != "needs_configuration":
                raise DomainError("PLAN_FROZEN", "面试流程已快照，不能覆盖在途流程", 409)
            pos = self.positions.get(ctx, iv["position_id"])
            if not pos["interviewPlans"]:
                raise DomainError("PLAN_REQUIRED", "请先在岗位中配置面试流程")
            iv.update(
                plan=deepcopy(pos["interviewPlans"][-1]),
                spec=deepcopy(pos["interviewPlans"][-1]["rounds"][0]),
                status="waiting",
            )
        elif action == "offer":
            self.validate_meeting_url(command.meeting_url)
            iv.update(location=command.location, meeting_url=command.meeting_url)
            if iv["spec"] and iv["spec"]["format"] == "onsite" and not command.location:
                raise DomainError("LOCATION_REQUIRED", "请先填写面试地址")
            if (
                iv["spec"]
                and iv["spec"]["format"] == "video"
                and (not command.meeting_url or urlparse(command.meeting_url).scheme != "https")
                and not self.gateway
            ):
                raise DomainError("MEETING_REQUIRED", "请先填写已核实的 HTTPS 会议链接")
            self.offer(iv, command.verified)
        elif action == "book":
            self.book(iv, command, candidate)
        elif action == "request_reschedule":
            if not command.reason or iv["status"] not in {"offered", "scheduled"}:
                raise DomainError("INVALID_TRANSITION", "请在约面中或已确定的面试填写改期原因", 409)
            if not candidate and ctx.principal.user_id not in iv["spec"]["interviewers"]:
                raise DomainError("FORBIDDEN", "仅本场面试官可申请改期", 403)
            iv["requests"].append(
                {
                    "actor": ctx.principal.user_id,
                    "reason": command.reason,
                    "status": "pending",
                    "at": self.clock.now().isoformat(),
                }
            )
            # A request keeps the existing booking until HR coordinates replacement.
            if (
                candidate
                and iv["start"]
                and datetime.fromisoformat(iv["start"]) - self.clock.now() >= timedelta(hours=2)
                and iv["candidate_reschedules"] < 2
                and not self.gateway
            ):
                self.reset(iv)
                iv["candidate_reschedules"] += 1
            # Requests inside 2h, third requests and interviewer requests always go to HR.
        elif action == "reschedule":
            if iv["status"] not in {"scheduled", "offered", "no_show"} or not command.reason:
                raise DomainError("REASON_REQUIRED", "请选择可改期面试并填写原因", 409)
            self.reset(iv)
        elif action == "cancel":
            if iv["status"] in TERMINAL or not command.reason:
                raise DomainError("INVALID_TRANSITION", "当前不可取消或缺少原因", 409)
            self.cancel_record(ctx, iv, command.reason)
            return {"id": iid}
        elif action in {"complete", "no_show"}:
            if iv["status"] != "scheduled" or not command.reason:
                raise DomainError("INVALID_TRANSITION", "请填写已确定面试的实际结果", 409)
            if self.clock.now() < datetime.fromisoformat(
                iv["end"] if action == "complete" else iv["start"]
            ) + (timedelta(minutes=15) if action == "no_show" else timedelta()):
                raise DomainError("TOO_EARLY", "尚未到面试结束或缺席确认时间", 409)
            iv.update(
                status="awaiting_feedback" if action == "complete" else "no_show",
                ended_at=self.clock.now().isoformat(),
            )
            # Keep historical reservations for workload counting; they no longer block future time.
        elif action == "feedback":
            self.feedback(ctx, iv, command)
        elif action == "remark":
            if ctx.principal.user_id not in iv["feedback"] or not command.reason:
                raise DomainError("FEEDBACK_REQUIRED", "请先提交本人面评并填写备注", 409)
            iv["feedback"][ctx.principal.user_id].setdefault("remarks", []).append(
                {"text": command.reason, "at": self.clock.now().isoformat()}
            )
        elif action == "retry_integration":
            if not self.gateway:
                raise DomainError(
                    "INTEGRATION_NOT_CONFIGURED", "飞书日历 / 腾讯会议适配器尚未配置", 409
                )
            if (
                iv["integration"]["state"]
                not in {"failed", "uncertain_meeting", "uncertain_calendar"}
                or iv["status"] != "scheduled"
            ):
                raise DomainError("INVALID_TRANSITION", "请先完成失败清理后再重试", 409)
            task = iv["integration"]
            if task["state"] == "failed":
                task["generation"] += 1
            task.update(
                state="calendar_pending" if task["state"] == "uncertain_calendar" else "pending",
                attempts=0,
            )
        self.save(ctx, iv, action)
        return {"id": iid}

    def reset(self, iv):
        self.check_external_uncertainty(iv)
        if iv["integration"].get("meeting") or iv["integration"].get("calendar"):
            raise DomainError(
                "EXTERNAL_CLEANUP_REQUIRED", "请先取消原面试并清理外部日程，再重新安排", 409
            )
        self.store.release(iv["id"])
        iv.update(status="waiting", start=None, end=None, slots=[], ended_at=None, reminders=[])
        iv["integration"]["state"] = "not_requested"

    def cancel_record(self, ctx, iv, reason):
        self.check_external_uncertainty(iv)
        self.store.release(iv["id"])
        iv.update(status="cancelled", slots=[], cancellation_reason=reason)
        for request in iv["requests"]:
            request["status"] = "handled"
        if iv["integration"].get("meeting") or iv["integration"].get("calendar"):
            iv["integration"]["state"] = "cleanup"
        else:
            iv["integration"]["state"] = "cancelled"
        self.save(ctx, iv, "cancelled")

    @staticmethod
    def validate_meeting_url(value):
        if value and (
            urlparse(value).scheme != "https"
            or not urlparse(value).hostname
            or urlparse(value).username
        ):
            raise DomainError("MEETING_URL_INVALID", "会议链接须为有效 HTTPS 地址")

    @staticmethod
    def check_external_uncertainty(iv):
        task = iv["integration"]
        if task["state"].startswith("uncertain_") or (
            task["state"] in {"pending", "calendar_pending"} and task.get("attempts", 0)
        ):
            raise DomainError(
                "INTEGRATION_UNCERTAIN", "外部请求结果待核实，请使用原请求重试查询后再调整安排", 409
            )

    def cancel_application(self, ctx, aid):
        for iv in self.store.all():
            if iv["application_id"] == aid and iv["status"] not in TERMINAL:
                self.cancel_record(ctx, iv, "应聘阶段或结果变更")

    def guard_merge(self, ids):
        if any(
            i["candidate_id"] in ids
            and i["status"] in {"scheduled", "offered", "awaiting_feedback"}
            for i in self.store.all()
        ):
            raise DomainError(
                "INTERVIEW_ACTIVE_MERGE", "请先处理已约面试和占位，再合并或拆分档案", 409
            )

    def erase(self, ids):
        if any(
            i["candidate_id"] in ids
            and (i["integration"].get("meeting") or i["integration"].get("calendar"))
            for i in self.store.all()
        ):
            raise DomainError(
                "EXTERNAL_CLEANUP_REQUIRED", "请先取消并清理外部面试日程，再删除资料", 409
            )
        self.store.erase(ids)

    def privacy_changed(self, ctx, ids):
        for iv in self.store.all():
            if iv["candidate_id"] in ids and iv["status"] == "offered":
                self.store.release(iv["id"])
                iv.update(status="waiting", slots=[])
                self.save(ctx, iv, "privacy_released")

    def feedback(self, ctx, iv, command):
        uid = ctx.principal.user_id
        if not iv["spec"] or uid not in iv["spec"]["interviewers"]:
            raise DomainError("FORBIDDEN", "面评须由本场指定面试官本人提交", 403)
        if iv["status"] not in {"awaiting_feedback", "completed"}:
            raise DomainError("INVALID_TRANSITION", "请在 HR 确认面试结束后提交面评", 409)
        criteria = list(
            dict.fromkeys(x.strip() for x in iv["spec"]["criteria"].splitlines() if x.strip())
        )
        questions = list(dict.fromkeys(x.strip() for x in iv["must_ask"].splitlines() if x.strip()))
        if not command.verified or command.recused:
            raise DomainError("VERIFICATION_REQUIRED", "请核对内容并确认无亲属关系等回避情形")
        if set(command.scores) != set(criteria) or any(
            type(v) is not int or v not in range(1, 6) for v in command.scores.values()
        ):
            raise DomainError("SCORE_REQUIRED", "请为每个评价维度填写 1–5 分")
        if (
            not command.recommendation
            or not command.strengths
            or (command.recommendation in {"hold", "no"} and not command.concerns)
        ):
            raise DomainError("FEEDBACK_REQUIRED", "请填写结论、优势；待定或不推荐时须填写顾虑")
        if any(not command.answers.get(q, "").strip() for q in questions) or any(
            len(v) > 2000 for v in command.answers.values()
        ):
            raise DomainError("ANSWERS_REQUIRED", "请补齐必问题回答（每项最多 2000 字）")
        old = iv["feedback"].get(uid)
        now = self.clock.now()
        if old and now > datetime.fromisoformat(old["submitted_at"]) + timedelta(hours=24):
            raise DomainError("FEEDBACK_LOCKED", "提交已超过 24 小时，请追加备注", 409)
        if old:
            iv["feedback_history"].append(deepcopy(old))
        iv["feedback"][uid] = {
            "author": uid,
            "scores": command.scores,
            "recommendation": command.recommendation,
            "strengths": command.strengths,
            "concerns": command.concerns,
            "next_focus": command.next_focus,
            "answers": command.answers,
            "submitted_at": old["submitted_at"] if old else now.isoformat(),
            "updated_at": now.isoformat(),
            "remarks": old.get("remarks", []) if old else [],
            "verified": True,
        }
        if len(iv["feedback"]) != len(set(iv["spec"]["interviewers"])):
            return
        votes = [f["recommendation"] in {"yes", "strong_yes"} for f in iv["feedback"].values()]
        rule = iv["spec"]["rule"]
        passed = (
            all(votes)
            if rule == "unanimous"
            else sum(votes) > len(votes) / 2
            if rule == "majority"
            else iv["feedback"][iv["spec"]["decision_by"]]["recommendation"]
            in {"yes", "strong_yes"}
        )
        result = "pass" if passed else "needs_hr_decision"
        later = [
            r
            for r in self.store.all()
            if r["cycle"] == iv["cycle"]
            and r["round_no"] > iv["round_no"]
            and r["status"] != "cancelled"
        ]
        if iv["result"] and iv["result"] != result:
            if any(r["status"] not in {"waiting", "offered"} for r in later):
                raise DomainError(
                    "RESULT_IN_USE", "结论已用于后续面试，请先由 HR 处理后续安排；可追加备注", 409
                )
            for r in later:
                self.cancel_record(ctx, r, "前轮面评结论修订")
            self.applications.interview_stage(ctx, iv["application_id"], "interview")
            later = []
        iv.update(status="completed", result=result)
        if passed and not later:
            if iv["round_no"] < len(iv["plan"]["rounds"]):
                app = self.applications.interview_context(iv["application_id"])
                if app["stage"] != "interview" or app["outcome"]:
                    raise DomainError("APPLICATION_ENDED", "应聘流程已变更", 409)
                self.create_round(ctx, app, iv["plan"], iv["round_no"], iv["cycle"], iv["must_ask"])
            else:
                self.applications.interview_stage(ctx, iv["application_id"], "manager_eval")

    def tick(self):
        self.org.lock_configuration()
        now = self.clock.now()
        self.store.expire(now)
        for iv in self.store.all():
            changed = step(iv, self.gateway)
            if iv["status"] == "offered" and not any(
                datetime.fromisoformat(s["expires_at"]) > now for s in iv["slots"]
            ):
                iv.update(status="waiting", slots=[])
                changed = True
            if iv["status"] == "awaiting_feedback":
                for hour in (2, 24, 48):
                    if now >= datetime.fromisoformat(iv["ended_at"]) + timedelta(hours=hour):
                        for uid in iv["spec"]["interviewers"]:
                            key = f"feedback:{hour}:{uid}"
                            if uid not in iv["feedback"] and not any(
                                r["key"] == key for r in iv["reminders"]
                            ):
                                iv["reminders"].append(
                                    {
                                        "key": key,
                                        "kind": "feedback",
                                        "hours": hour,
                                        "user_id": uid,
                                        "delivery": "in_app",
                                        "at": now.isoformat(),
                                    }
                                )
                                changed = True
            if iv["status"] == "scheduled":
                start = datetime.fromisoformat(iv["start"])
                local = start.astimezone(TZ)
                before_day = (
                    (local - timedelta(days=1))
                    .replace(hour=18, minute=0, second=0, microsecond=0)
                    .astimezone(UTC)
                )
                for kind, at in (
                    ("candidate_day_before", before_day),
                    ("candidate_one_hour", start - timedelta(hours=1)),
                    ("interviewer_15_minutes", start - timedelta(minutes=15)),
                ):
                    if at <= now < start and not any(r["key"] == kind for r in iv["reminders"]):
                        iv["reminders"].append(
                            {"key": kind, "kind": kind, "delivery": "in_app", "at": now.isoformat()}
                        )
                        changed = True
            if changed:
                self.save(SYSTEM, iv, "monitor_updated")
