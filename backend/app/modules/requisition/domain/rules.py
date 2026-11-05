import re
from datetime import date, timedelta

REQUIRED = {
    "recruitType": "招聘类型",
    "dept": "需求部门",
    "employmentType": "用工类型",
    "reqType": "需求类型",
    "headcount": "招聘人数",
    "title": "职位名称",
    "series": "职位序列",
    "level": "职级范围",
    "city": "工作地点",
    "reportTo": "汇报对象",
    "expectedOnboard": "期望到岗",
    "salary": "薪资带宽",
    "reason": "招聘原因",
    "duties": "岗位职责",
    "requirements": "任职资格",
}


def salary_range(text: str) -> tuple[float, float] | None:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*[-–~至]\s*(\d+(?:\.\d+)?)\s*(?:[kK](?:/月)?)?\s*(?:[×x*]\s*(\d{1,2})(?:薪|个月|月)?)?\s*",
        text,
    )
    if not match:
        return None
    low, high = float(match[1]), float(match[2])
    months = int(match[3] or 12)
    return (low, high) if 0 < low <= high <= 1000 and 1 <= months <= 24 else None


def precheck_fields(
    fields: dict[str, str], today: date, available_hc: int, salary_max: float, manager_name: str
) -> list[dict]:
    checks = []

    def add(key, label, ok, detail, warning=False):
        checks.append(
            {
                "key": key,
                "label": label,
                "status": "pass" if ok else ("warn" if warning else "block"),
                "detail": detail,
            }
        )

    missing = [name for key, name in REQUIRED.items() if not fields.get(key, "").strip()]
    add(
        "required",
        "必填字段",
        not missing,
        "完整" if not missing else "请填写：" + "、".join(missing),
    )
    for key, options in {
        "recruitType": {"社招", "校招", "活水"},
        "employmentType": {"正式", "外包", "实习"},
        "reqType": {"新增", "替补", "追加"},
    }.items():
        if fields.get(key):
            add(key, REQUIRED[key], fields[key] in options, "、".join(options))
    count = (
        int(fields["headcount"])
        if fields.get("headcount", "").isascii() and fields.get("headcount", "").isdigit()
        else 0
    )
    add("count", "招聘人数", 1 <= count <= 999, "须为 1–999 的整数")
    extra_text = fields.get("hcRequest", "0") or "0"
    extra = int(extra_text) if extra_text.isascii() and extra_text.isdigit() else -1
    formal = fields.get("employmentType") == "正式"
    add(
        "hc",
        "编制",
        0 <= extra <= 999 and (not formal or count <= available_hc + extra),
        f"可用 HC {available_hc}；超出部分须填写增编申请人数",
    )
    salary = salary_range(fields.get("salary", ""))
    add("salary", "薪资格式", salary is not None, "填写下限–上限 K/月，例如 8-12K/月×13")
    if salary:
        add(
            "salary_band",
            "薪资带宽",
            salary[1] <= salary_max,
            f"当前配置上限 {salary_max:g}K/月，超出将增加审批节点",
            warning=True,
        )
    try:
        valid_date = date.fromisoformat(fields.get("expectedOnboard", "")) >= today + timedelta(
            days=7
        )
    except ValueError:
        valid_date = False
    add("onboard", "到岗日期", valid_date, "填写 YYYY-MM-DD，且至少晚于今天 7 天")
    add(
        "manager",
        "汇报对象",
        fields.get("reportTo") == manager_name,
        f"当前部门已配置负责人：{manager_name}",
    )
    for key, limit in {"title": 30, "reason": 500, "duties": 2000, "requirements": 2000}.items():
        add(
            f"length_{key}",
            REQUIRED[key] + "长度",
            len(fields.get(key, "")) <= limit,
            f"不超过 {limit} 字",
        )
    text = " ".join(fields.get(key, "") for key in ("title", "duties", "requirements"))
    violations = [
        word
        for word in (
            "仅限男性",
            "仅限女性",
            "男性优先",
            "女性优先",
            "已婚已育",
            "未婚未育",
            "不要孕妇",
        )
        if word in text
    ]
    add(
        "discrimination",
        "歧视性表述基础检查",
        not violations,
        "请修改：" + "、".join(violations) if violations else "基础词库通过；模型复核尚未接入",
    )
    if fields.get("reqType") == "替补":
        add(
            "replacement",
            "被替补人",
            False,
            "人员替补关系校验尚未接入，本批可保存草稿，暂不支持提交替补需求",
        )
    if fields.get("reqType") == "追加":
        add("position", "关联岗位", False, "追加岗位需要岗位模块校验；本批暂不支持提交追加需求")
    if fields.get("confidential") == "1":
        add(
            "visibility",
            "保密可见人员",
            bool(fields.get("visibleTo", "").strip()),
            "填写可见人员的用户 ID，以逗号分隔；审批链自动包含",
        )
    return checks
