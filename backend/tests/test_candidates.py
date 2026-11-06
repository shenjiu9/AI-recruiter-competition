import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from test_positions import POS, act, opened

from app.kernel.types import Ctx, DomainError, Principal
from app.modules.application.adapters.repository import ApplicationRecord
from app.modules.candidate.adapters.repository import CandidateRecord, IdentityRecord, ResumeRecord
from app.platform.records import AuditRecord, EventRecord, RequestRecord

ROOT = "/api/v1/hr/candidates"
APPS = "/api/v1/hr/applications"


def ok(r):
    assert r.status_code == 200, r.text
    return r.json()


def create(client, login, **profile):
    return ok(
        client.post(
            ROOT,
            headers=login(key=uuid4().hex),
            json={"profile": {"name": "测试候选人", **profile}},
        )
    )["candidate"]


def command(client, login, c, action, actor="hr", **body):
    return client.post(
        f"{ROOT}/{c['id']}/actions",
        headers=login(actor, uuid4().hex),
        json={"expected_version": c["version"], "action": action, **body},
    )


def attach(client, login, c, p, **body):
    return client.post(
        APPS,
        headers=login(key=uuid4().hex),
        json={"candidate_id": c["id"], "position_id": p["id"], **body},
    )


def app_action(client, login, a, action, **body):
    return client.post(
        f"{APPS}/{a['id']}/actions",
        headers=login(key=uuid4().hex),
        json={"action": action, "expected_version": a["version"], **body},
    )


def docx(text):
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
            + "</w:body></w:document>",
        )
    return stream.getvalue()


def upload(client, login, data, filename="简历.docx", cid=None, key=None):
    return client.post(
        "/api/v1/hr/candidate-resumes",
        params={"filename": filename, **({"candidate_id": cid} if cid else {})},
        headers=login(key=key or uuid4().hex),
        content=data,
    )


def test_resume_parse_dedupe_encryption_masking_and_audited_download(client, login, container):
    data = docx(
        "姓名：张小测\n手机：13800138000\n邮箱：test@example.com\n技能：Python\n年龄：30\n性别：女\n身份证：110101199001011234"
    )
    result = ok(upload(client, login, data, key="upload-one"))
    c = result["candidate"]
    assert c["profile"]["name"] == "张小测" and c["profile"]["phone"] == "138****8000"
    assert c["resumes"][0]["status"] == "ok" and c["consent"] == "none"
    assert "13800138000" not in json.dumps(c) and "test@example.com" not in json.dumps(c)
    assert "身份证" not in json.dumps(c, ensure_ascii=False)
    assert ok(upload(client, login, data, key="upload-one"))["resume_id"] == result["resume_id"]
    second = ok(upload(client, login, data))
    assert second["id"] == c["id"] and second["deduplicated"]
    assert len(second["candidate"]["resumes"]) == 2
    assert ok(client.post(f"{ROOT}/{c['id']}/contacts", headers=login()))["phone"] == "13800138000"
    download = client.get(f"{ROOT}/{c['id']}/resumes/{result['resume_id']}/file", headers=login())
    assert download.content == data and download.headers["x-content-type-options"] == "nosniff"
    with container.db.sessions() as db:
        row = db.get(CandidateRecord, c["id"])
        assert b"13800138000" not in row.data and row.phone_hash != "13800138000"
        assert data not in db.get(ResumeRecord, result["resume_id"]).blob
        audits = list(db.scalars(select(AuditRecord)))
        assert {"candidate.view_contact", "candidate.download_resume"} <= {a.action for a in audits}
        assert "13800138000" not in str([(a.before, a.after) for a in audits])
        assert "13800138000" not in str(list(db.scalars(select(EventRecord.payload))))
        for row in db.scalars(select(RequestRecord)):
            assert "13800138000" not in str(container.crypto.decrypt(row.response, row.key))


