from datetime import datetime

from app.kernel.types import Ctx, DomainError, Principal


class TransferCommands:
    @staticmethod
    def _node_role(node):
        return "hc" if node.get("note") == "发起人本人，已上推" else node["id"]

    def _current_actor(self, ctx, req):
        if req.status != "in_approval":
            raise DomainError("INVALID_TRANSITION", "仅审批中的需求可转交", 409)
        node = req.chain[req.current_node]
        if node["approver_id"] != ctx.principal.user_id:
            raise DomainError("FORBIDDEN", "只有当前节点审批人可以转交", 403)
        self.org.check_approver(ctx.principal.user_id, req.dept, self._node_role(node))
        return node

    def _transfer_target(self, req, node, target):
        if not target:
            raise DomainError("REQ_SUPERVISOR_MISSING", "缺少已核验的直属上级，请修复目录后重试")
        forbidden = {req.creator_id, node["approver_id"]}
        # The proxy confirmation itself belongs to a manager; later nodes cannot return to them.
        if node["id"] != "manager":
            forbidden.add(req.manager_id)
            if req.owner_id:
                forbidden.add(req.owner_id)
        if target in forbidden:
            raise DomainError("REQ_TRANSFER_SELF", "不能转给本人、发起人或该需求的归属负责人")
        return self.org.check_approver(target, req.dept, self._node_role(node))

    def transfer_candidates(self, ctx, req_id, query, page, size):
        req = self.get_entity(ctx, req_id)
        node = self._current_actor(ctx, req)
        items = []
        for user in self.org.transfer_candidates(req.dept, self._node_role(node), query):
            try:
                self._transfer_target(req, node, user.id)
            except DomainError:
                continue
            items.append({"id": user.id, "name": user.name})
        return {
            "items": items[(page - 1) * size : page * size],
            "total": len(items),
            "page": page,
            "size": size,
            "version": req.version,
        }

    def _record_transfer(self, ctx, req, node, target, reason, event=None):
        action = "auto_transferred" if event else "transferred"
        req.chain = [dict(n) for n in req.chain]
        req.chain[req.current_node].update(approver_id=target.id, approver=target.name)
        req.history.append(
            {
                "action": action,
                "actor_id": "directory-system" if event else ctx.principal.user_id,
                "node_id": node["id"],
                "from_id": node["approver_id"],
                "to_id": target.id,
                "from_name": node["approver"],
                "to_name": target.name,
                "comment": reason,
                "at": self.clock.now().isoformat(),
                **({"source_event_id": event["event_id"]} if event else {}),
            }
        )
        self.transfers.notify(
            req,
            action,
            [req.owner_id or req.creator_id, req.manager_id, target.id],
            self.clock.now(),
        )

    def transfer(self, ctx, req_id, command):
        # Serialize with role/config writes so a concurrently revoked target cannot be assigned.
        self.org.lock_configuration()
        req = self.get_entity(ctx, req_id)
        self._version(req, command.expected_version)
        node = self._current_actor(ctx, req)
        if node["id"] != command.node_id:
            raise DomainError("VERSION_CONFLICT", "审批节点已改变，请刷新后重试", 409)
        if not command.reason.strip():
            raise DomainError("REQ_TRANSFER_REASON_REQUIRED", "转交原因不能为空")
        target = self._transfer_target(req, node, command.target_id)
        old = self._snapshot(req)
        self._record_transfer(ctx, req, node, target, command.reason.strip())
        return self._save(ctx, req, old, "requisition.transferred")

    def _blocked(self, ctx, req, event, task, error):
        # Repeated delivery of an unresolved event must not spam history/notices.
        prior = [
            h
            for h in req.history
            if h.get("source_event_id") == event["event_id"] and h.get("task") == task
        ]
        if prior and prior[-1]["action"] == "transfer_blocked":
            return
        req.history.append(
            {
                "action": "transfer_blocked",
                "task": task,
                "source_event_id": event["event_id"],
                "actor_id": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "comment": "组织变更待处理：" + error.message,
            }
        )
        self.transfers.notify(
            req,
            "transfer_blocked",
            [req.owner_id or req.creator_id, req.manager_id],
            self.clock.now(),
        )

    def _current_event(self, req):
        if req.status != "in_approval":
            return
        node = req.chain[req.current_node]
        event = self.transfers.change_for(node["approver_id"])
        if not event or (req.submitted_at and req.submitted_at > event["received_at"]):
            return
        if any(
            h["action"] == "transferred"
            and h.get("node_id") == node["id"]
            and h.get("to_id") == node["approver_id"]
            and datetime.fromisoformat(h["at"]) >= event["received_at"]
            for h in req.history
        ):
            return  # A later explicit, permission-checked reassignment supersedes this event.
        return event

    def reconcile_current(self, ctx, req):
        event = self._current_event(req)
        if not event:
            return
        node = req.chain[req.current_node]
        # Only current nodes move. Future nodes are reconciled when they become current.
        try:
            target = self._transfer_target(req, node, event["supervisor_id"])
        except DomainError as error:
            self._blocked(ctx, req, event, node["id"], error)
            return
        self._record_transfer(ctx, req, node, target, "组织变更自动转交", event)

    def consume_directory_change(self, command):
        """Trusted internal consumer only: the directory adapter must import and verify first."""
        self.org.lock_configuration()
        event = command.model_dump()
        identity = self.org.identity(command.user_id)
        if not identity or identity["version"] < command.source_version:
            raise DomainError("DIRECTORY_NOT_READY", "请先导入并核验对应版本的目录变更", 409)
        latest = self.transfers.change_for(command.user_id)
        if latest and latest["source_version"] > command.source_version:
            raise DomainError("EVENT_STALE", "已有更新的目录事件，不能重放旧的汇报关系", 409)
        if command.kind == "left" and identity["active"]:
            raise DomainError("DIRECTORY_NOT_READY", "离职事件与已导入的在职状态不一致", 409)
        if command.kind == "moved" and not identity["active"]:
            raise DomainError("DIRECTORY_NOT_READY", "调岗事件对应人员已离职，请核验事件类型", 409)
        if not latest or latest["event_id"] != command.event_id:
            if identity["version"] != command.source_version:
                raise DomainError("EVENT_STALE", "事件版本与当前目录版本不一致", 409)
        self.transfers.accept(event, self.clock.now())
        ctx = Ctx(Principal("directory-system", "组织变更", (), ()), command.event_id)
        results = []
        for req in self.repo.open_requests():
            before = len(req.history)
            old = self._snapshot(req)
            if command.kind == "left" and (
                (req.owner_id or req.creator_id) == command.user_id
                or (req.owner_id is None and req.manager_id == command.user_id)
            ):
                try:
                    target = self.org.check_approver(
                        self.org.policy(req.dept).director_id, req.dept, "director"
                    )
                    if target.id == command.user_id:
                        raise DomainError("REQ_OWNER_UNAVAILABLE", "需求部门负责人也已离职")
                    req.owner_id = target.id
                    req.history.append(
                        {
                            "action": "owner_transferred",
                            "task": "owner",
                            "actor_id": ctx.principal.user_id,
                            "source_event_id": command.event_id,
                            "from_id": command.user_id,
                            "to_id": target.id,
                            "from_name": identity["name"],
                            "to_name": target.name,
                            "comment": "发起人离职，已交接需求部门负责人",
                            "at": self.clock.now().isoformat(),
                        }
                    )
                    self.transfers.notify(req, "owner_transferred", [target.id], self.clock.now())
                except DomainError as error:
                    self._blocked(ctx, req, event, "owner", error)
            self.reconcile_current(ctx, req)
            if len(req.history) != before:
                self._save(ctx, req, old, "requisition.organization_changed")
                results.append({"id": req.id, "version": req.version})
        pending = []
        for req in self.repo.open_requests():
            owner_pending = command.kind == "left" and (
                (req.owner_id or req.creator_id) == command.user_id
                or (req.owner_id is None and req.manager_id == command.user_id)
            )
            current_event = self._current_event(req)
            node_pending = (
                current_event is not None and current_event["event_id"] == command.event_id
            )
            if owner_pending or node_pending:
                pending.append({"id": req.id, "owner": owner_pending, "approval": node_pending})
        return {"event_id": command.event_id, "changed": results, "pending": pending}

    def notifications(self, ctx):
        items = []
        for notice in self.transfers.notices(ctx.principal.user_id):
            req = self.repo.get(notice.requisition_id)
            if req and self._visible(ctx, req):
                items.append(
                    {
                        "id": notice.id,
                        "requisition_id": req.id,
                        "action": notice.action,
                        "at": notice.at.isoformat(),
                        "title": req.fields.get("title") or "未命名需求",
                    }
                )
        return items
