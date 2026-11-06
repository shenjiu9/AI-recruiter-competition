from hashlib import sha256
from typing import Protocol

from app.kernel.types import DomainError


class HeadcountStore(Protocol):
    def release(self, req_id): ...
    def get(self, dept, year): ...
    def list(self, departments, year): ...
    def save(self, dept, command, today): ...
    def reserve(self, dept, req_id, count, today): ...


class HeadcountService:
    def release_headcount(self, ctx, req_id):
        count = self.hc.release(req_id)
        if count:
            self.journal.record(
                ctx, "org.headcount_released", req_id, 1, None, {"released": count}, False
            )
        return count

    def __init__(self, store: HeadcountStore, clock, journal):
        self.hc, self.clock, self.journal = store, clock, journal

    def headcount(self, dept):
        return self.hc.get(dept, self.clock.now().year)

    def headcount_list(self, ctx, year):
        if not {"hrbp", "headcount_owner"}.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "仅编制负责人或 HRBP 可以维护编制", 403)
        today = self.clock.now().date()
        return {
            "departments": list(ctx.principal.departments),
            "items": [
                self._hc_dto(row, today) for row in self.hc.list(ctx.principal.departments, year)
            ],
        }

    def _hc_dto(self, row, today):
        return row | {
            "effective_from": row["effective_from"].isoformat(),
            "updated_on": row["updated_on"].isoformat(),
            "stale": (today - row["updated_on"]).days > 30,
        }

    def save_headcount(self, ctx, dept, command):
        if not {"hrbp", "headcount_owner"}.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "仅编制负责人或 HRBP 可以维护编制", 403)
        if dept not in ctx.principal.departments:
            raise DomainError("OUT_OF_SCOPE", "部门不在你的维护范围内", 403)
        self.policy(dept)
        today = self.clock.now().date()
        before = self.hc.get(dept, command.year)
        if command.year < today.year:
            raise DomainError("HC_PERIOD_CLOSED", "不能修改已结束年度的编制")
        if before and before["effective_from"] <= today and command.effective_from > today:
            raise DomainError("HC_EFFECTIVE_DATE", "已生效的编制不能改为未来生效；可冻结当前编制")
        row = self.hc.save(dept, command, today)
        after = self._hc_dto(row, today)
        self.journal.record(
            ctx,
            "org.headcount_updated",
            f"HC:{command.year}:{sha256(dept.encode()).hexdigest()[:24]}",
            row["version"],
            self._hc_dto(before, today) if before else None,
            after,
            False,
        )
        return after

    def reserve_headcount(self, ctx, dept, req_id, count):
        today = self.clock.now().date()
        if not self.hc.reserve(dept, req_id, count, today):
            return False
        # Counts only: no salary or personal data in the audit log.
        self.journal.record(
            ctx,
            "org.headcount_reserved",
            req_id,
            1,
            None,
            {"dept": dept, "year": today.year, "count": count},
            False,
        )
        return True
