from dataclasses import asdict

from app.kernel.types import Clock, Ctx, DomainError, Journal, new_id
from app.modules.requisition.domain.model import Requisition
from app.modules.requisition.domain.rules import precheck_fields, salary_range
from app.modules.requisition.domain.state import transition
from app.modules.requisition.ports import Organization, Repository

HR_ROLES = {"recruiter", "recruiting_lead", "hrbp"}
WRITE_ROLES = HR_ROLES | {"hiring_manager"}


class RequisitionCommands:
    def __init__(self, repo: Repository, org: Organization, clock: Clock, journal: Journal):
        self.repo, self.org, self.clock, self.journal = repo, org, clock, journal

    def _dept(self, ctx, dept):
        if not WRITE_ROLES.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "当前角色不能发起招聘需求", 403)
        if dept not in ctx.principal.departments:
            raise DomainError("OUT_OF_SCOPE", "该部门不在你的数据范围内", 403)
        return self.org.policy(dept)

    def _visible(self, ctx, req):
        p = ctx.principal
        actors = {req.creator_id, req.manager_id, *(n["approver_id"] for n in req.chain)}
        actors.update(x.strip() for x in req.fields.get("visibleTo", "").split(",") if x.strip())
        return p.user_id in actors or (
            req.fields.get("confidential") != "1"
            and req.dept in p.departments
            and bool(HR_ROLES.intersection(p.roles))
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
        if ctx.principal.user_id not in {req.creator_id, req.manager_id}:
            raise DomainError("FORBIDDEN", "只有发起人或用人经理可以修改此需求", 403)

    def _validate_fields(self, fields):
        if len(fields) > 50 or any(len(k) > 100 or len(v) > 4000 for k, v in fields.items()):
            raise DomainError("VALIDATION_ERROR", "表单字段过多或内容过长", 400)
        return {k: v.strip() for k, v in fields.items()}

    def _visible_users(self, fields):
        for user_id in fields.get("visibleTo", "").split(","):
            if user_id.strip():
                self.org.get_user(user_id.strip())

    def precheck_fields(self, ctx, fields):
        fields = self._validate_fields(fields)
        if not fields.get("dept"):
            return [
                {"key": "dept", "label": "需求部门", "status": "block", "detail": "请先选择部门"}
            ]
        policy = self._dept(ctx, fields["dept"])
        return precheck_fields(
            fields,
            self.clock.now().date(),
            policy.available_hc,
            policy.salary_max,
            self.org.get_user(policy.manager_id).name,
        )

    def approval_chain(self, ctx, fields):
        if not fields.get("dept"):
            return []
        policy = self._dept(ctx, fields["dept"])
        salary = salary_range(fields.get("salary", ""))
        return [
            asdict(n)
            for n in self.org.resolve_approval_chain(
                "requisition",
                policy.id,
                {
                    "proxy": ctx.principal.user_id != policy.manager_id,
                    "actor_id": ctx.principal.user_id,
                    "hc_request": fields.get("hcRequest", "0") not in {"", "0"},
                    "salary_over": bool(salary and salary[1] > policy.salary_max),
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
        self._visible_users(fields)
        fields["dept"] = dept
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
        fields = self._validate_fields({**req.fields, **patch})
        policy = self._dept(ctx, fields["dept"])
        self._visible_users(fields)
        req.fields, req.dept, req.manager_id = fields, policy.id, policy.manager_id
        req.mode = "self" if req.creator_id == policy.manager_id else "proxy"
        return self._save(ctx, req, old, "requisition.draft_updated", False)

    def submit(self, ctx, req_id, expected_version):
        req = self.get_entity(ctx, req_id)
        self._owner(ctx, req)
        self._version(req, expected_version)
        next_state = transition(req.status, "submit")
        checks = self.precheck_fields(ctx, req.fields)
        blocked = [c for c in checks if c["status"] == "block"]
        if blocked:
            raise DomainError(
                "REQ_PENDING_DECISIONS", "预检未通过，请处理后再提交", details={"checks": blocked}
            )
        old = self._snapshot(req)
        req.chain = self.approval_chain(ctx, req.fields)
        req.current_node = 0
        req.submitted_at = self.clock.now()
        req.status = next_state
        req.history.append(
            {
                "action": "submitted",
                "actor_id": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "chain": req.chain,
            }
        )
        return self._save(ctx, req, old, "requisition.submitted")

    def decide(self, ctx, req_id, node_id, expected_version, *, approve, comment):
        req = self.get_entity(ctx, req_id)
        self._version(req, expected_version)
        next_state = transition(req.status, "approve" if approve else "reject")
        node = req.chain[req.current_node]
        if node["id"] != node_id or node["approver_id"] != ctx.principal.user_id:
            raise DomainError("FORBIDDEN", "只有当前节点审批人可以处理", 403)
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
                req.status = next_state
        else:
            req.status = next_state
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
            "initiator": self.org.get_user(req.manager_id).name,
            "mode": req.mode,
            "proxyBy": self.org.get_user(req.creator_id).name if req.mode == "proxy" else None,
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
            )
        return result