def test_identity_normalization_conflict_and_concurrent_dedupe(client, login):
    c = create(client, login, phone="+86 138-0013-8000", email="First@Example.com")
    assert create(client, login, phone="13800138000")["id"] == c["id"]
    other = create(client, login, phone="13900139000", email="second@example.com")
    conflict = client.post(
        ROOT,
        headers=login(key="identity-conflict"),
        json={
            "profile": {"name": "conflict", "phone": "13800138000", "email": "second@example.com"}
        },
    )
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "IDENTITY_CONFLICT"
    h1, h2 = login(key="concurrent1"), login(key="concurrent2")
    with ThreadPoolExecutor(2) as executor:
        results = list(
            executor.map(
                lambda h: client.post(
                    ROOT, headers=h, json={"profile": {"name": "parallel", "phone": "13700137000"}}
                ),
                [h1, h2],
            )
        )
    assert len({ok(r)["id"] for r in results}) == 1
    assert (
        command(
            client, login, other, "edit", profile={"name": "conflict", "phone": "13800138000"}
        ).status_code
        == 409
    )


def test_new_contacts_on_deduplicated_resumes_remain_identity_aliases(client, login):
    first = ok(
        upload(client, login, docx("姓名：同一人\n手机：13800138000\n邮箱：same@example.com"))
    )
    second = ok(
        upload(client, login, docx("姓名：同一人\n手机：13900139000\n邮箱：same@example.com"))
    )
    third = ok(upload(client, login, docx("姓名：同一人\n手机：13900139000")))
    assert first["id"] == second["id"] == third["id"]
    assert len(third["candidate"]["resumes"]) == 3


def test_candidate_permissions_and_cross_position_summary(client, login, fields, container):
    c = create(
        client, login, phone="13800138000", email="private@example.com", expected_salary="30K"
    )
    assert client.get(f"{ROOT}/{c['id']}", headers=login("manager")).status_code == 404
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, c, p))
    view = ok(client.get(f"{ROOT}/{c['id']}", headers=login("manager")))
    assert view["profile"]["phone"] == "138****8000" and "expected_salary" not in view["profile"]
    assert view["resumes"] == [] and not view["can_edit"]
    assert client.post(f"{ROOT}/{c['id']}/contacts", headers=login("manager")).status_code == 403
    assert command(client, login, c, "tags", actor="manager", tags=["Python"]).status_code == 403
    assert client.get(f"{ROOT}/{c['id']}", headers=login("outsider")).status_code == 404
    assert (
        ok(client.get(ROOT, headers=login("manager"), params={"query": "13800138000"}))["total"]
        == 0
    )
    with container.scope() as s:
        app = s.application.store.get(a["id"])
        app.update(
            id="APP-restricted",
            position_id="POS-hidden",
            position_name="另一个岗位",
            evidence="private evidence",
            canonical_id=c["id"],
        )
        s.application.store.save(app)
    view = ok(client.get(f"{ROOT}/{c['id']}", headers=login("manager")))
    restricted = next(a for a in view["applications"] if a["restricted"])
    assert "evidence" not in restricted and "stage" not in restricted and "reason" not in restricted


def test_consent_protected_fields_and_opt_out(client, login, container, fields):
    assert (
        client.post(ROOT, headers=login(), json={"profile": {"name": "X", "age": 30}}).status_code
        == 400
    )
    c = create(client, login, skills="Python\n性别：女", experience="项目开发\n年龄：28")
    assert c["profile"]["skills"] == "Python"
    assert command(client, login, c, "tags", tags=["已婚已育"]).status_code == 422
    with container.scope() as s:
        with pytest.raises(DomainError, match="尚未授权"):
            s.candidate.evaluation_input(c["id"])
    assert command(client, login, c, "consent", granted=True).status_code == 422
    c = ok(
        command(
            client,
            login,
            c,
            "consent",
            granted=True,
            evidence="signed:document-123",
            reason="候选人签署招聘及 AI 评估授权",
        )
    )
    with container.scope() as s:
        value = s.candidate.evaluation_input(c["id"])
        assert "name" not in value and "phone" not in value and "年龄" not in str(value)
    c = ok(command(client, login, c, "do_not_contact", reason="候选人要求"))
    _, p = opened(client, login, fields, container)
    assert attach(client, login, c, p, source="candidate", evidence="submission").status_code == 409
    with container.scope() as s:
        assert not s.candidate.contactable(c["id"])
    c = ok(
        command(client, login, c, "consent", granted=False, evidence="message:123", reason="撤回")
    )
    with container.scope() as s:
        with pytest.raises(DomainError):
            s.candidate.evaluation_input(c["id"])


