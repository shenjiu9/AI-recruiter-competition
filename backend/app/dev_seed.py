"""Explicit local-only directory fixture; never runs at API startup."""

from app.bootstrap import build_container
from app.modules.org.adapters.headcount import HeadcountRecord
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.modules.org.adapters.salary import SqlSalary
from app.modules.org.contracts import SalaryBandCommand
from app.platform.settings import Settings

DEPARTMENTS = ["客服中心", "销售部 / 华南大区", "经营分析部", "财务部"]
USERS = [
    ("hr", "林悦", ["recruiter", "recruiting_lead"], DEPARTMENTS),
    ("manager", "何美玲", ["hiring_manager"], ["客服中心"]),
    ("sales", "周振华", ["hiring_manager"], ["销售部 / 华南大区"]),
    ("analyst", "田野", ["hiring_manager"], ["经营分析部", "财务部"]),
    ("director", "部门负责人", ["hiring_manager"], DEPARTMENTS),
    ("hrbp", "人力伙伴", ["hrbp"], DEPARTMENTS),
    ("hrd", "编制负责人", ["hrbp"], DEPARTMENTS),
    ("salary_hrd", "薪酬审批负责人", ["hrd"], DEPARTMENTS),
    ("payroll", "薪酬维护负责人", ["compensation_owner"], DEPARTMENTS),
    ("outsider", "其他部门用户", ["recruiter"], ["其他部门"]),
]


def seed(container):
    if container.settings.environment != "development" or not container.settings.dev_auth_enabled:
        raise RuntimeError("Demo directory requires explicit development authentication")
    with container.db.sessions.begin() as session:
        for user_id, name, roles, departments in USERS:
            if session.get(UserRecord, user_id) is None:
                session.add(UserRecord(id=user_id, name=name, roles=roles, departments=departments))
        for dept, manager in zip(
            DEPARTMENTS, ["manager", "sales", "analyst", "analyst"], strict=True
        ):
            today = container.clock.now().date()
            if session.get(HeadcountRecord, (dept, today.year)) is None:
                session.add(
                    HeadcountRecord(
                        dept=dept,
                        year=today.year,
                        version=1,
                        planned=2,
                        used=0,
                        reserved=0,
                        frozen=False,
                        effective_from=today.replace(month=1, day=1),
                        updated_on=today,
                    )
                )
            if session.get(DepartmentRecord, dept) is None:
                session.add(
                    DepartmentRecord(
                        id=dept,
                        policy={
                            "available_hc": 2,
                            "manager_id": manager,
                            "director_id": "director",
                            "hrbp_id": "hrbp",
                            "hc_owner_id": "hrd",
                            "salary_max": 20,
                            "hrd_id": "salary_hrd",
                        },
                    )
                )
            else:
                record = session.get(DepartmentRecord, dept)
                if not record.policy.get("hrd_id"):
                    record.policy = {**record.policy, "hrd_id": "salary_hrd"}
        salary = SqlSalary(session, container.crypto)
        for series in ["客服", "财务", "销售", "经营分析"]:
            if not salary.find(series, "P3", "深圳", today):
                salary.save(
                    SalaryBandCommand(
                        series=series,
                        grade="P3",
                        city="深圳",
                        lower=5,
                        upper=20,
                        months=13,
                        effective_from=today,
                        expected_version=0,
                    ),
                    today,
                )


if __name__ == "__main__":
    seed(build_container(Settings()))
    print("Local demo directory seeded (no business requests were created).")
