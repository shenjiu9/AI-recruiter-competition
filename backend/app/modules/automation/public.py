import json
from copy import deepcopy
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.kernel.types import DomainError

NODES = {
    "draft": ("需求起草", 2, 1, 3),
    "publish": ("JD 发布", 2, 1, 3),
    "attach": ("人才库挂人", 2, 1, 3),
    "outreach": ("首次触达", 3, 1, 3),
    "conversation": ("沟通答疑", 3, 2, 3),
    "advance": ("评估通过", 2, 1, 3),
    "reject": ("淘汰", 2, 1, 2),
    "schedule": ("约面与改期", 3, 2, 3),
    "ai_interview": ("AI 初面邀请", 3, 2, 3),
    "ai_advance": ("AI 初面推进", 2, 1, 3),
    "reminder": ("催办催评", 3, 1, 3),
    "hire": ("录用建议", 1, 1, 1),
}


class AutomationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    scope: Literal["global", "series", "position"] = "global"
    target: str = Field(default="", max_length=100)
    dept: str = Field(default="", max_length=100)
    levels: dict[str, StrictInt] = Field(default_factory=dict, max_length=20)
    mode: Literal["normal", "shadow", "manual"] | None = None
    components: dict[str, bool] | None = None
    low_threshold: float | None = Field(default=None, ge=0, le=1)
    high_threshold: float | None = Field(default=None, ge=0, le=1)
    approval_nodes: list[Literal["director", "hrbp"]] | None = Field(default=None, max_length=2)
    hrd_grade: int | None = Field(default=None, ge=1, le=20)
    restore_version: int | None = Field(default=None, ge=1)


class AutomationFacade:
    @staticmethod
    def series_key(dept, series):
        return (
            "series:"
            + sha256(json.dumps([dept, series], ensure_ascii=False).encode()).hexdigest()[:48]
        )

    def __init__(self, store, org, candidates, positions, clock, journal):
        self.store, self.org, self.candidates, self.positions, self.clock, self.journal = (
            store,
            org,
            candidates,
            positions,
            clock,
            journal,
        )

    def current(self, key="global"):
        return self.store.get(key) or {
            "id": key,
            "version": 1,
            "levels": {n: v[1] for n, v in NODES.items()} if key == "global" else {},
            "mode": "manual",
            "components": {f"A{i}": False for i in range(1, 8)},
            "low_threshold": 0.6,
            "high_threshold": 0.85,
            "approval_nodes": ["director", "hrbp"],
            "hrd_grade": 6,
            "history": [],
        }

    def key(self, ctx, scope, target, dept):
        self.candidates.lock(ctx)
        admin = "admin" in ctx.principal.roles
        if not admin and "recruiting_lead" not in ctx.principal.roles:
            raise DomainError("FORBIDDEN", "仅管理员或招聘负责人可维护策略", 403)
        if scope == "global":
            if not admin:
                raise DomainError("FORBIDDEN", "全局策略与录用审批规则仅管理员可维护", 403)
            return "global"
        if scope == "position":
            pos = self.positions.get(ctx, target)
            if not pos["canLead"]:
                raise DomainError("FORBIDDEN", "岗位策略须由范围内招聘负责人维护", 403)
            return "position:" + target
        self.org.policy(dept)
        if not target.strip() or (not admin and dept not in ctx.principal.departments):
            raise DomainError("FORBIDDEN", "请选择授权部门内的序列", 403)
        return self.series_key(dept, target)

    def get(self, ctx, scope="global", target="", dept=""):
        key = self.key(ctx, scope, target, dept)
        value = self.current(key)
        return {
            **value,
            "nodes": [{"key": n, "name": v[0], "min": v[2], "max": v[3]} for n, v in NODES.items()],
            "engine_enabled": False,
        }

    def configure(self, ctx, body):
        key = self.key(ctx, body.scope, body.target, body.dept)
        value = self.current(key)
        if value["version"] != body.expected_version:
            raise DomainError("VERSION_CONFLICT", "策略已变化，请刷新", 409)
        old = deepcopy(value)
        if body.restore_version:
            source = next(
                (h["snapshot"] for h in value["history"] if h["version"] == body.restore_version),
                None,
            )
            if source is None:
                raise DomainError("NOT_FOUND", "历史版本不存在", 404)
            value.update(deepcopy(source))
        else:
            for node, level in body.levels.items():
                if (
                    node not in NODES
                    or type(level) is not int
                    or not NODES[node][2] <= level <= NODES[node][3]
                ):
                    raise DomainError("AUTOMATION_LIMIT", "配置不能突破淘汰 L2、录用 L1 等硬上限")
            value["levels"] = body.levels if key != "global" else {**value["levels"], **body.levels}
            for field in (
                "mode",
                "components",
                "low_threshold",
                "high_threshold",
                "approval_nodes",
                "hrd_grade",
            ):
                update = getattr(body, field)
                if update is not None:
                    if key != "global":
                        raise DomainError("GLOBAL_ONLY", "模式、组件与审批规则只能在全局维护")
                    value[field] = update
        if not value["low_threshold"] < value["high_threshold"]:
            raise DomainError("THRESHOLD_INVALID", "低把握阈值须小于高把握阈值")
        if set(value["components"]) != {f"A{i}" for i in range(1, 8)} or len(
            set(value["approval_nodes"])
        ) != len(value["approval_nodes"]):
            raise DomainError("CONFIG_INVALID", "组件须完整，审批节点不能重复")
        value["history"] = old["history"] + [
            {
                "version": old["version"],
                "snapshot": {k: v for k, v in old.items() if k not in {"id", "version", "history"}},
                "actor": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
            }
        ]
        value["version"] = old["version"] + 1
        self.store.save(value, old["version"] if self.store.get(key) else None)
        self.journal.record(
            ctx, "automation.configured", key, value["version"], None, {"mode": value["mode"]}
        )
        return {"id": key}

    def effective(self, node, pos, confidence=1, sensitive=False):
        if node not in NODES:
            raise DomainError("NODE_UNKNOWN", "未知自动化环节")
        global_config = self.current()
        level = global_config["levels"][node]
        for key in (self.series_key(pos["dept"], pos["series"]), "position:" + pos["id"]):
            level = self.current(key)["levels"].get(node, level)
        cap = NODES[node][3]
        if node == "publish" and pos.get("jdApprovalRequired"):
            cap = min(cap, 2)
        if confidence < global_config["low_threshold"] or sensitive or pos.get("confidential"):
            cap = min(cap, 2)
        return 1 if global_config["mode"] in {"manual", "shadow"} else min(level, cap)