def test_redaction_preserves_names_dates_and_masks_embedded_contacts(client, login):
    c = create(
        client,
        login,
        name="编号-1793930597626",
        experience="联系138-0013-8000，邮箱someone@example.com",
    )
    assert c["profile"]["name"] == "编号-1793930597626"
    assert "138-0013-8000" not in c["profile"]["experience"]
    assert "someone@example.com" not in c["profile"]["experience"]
    assert "****" not in c["created_at"]


def test_merge_and_unmerge_never_reenable_revoked_consent(client, login, container):
    c, d = create(client, login), create(client, login)
    c = ok(
        command(
            client, login, c, "consent", granted=False, evidence="message:revoke", reason="撤回"
        )
    )
    c = ok(
        command(
            client,
            login,
            c,
            "merge",
            target_id=d["id"],
            target_version=d["version"],
            reason="本人确认",
        )
    )
    assert c["consent"] == "revoked"
    c = ok(command(client, login, c, "do_not_contact", reason="本人要求"))
    ok(command(client, login, c, "unmerge", target_id=d["id"]))
    with container.scope() as s:
        assert not s.candidate.contactable(d["id"])
        assert s.candidate.canonical(d["id"])["consent"] == "revoked"


def test_active_unique_stage_consent_and_position_counts(client, login, fields, container):
    c = create(client, login)
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, c, p))
    assert attach(client, login, c, p).status_code == 409
    assert ok(client.get(f"{POS}/{p['id']}", headers=login()))["candidateCounts"]["active"] == 1
    assert ok(client.get(f"{ROOT}/{c['id']}", headers=login()))["applications"][0]["id"] == a["id"]
    assert ok(client.get(f"{POS}/{p['id']}/applications", headers=login()))[0]["id"] == a["id"]
    assert app_action(client, login, a, "advance", target_stage="interview").status_code == 409
    a = ok(app_action(client, login, a, "advance"))
    assert a["stage"] == "talking"
    assert app_action(client, login, a, "advance").json()["error"]["code"] == "CONSENT_REQUIRED"
    c = ok(command(client, login, c, "consent", granted=True, reason="授权", evidence="message:1"))
    a = ok(app_action(client, login, a, "advance"))
    a = ok(app_action(client, login, a, "advance"))
    assert a["stage"] == "interview"
    assert app_action(client, login, a, "advance").json()["error"]["code"] == "WORKFLOW_REQUIRED"
    a = ok(app_action(client, login, a, "rollback", target_stage="talking", reason="补充沟通"))
    assert a["stage"] == "talking" and a["furthest_stage"] == "interview"


def test_concurrent_attach_and_close_leave_no_active_application(client, login, fields, container):
    c = create(client, login)
    _, p = opened(client, login, fields, container)
    body = {"candidate_id": c["id"], "position_id": p["id"]}
    keys = [login(key="attach-parallel-1"), login(key="attach-parallel-2")]
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda h: client.post(APPS, headers=h, json=body), keys))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len(ok(client.get(f"{POS}/{p['id']}/applications", headers=login()))) == 1
    second = create(client, login, name="另一个候选人")
    attach_headers, close_headers = login(key="racing-attach"), login(key="racing-close")
    with ThreadPoolExecutor(2) as executor:
        attaching = executor.submit(
            client.post,
            APPS,
            headers=attach_headers,
            json={"candidate_id": second["id"], "position_id": p["id"]},
        )
        closing = executor.submit(
            client.post,
            f"{POS}/{p['id']}/actions",
            headers=close_headers,
            json={"action": "close", "expected_version": p["version"], "reason": "需求取消"},
        )
        assert attaching.result().status_code in {200, 409}
        assert closing.result().status_code == 200
    assert all(
        a["outcome"] == "position_closed"
        for a in ok(client.get(f"{POS}/{p['id']}/applications", headers=login()))
    )


