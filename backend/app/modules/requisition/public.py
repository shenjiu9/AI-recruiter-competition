from app.modules.requisition.application.commands import RequisitionCommands


class RequisitionFacade(RequisitionCommands):
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
