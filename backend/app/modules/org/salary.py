import re
from decimal import Decimal
from typing import Protocol

from app.kernel.types import DomainError


class SalaryStore(Protocol):
    def find(self, series, grade, city, today): ...
    def list(self, today, page, size): ...
    def get(self, band_id, today): ...
    def history(self, band_id): ...
    def save(self, command, today): ...


def grades(level):
    value = level.strip().upper()
    match = re.fullmatch(r"([A-Z]+)(\d{1,2})\s*[-–~至]\s*([A-Z]+)?(\d{1,2})", value)
    if match:
        prefix, low, other, high = match.groups()
        start, end = int(low), int(high)
        if (other and other != prefix) or not 0 <= end - start < 20:
            return []
        return [f"{prefix}{i}" for i in range(start, end + 1)]
    return [value] if value and not re.search(r"[\s–~至,-]", value) else []


class SalaryService:
    def __init__(self, store: SalaryStore, clock, journal):
        self.store, self.clock, self.journal = store, clock, journal

    def _authorize(self, ctx):
        if not {"recruiting_lead", "compensation_owner"}.intersection(ctx.principal.roles):
            raise DomainError("FORBIDDEN", "仅招聘负责人或薪酬负责人可以维护职级薪资表", 403)

    def list(self, ctx, page, size):
        self._authorize(ctx)
        return self.store.list(self.clock.now().date(), page, size)

    def history(self, ctx, band_id):
        self._authorize(ctx)
        if not self.store.get(band_id, self.clock.now().date()):
            raise DomainError("NOT_FOUND", "薪资配置不存在", 404)
        return self.store.history(band_id)

    def save(self, ctx, command):
        self._authorize(ctx)
        today = self.clock.now().date()
        # Only today's or future rules can be published; historical decisions remain reproducible.
        if command.effective_from < today:
            raise DomainError("SALARY_EFFECTIVE_DATE", "新版本生效日期不能早于今天")
        row = self.store.save(command, today)
        self.journal.record(
            ctx,
            "org.salary_updated",
            row["id"],
            row["version"],
            {"version": command.expected_version} if command.expected_version else None,
            {"version": row["version"], "effective_from": command.effective_from.isoformat()},
            False,
        )
        return row

    def check(self, series, level, city, quote):
        today = self.clock.now().date()
        levels = grades(level)
        rows = [self.store.find(series, level, city, today) for level in levels]
        missing = [
            level for level, row in zip(levels, rows, strict=True) if not row or not row["active"]
        ]
        checks, refs = [], []
        if not levels or missing:
            return {
                "over": False,
                "refs": [],
                "checks": [
                    {
                        "key": "salary_config",
                        "label": "职级薪资配置",
                        "status": "block",
                        "detail": f"职级薪资表缺少已生效的 {series} / {'、'.join(missing) or level} / {city}，请联系维护人补全"
                        if levels
                        else "职级格式无效；填写单个职级或同序列连续范围，例如 P3–P5（最多 20 级）",
                    }
                ],
            }
        for row in rows:
            refs.append({"band_id": row["id"], "version": row["active"]["version"]})
        checks.append(
            {
                "key": "salary_config",
                "label": "职级薪资配置",
                "status": "pass",
                "detail": "对应职级的生效配置均已匹配",
            }
        )
        if any(row["stale"] for row in rows):
            checks.append(
                {
                    "key": "salary_stale",
                    "label": "薪资更新时间",
                    "status": "warn",
                    "detail": "生效薪资数据超过 30 天未维护，可能过期",
                }
            )
        over = False
        if quote:

            def dec(value):
                return Decimal(str(value))

            lower = min(dec(row["active"]["lower"]) for row in rows)
            upper = max(dec(row["active"]["upper"]) for row in rows)
            annual_lower = min(
                dec(row["active"]["lower"]) * row["active"]["months"] for row in rows
            )
            annual_upper = max(
                dec(row["active"]["upper"]) * row["active"]["months"] for row in rows
            )
            low, high, months = quote
            over = not (
                lower <= dec(low) <= dec(high) <= upper
                and annual_lower <= dec(low) * months <= dec(high) * months <= annual_upper
            )
            checks.append(
                {
                    "key": "salary_band",
                    "label": "薪资带宽",
                    "status": "warn" if over else "pass",
                    "detail": f"生效月薪 {lower:g}–{upper:g}K，年薪 {annual_lower:g}–{annual_upper:g}K；"
                    + ("超出范围，将独立加签 HRD" if over else "在配置范围内"),
                }
            )
        return {"over": over, "refs": refs, "checks": checks}
