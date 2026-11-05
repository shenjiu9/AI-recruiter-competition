from dataclasses import asdict

from app.kernel.types import Clock, Ctx, DomainError, Journal, new_id
from app.modules.requisition.application.form_directory import HR_ROLES, WRITE_ROLES, FormDirectory
from app.modules.requisition.application.transfers import TransferCommands
from app.modules.requisition.domain.model import Requisition
from app.modules.requisition.domain.rules import precheck_fields, salary_range
from app.modules.requisition.domain.state import transition
from app.modules.requisition.ports import Organization, Repository

CONFIRM_FIELDS = {
    "recruitType",
    "employmentType",
    "reqType",
    "headcount",
    "title",
    "series",
    "level",
    "city",
    "reportTo",
    "reportToId",
    "expectedOnboard",
    "salary",
    "reason",
    "duties",
    "requirements",
    "hcRequest",
    "replacementIds",
    "positionId",
    "country",
    "highlights",
}


class RequisitionCommands(FormDirectory, TransferCommands):
    def __init__(
        self, repo: Repository, org: Organization, clock: Clock, journal: Journal, transfers
    ):
        self.repo, self.org, self.clock, self.journal = repo, org, clock, journal
        self.transfers = transfers

    def _dept(self, ctx, dept):
        if not WRITE_ROLES.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "当前角色不能发起招聘需求", 403)
        if dept not in ctx.principal.departments:
            raise DomainError("OUT_OF_SCOPE", "该部门不在你的数据范围内", 403)
        return self.org.policy(dept)

    def _visible(self, ctx, req):
        p = ctx.principal
        if not {
            "recruiter",
            "recruiting_lead",
            "hiring_manager",
            "hrbp",
            "hrd",
            "headcount_owner",
        }.intersection(p.roles):
            return False
        actors = {req.creator_id, req.manager_id, *(n["approver_id"] for n in req.chain)}
        actors.add(req.owner_id)
        actors.update(x.strip() for x in req.fields.get("visibleTo", "").split(",") if x.strip())
        return p.user_id in actors or (
            req.fields.get("confidential") != "1"
            and req.dept in p.departments
            and bool({"recruiting_lead", "hiring_manager", "hrbp"}.intersection(p.roles))
        )

    def get_entity(self, ctx, req_id):
        req = self.repo.get(req_id)
        if not req or not self._visible(ctx, req):
            raise DomainError("NOT_FOUND", "招聘需求不存在", 404)
        return req

    def _version(self, req, expected):
        if req.version != expected:
            raise DomainError(
                "VERSION_CONFLICT",
                "需求已被修改，请刷新后重试",
                409,
                {"current_version": req.version},
            )

    def _owner(self, ctx, req):
        if ctx.principal.user_id not in {req.owner_id or req.creator_id, req.manager_id}:
            raise DomainError("FORBIDDEN", "只有发起人或用人经理可以修改此需求", 403)

    def _validate_fields(self, fields):
        if len(fields) > 50 or any(len(k) > 100 or len(v) > 4000 for k, v in fields.items()):
            raise DomainError("VALIDATION_ERROR", "表单字段过多或内容过长", 400)
        return {k: v.strip() for k, v in fields.items()}

    def _salary_check(self, fields):
        return self.org.salary_check(
            fields.get("series", ""),
            fields.get("level", ""),
            fields.get("city", ""),
            salary_range(fields.get("salary", "")),
        )

    def precheck_fields(self, ctx, fields, salary_result=None, *, reporting=True, visibility=True):
        fields = self._validate_fields(fields)
        if not fields.get("dept"):
            return [
                {"key": "dept", "label": "需求部门", "status": "block", "detail": "请先选择部门"}
            ]
        policy = self._dept(ctx, fields["dept"])
        budget = self.org.headcount(policy.id)
        today = self.clock.now().date()
        active = budget is not None and budget["effective_from"] <= today
        checks = precheck_fields(
            fields,
            today,
            budget["available"] if active and not budget["frozen"] else 0,
        )
        checks.extend(self._people_checks(fields, reporting, visibility))
        checks.extend((salary_result or self._salary_check(fields))["checks"])
        if fields.get("employmentType") == "正式":
            checks.append(
                {
                    "key": "hc_plan",
                    "label": "年度编制表",
                    "status": "pass" if active else "block",
                    "detail": "年度编制已生效"
                    if active
                    else "缺少本年度已生效编制，请联系 HRBP 或编制负责人维护",
                }
            )
            if active and budget["frozen"]:
                checks.append(
                    {
                        "key": "hc_frozen",
                        "label": "编制冻结",
                        "status": "block",
                        "detail": "编制已冻结，请联系维护人解冻后提交",
                    }
                )
            if active and (today - budget["updated_on"]).days > 30:
                checks.append(
                    {
                        "key": "hc_stale",
                        "label": "编制更新时间",
                        "status": "warn",
                        "detail": "编制数据超过 30 天未维护，可能过期",
                    }
                )
        return checks

    def approval_chain(self, ctx, fields, salary_result=None):
        if not fields.get("dept"):
            return []
        policy = self._dept(ctx, fields["dept"])
        salary_result = salary_result or self._salary_check(fields)
        return [
            asdict(n)
            for n in self.org.resolve_approval_chain(
                "requisition",
                policy.id,
                {
                    "proxy": ctx.principal.user_id != policy.manager_id,
                    "actor_id": ctx.principal.user_id,
                    "hc_request": fields.get("hcRequest", "0") not in {"", "0"},
                    "salary_over": salary_result["over"],
                },
            )
        ]

    def _snapshot(self, req):
        # Audit metadata never contains salary, free text, contact data or credentials.
        return {"status": req.status, "version": req.version, "current_node": req.current_node}

    def _save(self, ctx, req, old, action, event=True):
        previous = req.version
        req.version += 1
        self.repo.save(req, previous)
        self.journal.record(ctx, action, req.id, req.version, old, self._snapshot(req), event)
        return self.dto(req, detail=True)

    def create_draft(self, ctx: Ctx, cmd: dict) -> dict:
        fields = self._validate_fields(cmd)
        dept = fields.get("dept") or next(iter(ctx.principal.departments), "")
        policy = self._dept(ctx, dept)
        if (
            "hiring_manager" in ctx.principal.roles
            and not HR_ROLES.intersection(ctx.principal.roles)
            and ctx.principal.user_id != policy.manager_id
        ):
            raise DomainError("FORBIDDEN", "只能为自己负责的部门发起需求", 403)
        fields["dept"] = dept
        fields = self._normalize_reporting(fields)
        self._visible_users(fields)
        req = Requisition(
            new_id("REQ"),
            1,
            ctx.principal.user_id,
            policy.manager_id,
            dept,
            "draft",
            fields,
            self.clock.now(),
            mode="self" if ctx.principal.user_id == policy.manager_id else "proxy",
        )
        self.repo.add(req)
        self.journal.record(
            ctx, "requisition.draft_created", req.id, req.version, None, self._snapshot(req), False
        )
        return self.dto(req, detail=True)

    def update_draft(self, ctx, req_id, patch, expected_version):
        req = self.get_entity(ctx, req_id)
        self._owner(ctx, req)
        self._version(req, expected_version)
        if req.status not in {"draft", "rejected", "withdrawn"}:
            raise DomainError("INVALID_TRANSITION", "只能编辑草稿、已驳回或已撤回的需求", 409)
        old = self._snapshot(req)
        fields = self._normalize_reporting(self._validate_fields({**req.fields, **patch}), patch)
        policy = self._dept(ctx, fields["dept"])
        self._visible_users(fields)
        if policy.id != req.dept and policy.id not in {
            d["id"] for d in self.form_departments(ctx, req_id)
        }:
            raise DomainError("OUT_OF_SCOPE", "该部门不在可选范围内", 403)
        req.fields, req.dept, req.manager_id = fields, policy.id, policy.manager_id
        req.mode = "self" if req.creator_id == policy.manager_id else "proxy"
        return self._save(ctx, req, old, "requisition.draft_updated", False)

    def submit(self, ctx, req_id, expected_version):
        req = self.get_entity(ctx, req_id)
        self._owner(ctx, req)
        self._version(req, expected_version)
        next_state = transition(req.status, "submit")
        req.fields = self._normalize_reporting(req.fields)
        salary_result = self._salary_check(req.fields)
        checks = self.precheck_fields(ctx, req.fields, salary_result)
        blocked = [c for c in checks if c["status"] == "block"]
        if blocked:
            raise DomainError(
                "REQ_PENDING_DECISIONS", "预检未通过，请处理后再提交", details={"checks": blocked}
            )
        old = self._snapshot(req)
        # Routing is based on the original creator, even if the manager submits an HR draft.
        policy = self.org.policy(req.dept)
        req.manager_id = policy.manager_id
        req.mode = "self" if req.creator_id == req.manager_id else "proxy"
        req.approval_policy = asdict(policy)
        req.salary_review = salary_result
        req.chain = self._confirmation_chain(req, req.fields, salary_result)
        # Snapshot the exceptional final approver, too: later directory policy changes
        # must not silently redirect an in-flight request to a different approver.
        policy = self.org.policy(req.dept)
        hc_user = self.org.get_user(policy.hc_owner_id)
        req.hc_approver = {
            "id": "hc_final",
            "name": "终审编制复核",
            "approver_id": hc_user.id,
            "approver": hc_user.name,
            "note": "请先确认编制已补足且未冻结，再通过审批",
        }
        req.current_node = 0
        req.submitted_at = self.clock.now()
        req.status = next_state
        req.history.append(
            {
                "action": "submitted",
                "actor_id": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "chain": req.chain,
                "salary_rules": salary_result["refs"],
                "changes": {
                    key: {"before": req.submitted_fields.get(key, ""), "after": value}
                    for key, value in req.fields.items()
                    if req.submitted_fields is not None
                    and value != req.submitted_fields.get(key, "")
                },
            }
        )
        req.submitted_fields = dict(req.fields)
        return self._save(ctx, req, old, "requisition.submitted")

    def _confirmation_chain(self, req, fields, salary_result, preserve_existing=False):
        return [
            asdict(n)
            for n in self.org.resolve_approval_chain(
                "requisition",
                req.dept,
                {
                    "proxy": req.mode == "proxy",
                    "actor_id": req.creator_id,
                    "owner_id": req.owner_id,
                    "hc_request": fields.get("hcRequest", "0") not in {"", "0"},
                    "salary_over": salary_result["over"],
                    "retained_nodes": {n["id"]: n for n in req.chain} if preserve_existing else {},
                },
                req.approval_policy,
            )
        ]

    def _confirmation(self, ctx, req, patch, expected_version):
        self._version(req, expected_version)
        if req.status != "in_approval" or req.current_node != 0 or req.mode != "proxy":
            raise DomainError("INVALID_TRANSITION", "仅代发起需求的首个确认节点可修改确认", 409)
        node = req.chain[0]
        if node["id"] != "manager" or node["approver_id"] != ctx.principal.user_id:
            raise DomainError("FORBIDDEN", "只有当前归属用人经理可以修改确认", 403)
        self.org.check_approver(ctx.principal.user_id, req.dept, "manager")
        fields = self._validate_fields({**req.fields, **patch})
        reporting_changed = any(
            fields.get(k, "") != req.fields.get(k, "") for k in ("reportTo", "reportToId")
        )
        if reporting_changed:
            fields = self._normalize_reporting(fields, patch)
        changes = {
            k: {"before": req.fields.get(k, ""), "after": v}
            for k, v in fields.items()
            if v != req.fields.get(k, "")
        }
        if set(changes) - CONFIRM_FIELDS:
            raise DomainError(
                "REQ_CONFIRM_FIELD_LOCKED", "确认时不能变更部门、保密范围或负责 HR，请撤回后修改"
            )
        if changes and (req.approval_policy is None or req.salary_review is None):
            raise DomainError(
                "REQ_RESUBMIT_REQUIRED", "旧版需求缺少规则快照，请撤回后重新提交", 409
            )
        salary_changed = bool(set(changes) & {"salary", "series", "level", "city"})
        salary = self._salary_check(fields) if salary_changed else req.salary_review
        # Unedited confirmations preserve the submitted decision. Final HC is always rechecked.
        checks = (
            self.precheck_fields(ctx, fields, salary, reporting=reporting_changed, visibility=False)
            if changes
            else []
        )
        chain = req.chain
        if set(changes) & {"salary", "series", "level", "city", "hcRequest"}:
            proposed = self._confirmation_chain(req, fields, salary, preserve_existing=True)
            existing = {n["id"]: n for n in req.chain}
            chain = [existing.get(n["id"], n) for n in proposed]
        return {
            "fields": fields,
            "changes": changes,
            "checks": checks,
            "chain": chain,
            "salary_rules": salary["refs"] if salary else [],
        }, salary

    def confirmation_preview(self, ctx, req_id, patch, expected_version):
        req = self.get_entity(ctx, req_id)
        preview, _ = self._confirmation(ctx, req, patch, expected_version)
        return {**preview, "version": req.version}

    def confirm(self, ctx, req_id, patch, expected_version, comment=None):
        req = self.get_entity(ctx, req_id)
        preview, salary = self._confirmation(ctx, req, patch, expected_version)
        blocked = [c for c in preview["checks"] if c["status"] == "block"]
        if blocked:
            raise DomainError(
                "REQ_PENDING_DECISIONS", "预检未通过，请处理后再确认", details={"checks": blocked}
            )
        old = self._snapshot(req)
        req.fields, req.chain, req.salary_review = preview["fields"], preview["chain"], salary
        req.current_node = 1
        req.history.append(
            {
                "action": "manager_confirmed",
                "node_id": "manager",
                "actor_id": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "comment": comment,
                "changes": preview["changes"],
                "chain": req.chain,
                "salary_rules": preview["salary_rules"],
            }
        )
        self.reconcile_current(ctx, req)
        return self._save(ctx, req, old, "requisition.manager_confirmed")

    def decide(self, ctx, req_id, node_id, expected_version, *, approve, comment):
        if approve and node_id == "manager":
            return self.confirm(ctx, req_id, {}, expected_version, comment)
        req = self.get_entity(ctx, req_id)
        self._version(req, expected_version)
        next_state = transition(req.status, "approve" if approve else "reject")
        node = req.chain[req.current_node]
        if node["id"] != node_id or node["approver_id"] != ctx.principal.user_id:
            raise DomainError("FORBIDDEN", "只有当前节点审批人可以处理", 403)
        if req.owner_id == ctx.principal.user_id:
            raise DomainError(
                "REQ_OWNER_SELF_APPROVAL", "交接负责人不能自审，请撤回后重新提交审批", 409
            )
        self.org.check_approver(
            ctx.principal.user_id,
            req.dept,
            "hc" if node.get("note") == "发起人本人，已上推" else node_id,
        )
        if not approve and not (comment or "").strip():
            raise DomainError("REQ_REJECT_REASON_REQUIRED", "驳回原因不能为空")
        old = self._snapshot(req)
        req.history.append(
            {
                "action": "approved" if approve else "rejected",
                "node_id": node_id,
                "actor_id": ctx.principal.user_id,
                "comment": comment,
                "at": self.clock.now().isoformat(),
            }
        )
        if approve:
            req.current_node += 1
            if req.current_node == len(req.chain):
                if req.fields.get("employmentType") != "正式" or self.org.reserve_headcount(
                    ctx, req.dept, req.id, int(req.fields["headcount"])
                ):
                    req.status = next_state
                elif node_id == "hc_final":
                    raise DomainError(
                        "HC_UNAVAILABLE", "编制不足、冻结或尚未生效，请先维护编制，再重新审批", 409
                    )
                else:
                    if req.hc_approver is None:
                        raise DomainError(
                            "HC_RESUBMIT_REQUIRED",
                            "旧版需求缺少编制复核人快照，请撤回后重新提交",
                            409,
                        )
                    if req.hc_approver["approver_id"] in {req.creator_id, req.manager_id}:
                        raise DomainError(
                            "REQ_APPROVER_UNAVAILABLE",
                            "编制复核人不能自审，请配置其他负责人并重新提交",
                            409,
                        )
                    req.chain.append(dict(req.hc_approver))
                    req.history.append(
                        {
                            "action": "hc_review_added",
                            "actor_id": ctx.principal.user_id,
                            "at": self.clock.now().isoformat(),
                            "comment": "终审编制不足、冻结或未生效，已加签编制负责人；尚未预占名额",
                        }
                    )
        else:
            req.status = next_state
        self.reconcile_current(ctx, req)
        action = (
            "requisition.approved"
            if req.status == "approved"
            else ("requisition.rejected" if not approve else "requisition.node_approved")
        )
        return self._save(ctx, req, old, action)

    def withdraw(self, ctx, req_id, expected_version):
        req = self.get_entity(ctx, req_id)
        self._owner(ctx, req)
        self._version(req, expected_version)
        old = self._snapshot(req)
        req.status = transition(req.status, "withdraw")
        req.history.append(
            {
                "action": "withdrawn",
                "actor_id": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
            }
        )
        return self._save(ctx, req, old, "requisition.withdrawn")

    def _identity_name(self, user_id):
        identity = self.org.identity(user_id)
        return identity["name"] if identity else user_id

    def dto(self, req, detail=False):
        node = req.chain[req.current_node] if req.status == "in_approval" else None
        result = {
            "id": req.id,
            "no": req.id,
            "version": req.version,
            "title": req.fields.get("title") or "未命名需求",
            "dept": req.dept,
            "type": {"新增": "new", "替补": "replace", "追加": "additional"}.get(
                req.fields.get("reqType"), "new"
            ),
            "headcount": int(req.fields["headcount"])
            if req.fields.get("headcount", "").isascii()
            and req.fields.get("headcount", "").isdigit()
            else 0,
            "initiator": self._identity_name(req.manager_id),
            "mode": req.mode,
            "proxyBy": self._identity_name(req.creator_id) if req.mode == "proxy" else None,
            "status": req.status,
            "waitingFor": node["approver"] if node else None,
            "waitingDays": max(0, (self.clock.now() - req.submitted_at).days) if node else 0,
            "submittedAt": req.submitted_at.isoformat() if req.submitted_at else None,
        }
        if detail:
            result.update(
                fields=req.fields,
                chain=req.chain,
                history=req.history,
                currentNode=req.current_node,
                creatorId=req.creator_id,
                managerId=req.manager_id,
                ownerId=req.owner_id or req.creator_id,
            )
        return result
