from app.kernel.types import DomainError

WRITE_ROLES = {"recruiter", "recruiting_lead", "hrbp", "hiring_manager"}
HR_ROLES = WRITE_ROLES - {"hiring_manager"}


class FormDirectory:
    def form_salary_options(self, ctx, dept, page, size, req_id=None):
        if dept not in {row["id"] for row in self.form_departments(ctx, req_id)}:
            raise DomainError("OUT_OF_SCOPE", "该部门不在可选范围内", 403)
        return self.org.form_salary_options(page, size)

    def _form_context(self, ctx, req_id):
        if not WRITE_ROLES.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "当前角色不能使用需求表单目录", 403)
        if not req_id:
            return None
        req = self.get_entity(ctx, req_id)
        if req.status in {"draft", "rejected", "withdrawn"}:
            self._owner(ctx, req)
        elif not (
            req.status == "in_approval"
            and req.current_node == 0
            and req.mode == "proxy"
            and req.chain[0]["approver_id"] == ctx.principal.user_id
        ):
            raise DomainError("FORBIDDEN", "当前不能编辑此需求", 403)
        return req

    def form_departments(self, ctx, req_id=None):
        req = self._form_context(ctx, req_id)
        rows = []
        for dept, parent in self.org.form_departments():
            if dept not in ctx.principal.departments:
                continue
            if req and req.status == "in_approval" and dept != req.dept:
                continue
            if (
                not HR_ROLES.intersection(ctx.principal.roles)
                and self.org.policy(dept).manager_id != ctx.principal.user_id
                and not (req and dept == req.dept)
            ):
                continue
            rows.append({"id": dept, "parent_id": parent})
        ids = {row["id"] for row in rows}
        return [
            {**row, "parent_id": row["parent_id"] if row["parent_id"] in ids else None}
            for row in rows
        ]

    def form_users(self, ctx, dept, query, page, size, selected, req_id=None):
        if dept not in {row["id"] for row in self.form_departments(ctx, req_id)}:
            raise DomainError("OUT_OF_SCOPE", "该部门不在可选范围内", 403)
        users = self.org.form_users(dept)
        eligible = {u.id: u for u in users}
        matches = [u for u in users if query.casefold() in (u.id + " " + u.name).casefold()]
        return {
            "items": [
                {"id": u.id, "name": u.name} for u in matches[(page - 1) * size : page * size]
            ],
            "total": len(matches),
            "selected": [
                {"id": uid, "name": eligible[uid].name, "available": True}
                if uid in eligible
                else {"id": uid, "name": None, "available": False}
                for uid in dict.fromkeys(selected)
            ],
        }

    def _reporting_user(self, fields):
        users = self.org.form_users(fields.get("dept", ""))
        uid = fields.get("reportToId")
        matches = (
            [u for u in users if u.id == uid]
            if uid
            else [u for u in users if u.name == fields.get("reportTo")]
        )
        return matches[0] if len(matches) == 1 else None

    def _normalize_reporting(self, fields, patch=None):
        fields = dict(fields)
        # A name-only legacy edit must not reuse the previous person's ID.
        if patch is not None and "reportTo" in patch and "reportToId" not in patch:
            fields.pop("reportToId", None)
        user = self._reporting_user(fields)
        if user:
            fields.update(reportToId=user.id, reportTo=user.name)
        return fields

    def _people_checks(self, fields, reporting=True, visibility=True):
        checks = []
        if reporting:
            valid = self._reporting_user(fields) is not None
            checks.append(
                {
                    "key": "manager",
                    "label": "汇报对象",
                    "status": "pass" if valid else "block",
                    "detail": "在职且具备该部门范围"
                    if valid
                    else "汇报对象已失效、超出部门范围或姓名不唯一，请重新选择",
                }
            )
        if visibility:
            selected = {
                uid.strip() for uid in fields.get("visibleTo", "").split(",") if uid.strip()
            }
            valid_ids = {u.id for u in self.org.form_users(fields.get("dept", ""))}
            if selected - valid_ids or len(selected) > 50:
                checks.append(
                    {
                        "key": "visible_users",
                        "label": "可见人员",
                        "status": "block",
                        "detail": "可见人员已失效或超出部门范围，请重新选择（最多 50 人）",
                    }
                )
        return checks

    def _visible_users(self, fields):
        checks = self._people_checks(fields, reporting=False)
        if checks:
            raise DomainError(
                "REQ_VISIBLE_USER_INVALID", checks[0]["detail"], details={"checks": checks}
            )