def test_cooldown_force_attach_voluntary_and_undo(client, login, fields, container):
    c = create(client, login)
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, c, p))
    assert app_action(client, login, a, "reject", reason="缺经验").status_code == 422
    a = ok(app_action(client, login, a, "reject", reason="缺经验", reason_code="experience"))
    assert attach(client, login, c, p).json()["error"]["code"] == "COOLDOWN"
    a = ok(app_action(client, login, a, "undo_reject", reason="重新核对"))
    assert a["outcome"] is None
    a = ok(app_action(client, login, a, "reject", reason="仍不符合", reason_code="experience"))
    b = ok(attach(client, login, c, p, reason="补充了新经验"))
    assert b["forced_attach_reason"] == "补充了新经验"
    assert app_action(client, login, a, "undo_reject", reason="重复恢复").status_code == 409
    ok(app_action(client, login, b, "withdraw", reason="时间不合适"))
    assert attach(client, login, c, p, source="candidate").status_code == 422
    assert (
        ok(attach(client, login, c, p, source="candidate", evidence="channel:submission-123"))[
            "source"
        ]
        == "candidate"
    )


def test_cooldown_same_series_level_and_expiry(client, login, fields, container):
    c = create(client, login)
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, c, p))
    ok(app_action(client, login, a, "reject", reason="技能", reason_code="skills"))
    _, other = opened(client, login, fields, container, key="another", title="同序列另一个岗位")
    assert attach(client, login, c, other).json()["error"]["code"] == "COOLDOWN"
    with container.scope() as s:
        app = s.application.store.get(a["id"])
        app["ended_at"] = (container.clock.now() - timedelta(days=183)).isoformat()
        s.application.store.save(app, app["version"])
    assert attach(client, login, c, other).status_code == 200


def test_pause_close_and_transfer_are_atomic(client, login, fields, container):
    c = create(client, login)
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, c, p))
    assert (
        app_action(
            client, login, a, "transfer", reason="转岗", target_position_id="missing"
        ).status_code
        == 404
    )
    assert ok(client.get(f"{POS}/{p['id']}/applications", headers=login()))[0]["outcome"] is None
    p = ok(act(client, login, p, "pause", reason="业务暂停", handling="freeze"))
    assert app_action(client, login, a, "advance").json()["error"]["code"] == "POSITION_FROZEN"
    other = create(client, login, name="other")
    assert attach(client, login, other, p).status_code == 409
    ok(act(client, login, p, "close", reason="需求取消"))
    a = ok(client.get(f"{POS}/{p['id']}/applications", headers=login()))[0]
    assert a["outcome"] == "position_closed"
    assert ok(client.get(f"{POS}/{p['id']}", headers=login()))["candidateCounts"]["active"] == 0


def test_merge_unmerge_restores_original_resumes_and_applications(client, login, fields, container):
    c = create(
        client, login, name="同名", school="某大学", graduation_year=2020, phone="13800138000"
    )
    d = ok(upload(client, login, docx("姓名：同名\n手机：13900139000")))["candidate"]
    d = ok(
        command(
            client,
            login,
            d,
            "edit",
            profile={
                "name": "同名",
                "school": "某大学",
                "graduation_year": 2020,
                "phone": "13900139000",
            },
        )
    )
    assert ok(client.get(f"{ROOT}/{c['id']}", headers=login()))["similar"][0]["id"] == d["id"]
    _, p = opened(client, login, fields, container)
    a = ok(attach(client, login, d, p))
    c = ok(
        command(
            client,
            login,
            c,
            "merge",
            target_id=d["id"],
            target_version=d["version"],
            reason="本人确认同一人",
        )
    )
    assert len(c["resumes"]) == 1 and c["applications"][0]["id"] == a["id"]
    assert ok(client.get(f"{ROOT}/{d['id']}", headers=login()))["id"] == c["id"]
    assert attach(client, login, c, p).status_code == 409
    c = ok(command(client, login, c, "unmerge", target_id=d["id"]))
    assert not c["applications"] and not c["resumes"]
    assert ok(client.get(f"{ROOT}/{d['id']}", headers=login()))["applications"][0]["id"] == a["id"]


