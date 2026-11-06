import re
from datetime import datetime, timedelta

from app.kernel.types import DomainError, new_id
from app.modules.candidate.parser import PROTECTED, parse_resume, safe_text

HR = {"recruiter", "recruiting_lead", "hrbp"}


class CandidateFacade:
    def __init__(self, store, org, clock, journal):
        self.store, self.org, self.clock, self.journal = store, org, clock, journal
        self.applications = None  # Public port wired by the composition root.
        self.conversations = None

    def lock(self, ctx):
        self.org.lock_configuration()
        user = self.org.get_user(ctx.principal.user_id)
        if user.permission_version != ctx.principal.permission_version:
            raise DomainError("PERMISSION_CHANGED", "权限已更新，请刷新", 409)

    def hr(self, ctx):
        return bool(HR.intersection(ctx.principal.roles)) and bool(ctx.principal.departments)

    def require_hr(self, ctx):
        if not self.hr(ctx):
            raise DomainError("FORBIDDEN", "仅招聘 HR 可执行此操作", 403)

    def canonical(self, cid):
        c = self.store.get(cid)
        while c and c.get("merged_into"):
            c = self.store.get(c["merged_into"])
        return c

    def family(self, cid):
        return [
            c["id"]
            for c in self.store.all()
            if (root := self.canonical(c["id"])) and root["id"] == cid
        ]

    def _get(self, ctx, cid):
        c = self.canonical(cid)
        if c:
            apps = self.applications.for_candidates(self.family(c["id"]))
            allowed = (not apps and self.hr(ctx)) or any(
                self.applications.visible(ctx, a) for a in apps
            )
            if allowed:
                return c
        raise DomainError("NOT_FOUND", "候选人不存在或不在可见范围内", 404)

    def authorize(self, ctx, cid=None):
        self.lock(ctx)
        self.require_hr(ctx)
        return self._get(ctx, cid) if cid else None

    def safe_profile(self, profile):
        return {
            key: safe_text(value) if isinstance(value, str) else value
            for key, value in profile.items()
        }

    def create(self, ctx, command):
        self.authorize(ctx)
        profile = self.safe_profile(command.profile.model_dump())
        if not profile["name"]:
            raise DomainError("PROFILE_INVALID", "姓名不能为空或包含受保护属性")
        matches = self.store.matches(profile)
        roots = {self.canonical(c["id"])["id"] for c in matches}
        if len(roots) > 1:
            raise DomainError(
                "IDENTITY_CONFLICT", "手机和邮箱分别命中不同档案，请核对后人工合并", 409
            )
        if roots:
            c = self._get(ctx, next(iter(roots)))
            self.store.register_identity(c["id"], profile)
            # Never overwrite confirmed fields merely because another file was uploaded.
            return {"id": c["id"], "deduplicated": True}
        c = {
            "id": new_id("CAN"),
            "version": 1,
            "profile": profile,
            "source": command.source,
            "consent": "none",
            "consents": [],
            "do_not_contact": False,
            "tags": [],
            "key_candidate": False,
            "created_at": self.clock.now().isoformat(),
            "retention_until": (self.clock.now() + timedelta(days=1095)).date().isoformat(),
            "merged_into": None,
            "merges": [],
            "history": [],
        }
        self.store.save(c)
        self.log(ctx, c, "created")
        return {"id": c["id"], "deduplicated": False}

    def ingest(self, ctx, filename, data, cid=None):
        from app.modules.candidate.contracts import CreateCandidate, Profile

        self.authorize(ctx, cid)
        parsed = parse_resume(filename, data)
        if cid:
            c = self._get(ctx, cid)
            roots = {self.canonical(m["id"])["id"] for m in self.store.matches(parsed["profile"])}
            if roots - {c["id"]}:
                raise DomainError(
                    "IDENTITY_CONFLICT", "简历联系方式属于其他候选人，请先核对身份", 409
                )
            result = {"id": c["id"], "deduplicated": True}
        else:
            result = self.create(ctx, CreateCandidate(profile=Profile(**parsed["profile"])))
        c = self._get(ctx, result["id"])
        self.store.register_identity(c["id"], parsed["profile"])
        rid = new_id("RES")
        record = {
            "id": rid,
            "filename": filename.replace("\\", "/").split("/")[-1][:200],
            "at": self.clock.now().isoformat(),
            **parsed,
        }
        self.store.save_resume(rid, c["id"], record, data)
        self.journal.record(ctx, "resume.received", rid, 1, None, {"status": parsed["status"]})
        self.touch(ctx, c, "resume_added")
        return {**result, "resume_id": rid}

    def log(self, ctx, c, action):
        self.journal.record(
            ctx, "candidate." + action, c["id"], c["version"], None, {"version": c["version"]}
        )

    def touch(self, ctx, c, action):
        old = c["version"]
        c["version"] += 1
        c["history"].append(
            {"action": action, "actor": ctx.principal.user_id, "at": self.clock.now().isoformat()}
        )
        self.store.save(c, old)
        self.log(ctx, c, action)

    def get(self, ctx, cid):
        c = self._get(ctx, cid)
        profile = self.mask_tree(c["profile"])
        profile["phone"] = self.mask(profile["phone"])
        profile["email"] = self.mask(profile["email"])
        is_hr = self.hr(ctx)
        if not is_hr:
            profile.pop("expected_salary", None)
        ids = self.family(c["id"])
        apps = self.applications.for_candidates(ids)
        similar = []
        p = c["profile"]
        if is_hr and p["school"] and p["graduation_year"]:
            for other in self.store.all():
                if other["id"] in ids or other.get("merged_into"):
                    continue
                if all(other["profile"][k] == p[k] for k in ("name", "school", "graduation_year")):
                    try:
                        self._get(ctx, other["id"])
                        similar.append(
                            {
                                "id": other["id"],
                                "name": other["profile"]["name"],
                                "version": other["version"],
                            }
                        )
                    except DomainError:
                        pass
        return {
            "id": c["id"],
            "version": c["version"],
            "profile": profile,
            "source": c["source"],
            "consent": c["consent"],
            "do_not_contact": c["do_not_contact"],
            "tags": c["tags"],
            "key_candidate": c["key_candidate"],
            "can_edit": is_hr,
            "created_at": c["created_at"],
            "retention_until": c["retention_until"],
            "resumes": self.mask_tree(self.store.resumes(ids)) if is_hr else [],
            "similar": similar,
            "merges": c["merges"] if is_hr else [],
            "history": c["history"] if is_hr else [],
            "applications": [
                self.applications.dto(ctx, a, brief=not self.applications.visible(ctx, a))
                for a in apps
            ],
        }

    @staticmethod
    def mask(value):
        if not value:
            return ""
        return (
            value[:1] + "***@" + value.split("@")[-1]
            if "@" in value
            else value[:3] + "****" + value[-4:]
        )

    def mask_tree(self, value):
        if isinstance(value, dict):
            return {
                k: self.mask(v)
                if k in {"phone", "email"} and isinstance(v, str)
                else self.mask_tree(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.mask_tree(v) for v in value]
        if isinstance(value, str):
            value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", lambda m: self.mask(m[0]), value)
            return re.sub(
                r"(?<![0-9A-Za-z])\+?\d[\d ()-]{5,23}\d(?![0-9A-Za-z])",
                lambda m: (
                    self.mask(m[0])
                    if len(re.sub(r"\D", "", m[0])) in {10, 11} or m[0].startswith("+")
                    else m[0]
                ),
                value,
            )
        return value

    def search(self, ctx, page, size, query="", state="", city="", source=""):
        rows = []
        for c in self.store.all():
            if c.get("merged_into"):
                continue
            try:
                self._get(ctx, c["id"])
            except DomainError:
                continue
            # Business search never acts as a full contact-number oracle.
            keys = ("name", "company", "skills") + (("phone", "email") if self.hr(ctx) else ())
            if (
                query
                and query.casefold()
                not in " ".join([*(str(c["profile"][k]) for k in keys), *c["tags"]]).casefold()
            ):
                continue
            if city and city not in c["profile"]["city"] or source and source != c["source"]:
                continue
            active = any(
                not a["outcome"] for a in self.applications.for_candidates(self.family(c["id"]))
            )
            if (
                state == "active"
                and not active
                or state == "idle"
                and active
                or state == "do_not_contact"
                and not c["do_not_contact"]
            ):
                continue
            rows.append(c)
        rows.sort(key=lambda c: (c["created_at"], c["id"]), reverse=True)
        return {
            "items": [
                {
                    k: v
                    for k, v in self.get(ctx, c["id"]).items()
                    if k not in {"resumes", "history", "merges", "similar"}
                }
                for c in rows[(page - 1) * size : page * size]
            ],
            "total": len(rows),
            "page": page,
            "size": size,
        }

    def contacts(self, ctx, cid):
        c = self.authorize(ctx, cid)
        self.journal.record(
            ctx, "candidate.view_contact", c["id"], c["version"], None, {}, event=False
        )
        return {"phone": c["profile"]["phone"], "email": c["profile"]["email"]}

    def download(self, ctx, cid, rid):
        c = self.authorize(ctx, cid)
        record = next((r for r in self.store.resumes(self.family(c["id"])) if r["id"] == rid), None)
        if not record:
            raise DomainError("NOT_FOUND", "简历不存在", 404)
        self.journal.record(
            ctx,
            "candidate.download_resume",
            c["id"],
            c["version"],
            None,
            {"resume_id": rid},
            event=False,
        )
        return record["filename"], self.store.file(rid)

    def command(self, ctx, cid, command):
        c = self.authorize(ctx, cid)
        if c["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "候选人已更新，请刷新", 409)
        action = command.action
        if action == "edit":
            if not command.profile:
                raise DomainError("PROFILE_REQUIRED", "请填写候选人资料")
            profile = self.safe_profile(command.profile.model_dump())
            if not profile["name"]:
                raise DomainError("PROFILE_INVALID", "姓名不能为空或包含受保护属性")
            if self.store.matches(profile, [c["id"]]):
                raise DomainError("IDENTITY_CONFLICT", "联系方式已属于其他档案，请核对或合并", 409)
            c["profile"] = profile
            if command.resume_id:
                resume = next(
                    (
                        r
                        for r in self.store.resumes(self.family(c["id"]))
                        if r["id"] == command.resume_id
                    ),
                    None,
                )
                if not resume:
                    raise DomainError("NOT_FOUND", "简历不属于当前候选人", 404)
                resume.update(
                    profile=profile,
                    status="ok"
                    if profile["name"] != "待补全" and (profile["phone"] or profile["email"])
                    else "partial",
                    reviewed_by=ctx.principal.user_id,
                    reviewed_at=self.clock.now().isoformat(),
                    warning="已由 HR 核对修正；原件保持不变",
                )
                self.store.save_resume_metadata(resume)
        elif action == "consent":
            if not command.evidence or not command.reason:
                raise DomainError("CONSENT_EVIDENCE_REQUIRED", "请记录候选人授权或撤回的证据及说明")
            c["consent"] = "granted" if command.granted else "revoked"
            c["consents"].append(
                {
                    "granted": command.granted,
                    "scope": "recruitment_and_ai_evaluation",
                    "policy_version": command.policy_version,
                    "evidence": command.evidence,
                    "reason": command.reason,
                    "actor": ctx.principal.user_id,
                    "at": self.clock.now().isoformat(),
                }
            )
        elif action == "do_not_contact":
            if not command.reason:
                raise DomainError("REASON_REQUIRED", "请填写不再联系的原因")
            c["do_not_contact"] = True
        elif action == "tags":
            if any(not t.strip() or len(t) > 40 or PROTECTED.search(t) for t in command.tags):
                raise DomainError("TAG_INVALID", "标签不能为空、超过 40 字或涉及受保护属性")
            c["tags"] = list(dict.fromkeys(t.strip() for t in command.tags))
        elif action == "key":
            c["key_candidate"] = command.key_candidate
        elif action == "merge":
            if not command.reason:
                raise DomainError("REASON_REQUIRED", "合并须填写原因")
            other = self._get(ctx, command.target_id)
            if c["id"] == other["id"] or other["version"] != command.target_version:
                raise DomainError("VERSION_CONFLICT", "目标档案已更新或已合并，请刷新", 409)
            if other["merges"]:
                raise DomainError("MERGE_NESTED", "请先撤销目标档案已有合并，再合并到主档案", 409)
            self.conversations.invalidate(
                ctx, self.family(c["id"]) + self.family(other["id"]), revoke=True
            )
            self.applications.rekey(self.family(other["id"]), c["id"])
            other["merged_into"] = c["id"]
            self.touch(ctx, other, "merged_into")
            c["merges"].append(
                {"id": other["id"], "at": self.clock.now().isoformat(), "reason": command.reason}
            )
            # Preserve the stricter privacy choice across both identities.
            c["do_not_contact"] = c["do_not_contact"] or other["do_not_contact"]
            states = {c["consent"], other["consent"]}
            c["consent"] = (
                "revoked" if "revoked" in states else "none" if "none" in states else "granted"
            )
        elif action == "unmerge":
            merge = next((m for m in c["merges"] if m["id"] == command.target_id), None)
            if (
                not merge
                or datetime.fromisoformat(merge["at"]) + timedelta(days=7) < self.clock.now()
            ):
                raise DomainError("MERGE_EXPIRED", "只能撤销 7 天内的合并", 409)
            other = self.store.get(command.target_id)
            self.conversations.invalidate(ctx, self.family(c["id"]), revoke=True)
            other["merged_into"] = None
            other["do_not_contact"] = other["do_not_contact"] or c["do_not_contact"]
            if c["consent"] == "revoked":
                other["consent"] = "revoked"
            self.applications.rekey([other["id"]], other["id"])
            self.touch(ctx, other, "unmerged")
            c["merges"].remove(merge)
        elif action == "erase":
            if not command.reason:
                raise DomainError("REASON_REQUIRED", "请记录候选人删除请求的依据")
            ids = self.family(c["id"])
            self.conversations.invalidate(ctx, ids, erase=True)
            self.applications.erase(ids)
            self.store.erase(ids)
            self.log(ctx, c, "deleted")
            return {"deleted": True}
        self.touch(ctx, c, action)
        if action == "do_not_contact" or (action == "consent" and not command.granted):
            self.conversations.invalidate(ctx, self.family(c["id"]))
        return {"id": c["id"]}

    def resolve_request(self, ctx, cid, rid, resolution):
        c = self.authorize(ctx, cid)
        item = next((r for r in c.get("self_requests", []) if r["id"] == rid), None)
        if not item or item["status"] != "pending":
            raise DomainError("REQUEST_CLOSED", "请求不存在或已处理", 409)
        if item["kind"] == "deletion_request":
            raise DomainError("ERASURE_REQUIRED", "删除请求请使用档案删除操作完成", 409)
        if not resolution:
            raise DomainError("REASON_REQUIRED", "请记录实际处理结果")
        item.update(
            status="resolved", resolution=resolution, resolved_at=self.clock.now().isoformat()
        )
        self.touch(ctx, c, "request_resolved")

    def self_service(self, ctx, cid, action, content):
        """Called only after the portal capability has been verified under the transaction lock."""
        c = self.canonical(cid)
        if not c or ctx.principal.user_id != "candidate:" + cid:
            raise DomainError("FORBIDDEN", "身份验证失败", 403)
        if action in {"consent", "revoke"}:
            c["consent"] = "granted" if action == "consent" else "revoked"
            c["consents"].append(
                {
                    "granted": action == "consent",
                    "scope": "recruitment_and_ai_evaluation",
                    "policy_version": "2026-11",
                    "evidence": ctx.trace_id,
                    "actor": ctx.principal.user_id,
                    "at": self.clock.now().isoformat(),
                }
            )
        elif action == "do_not_contact":
            c["do_not_contact"] = True
        elif action in {"correction_request", "deletion_request"}:
            if not content:
                raise DomainError("CONTENT_REQUIRED", "请填写请求说明")
            c.setdefault("self_requests", []).append(
                {
                    "id": new_id("RIGHT"),
                    "kind": action,
                    "content": content,
                    "status": "pending",
                    "at": self.clock.now().isoformat(),
                    "due_at": (self.clock.now() + timedelta(days=15)).isoformat(),
                }
            )
        else:
            raise DomainError("INVALID_ACTION", "不支持的操作")
        self.touch(ctx, c, action)

    def contactable(self, cid):
        c = self.canonical(cid)
        return bool(c and not c["do_not_contact"] and c["consent"] != "revoked")

    def evaluation_input(self, cid):
        c = self.canonical(cid)
        if not c or c["consent"] != "granted":
            raise DomainError("CONSENT_REQUIRED", "候选人尚未授权 AI 评估", 409)
        return {
            k: v
            for k, v in self.safe_profile(c["profile"]).items()
            if k not in {"phone", "email", "name", "expected_salary"}
        }
