from app.modules.requisition.application.commands import RequisitionCommands


class RequisitionFacade(RequisitionCommands):
    def pending_approvals(self, ctx):
        return [
            self.dto(req)
            for req in self.repo.open_requests()
            if req.status == "in_approval"
            and self._visible(ctx, req)
            and req.chain[req.current_node]["approver_id"] == ctx.principal.user_id
        ]

    def set_position_readers(self, req_id, user_ids):
        from app.kernel.types import DomainError

        req = self.repo.get(req_id)
        if not req or req.status != "approved":
            raise DomainError("APPROVED_SOURCE_INVALID", "岗位来源必须为已通过需求")
        self.repo.set_position_readers(req_id, user_ids)

    def approved_snapshot(self, req_id, version):
        from app.kernel.types import DomainError

        req = self.repo.get(req_id)
        if not req or req.status != "approved" or req.version != version:
            raise DomainError("APPROVED_SOURCE_INVALID", "审批事件与已通过需求不一致")
        return self.dto(req, detail=True)

    def get(self, ctx, req_id):
        return self.dto(self.get_entity(ctx, req_id), detail=True)

    def search(self, ctx, filters, page):
        items, total = self.repo.search(ctx.principal, page[0], page[1], filters.get("status"))
        return {
            "items": [self.dto(r) for r in items],
            "total": total,
            "page": page[0],
            "size": page[1],
        }

    def precheck(self, ctx, req_id):
        return self.precheck_fields(ctx, self.get_entity(ctx, req_id).fields)

    def approve(self, ctx, req_id, node_id, comment, expected_version):
        return self.decide(ctx, req_id, node_id, expected_version, approve=True, comment=comment)

    def reject(self, ctx, req_id, node_id, reason, expected_version):
        return self.decide(ctx, req_id, node_id, expected_version, approve=False, comment=reason)

    def resubmit(self, ctx, req_id, expected_version):
        return self.submit(ctx, req_id, expected_version)