def test_merge_active_conflict_and_seven_day_limit(client, login, fields, container):
    c, d = create(client, login), create(client, login)
    _, p = opened(client, login, fields, container)
    ok(attach(client, login, c, p))
    a = ok(attach(client, login, d, p))
    assert (
        command(
            client,
            login,
            c,
            "merge",
            target_id=d["id"],
            target_version=d["version"],
            reason="同一人",
        ).json()["error"]["code"]
        == "MERGE_ACTIVE_CONFLICT"
    )
    ok(app_action(client, login, a, "withdraw", reason="重复档案"))
    c = ok(
        command(
            client,
            login,
            c,
            "merge",
            target_id=d["id"],
            target_version=d["version"],
            reason="同一人",
        )
    )
    with container.scope() as s:
        row = s.candidate.store.get(c["id"])
        row["merges"][0]["at"] = (container.clock.now() - timedelta(days=8)).isoformat()
        s.candidate.store.save(row, row["version"])
    assert (
        command(client, login, c, "unmerge", target_id=d["id"]).json()["error"]["code"]
        == "MERGE_EXPIRED"
    )


def test_erase_removes_files_apps_identity_and_cached_pii(client, login, fields, container):
    data = docx("姓名：删除测试\n手机：13800138000")
    c = ok(upload(client, login, data, key="erase-upload"))["candidate"]
    _, p = opened(client, login, fields, container)
    ok(attach(client, login, c, p))
    assert ok(command(client, login, c, "erase", reason="候选人本人申请"))["deleted"]
    assert client.get(f"{ROOT}/{c['id']}", headers=login()).status_code == 404
    with container.db.sessions() as db:
        assert db.get(CandidateRecord, c["id"]) is None
        assert not list(db.scalars(select(ResumeRecord)))
        assert not list(db.scalars(select(ApplicationRecord)))
        assert not list(db.scalars(select(IdentityRecord)))
        for row in db.scalars(select(RequestRecord)):
            assert "13800138000" not in str(container.crypto.decrypt(row.response, row.key))
    assert upload(client, login, data, key="erase-upload").status_code == 404


@pytest.mark.parametrize(
    "filename,data", [("bad.exe", b"MZbad"), ("bad.pdf", b"<script>"), ("empty.docx", b"")]
)
def test_invalid_files_are_rejected(client, login, filename, data):
    assert upload(client, login, data, filename).status_code == 422


def test_failed_and_image_extraction_are_honest(client, login):
    broken = ok(upload(client, login, b"%PDF-broken", "broken.pdf"))["candidate"]
    assert broken["resumes"][0]["status"] == "failed"
    image = ok(upload(client, login, b"\x89PNG\r\n\x1a\nfixture", "scan.png"))["candidate"]
    assert image["resumes"][0]["status"] == "partial" and image["profile"]["name"] == "待补全"


def test_resume_correction_updates_review_metadata_without_changing_original(client, login):
    data = b"%PDF-broken"
    c = ok(upload(client, login, data, "broken.pdf"))["candidate"]
    rid = c["resumes"][0]["id"]
    assert (
        command(
            client,
            login,
            c,
            "edit",
            resume_id="missing",
            profile={"name": "修正", "phone": "13800138000"},
        ).status_code
        == 404
    )
    c = ok(
        command(
            client,
            login,
            c,
            "edit",
            resume_id=rid,
            profile={"name": "修正", "phone": "13800138000"},
        )
    )
    assert c["resumes"][0]["status"] == "ok" and c["resumes"][0]["reviewed_by"] == "hr"
    assert c["resumes"][0]["profile"]["phone"] == "138****8000"
    assert client.get(f"{ROOT}/{c['id']}/resumes/{rid}/file", headers=login()).content == data


def test_stale_versions_and_removed_permission_block_mutations(client, login, container):
    c = create(client, login)
    ok(command(client, login, c, "tags", tags=["客服"]))
    assert command(client, login, c, "key", key_candidate=True).status_code == 409
    with container.scope() as s:
        old = s.org.get_user("hr")
        ctx = Ctx(Principal(old.id, old.name, old.roles, old.departments), "trace")
        # A stale principal must not cross the write boundary.
        stale = SimpleNamespace(
            **{**ctx.principal.__dict__, "permission_version": old.permission_version - 1}
        )
        with pytest.raises(DomainError, match="权限已更新"):
            s.candidate.authorize(Ctx(stale, ctx.trace_id), c["id"])
