"""Tool catalog of the HR assistant: everything it can look up or do, in one place.

Each tool names one thing the HR can ask for in a sentence. The catalog drives three things,
so adding a tool updates them together:

* the A0 router prompt (``scripts/generate_dify_workflows.py`` lists every tool),
* the keyword rules used when the router model is unavailable,
* the capability list the assistant shows for "你能做什么".

Modes say how a tool may touch data:

* ``read``    answers from the same read facades as the pages, with the requester's permissions.
* ``direct``  a small, reversible change that does not need a human review step (tags, key
  candidate, who handles a conversation). It runs at once and the reply carries an undo button.
* ``confirm`` a change that affects a candidate or a process (advance, reject, message, pause).
  It is returned as a confirmation card; the browser calls the existing endpoint after the HR
  confirms, so permissions, idempotency, optimistic locking and audit are unchanged.
* ``ai``      an A1–A7 job that runs in the background and waits for the HR's review.

Human review steps (hiring decisions and approvals, requisition approvals, AI result review,
interview feedback, JD approval) are deliberately not tools: the assistant links to them.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    mode: str  # read | direct | confirm | ai | meta
    router: str  # what the A0 router should know about the tool
    example: str = ""  # one sentence the HR could say
    pattern: str = ""  # keyword rule used without the router model
    stage: str = "pre"  # pre: before the A1–A6 task rules; post: after them
    args: tuple = field(default=())


T = Tool
CATALOG = [
    # ----- conversation --------------------------------------------------------------
    T(
        "help",
        "怎么用",
        "meta",
        "打招呼、问你能做什么、怎么用。",
        "你能做什么",
        r"^(你好|您好|hi|hello|在吗)|你能(做|干)什么|能帮我(做|干)?什么|怎么用|使用说明|^帮助$",
    ),
    T(
        "none",
        "无法处理",
        "meta",
        "与招聘无关，或要求你直接发 offer、决定录用、改薪资、审批、删除数据等系统不允许助手做的事。",
    ),
    # ----- AI work that must be read before the action rules ---------------------------
    T(
        "A6",
        "整理面试记录",
        "ai",
        "把一段面试记录原文整理成面评要点（content 填记录原文）。",
        "整理张三的面试记录：沟通清晰，有两年电商客服经验",
        r"面评|面试(记录|纪要|笔记)|整理.{0,8}面试",
        args=("candidate", "content"),
    ),
    # ----- direct, reversible changes --------------------------------------------------
    T(
        "key",
        "设为重点候选人",
        "direct",
        "把某候选人设为或取消重点候选人（取消时 keyword=取消）。",
        "把张三设为重点候选人",
        r"(设为|设成|标为|标记为|标成|列为|加为|作为)重点|取消.{0,8}重点|重点.{0,4}(取消|去掉)",
        args=("candidate", "keyword"),
    ),
    T(
        "tag",
        "打标签",
        "direct",
        "给某候选人加标签（keyword 逐字复制标签文字）。",
        "给张三打个标签：沟通好",
        r"(打|加|贴|添加|标记|标上)(个|一个|上)?标签|标签[：:]",
        args=("candidate", "keyword"),
    ),
    T(
        "hand_back",
        "会话交还 AI",
        "direct",
        "把某候选人的会话交还给 AI 自动回复。",
        "把张三的会话交还给 AI",
        r"(交还|交回|还给|交给)\s*AI|恢复\s*AI\s*(自动)?(回复|托管)|AI\s*托管",
        args=("candidate",),
    ),
    T(
        "take_over",
        "接管会话",
        "direct",
        "HR 亲自接管某候选人的会话，AI 自动回复暂停。",
        "接管张三的会话",
        r"接管|我(亲自|自己)?来(回复|沟通|跟进|聊)",
        args=("candidate",),
    ),
    # ----- changes confirmed by the HR ------------------------------------------------
    T(
        "message",
        "发消息",
        "confirm",
        "让系统以 HR 名义直接给某候选人发一条已写好的消息（content 逐字复制正文，通常在冒号之后）。",
        "给张三发消息：明天上午 10 点电话沟通",
        r"(给|跟|和|向).{1,16}(发|留|说).{0,3}(消息|信息|短信|一声|个话|一句)|发消息给|发信息给|(告诉|通知)[^，。]{1,12}[：:]",
        args=("candidate", "content"),
    ),
    T(
        "restore",
        "撤销淘汰",
        "confirm",
        "撤销对某候选人的淘汰，恢复其应聘流程。",
        "撤销张三的淘汰",
        r"(撤销|撤回|取消).{0,4}淘汰|淘汰.{0,4}(撤销|撤回|取消)|恢复.{0,8}(应聘|流程)",
        args=("candidate", "position"),
    ),
    T(
        "reject",
        "淘汰",
        "confirm",
        "淘汰某候选人、终止其流程。",
        "淘汰张三",
        r"淘汰(?!原因|率|了多少|数据|统计|情况|的人数|的人都|的原因)|刷掉|拒掉|不再推进|终止.{0,4}(流程|应聘)",
        args=("candidate", "position"),
    ),
    T(
        "attach",
        "关联岗位",
        "confirm",
        "把某候选人加到/关联到/推荐到某岗位。",
        "把李四加到夜班客服",
        r"(加到|加入|关联到|挂到|投递到|放到|添加到|推荐到).{0,16}",
        args=("candidate", "position"),
    ),
    T(
        "advance",
        "推进阶段",
        "confirm",
        "把某候选人推进到下一阶段、安排进面试。",
        "推进张三",
        r"推进|推到|往前推|下一(阶段|步)|进入下一|约面|进面试|进入面试|安排.{0,6}面试",
        args=("candidate", "position"),
    ),
    T(
        "pause",
        "暂停岗位",
        "confirm",
        "暂停某岗位的招聘。",
        "暂停夜班客服的招聘",
        r"暂停.{0,12}(招聘|岗位|职位)|(岗位|职位|招聘).{0,6}暂停",
        args=("position",),
    ),
    T(
        "resume",
        "恢复岗位",
        "confirm",
        "恢复已暂停岗位的招聘。",
        "恢复夜班客服的招聘",
        r"(恢复|重启|重新开放|继续|重新开始).{0,8}(招聘|岗位|职位)",
        args=("position",),
    ),
    # ----- read-only answers -------------------------------------------------------------
    T(
        "conversation",
        "沟通记录",
        "read",
        "看某候选人的聊天/沟通记录、最近说了什么、有没有回复。",
        "张三最近说了什么",
        r"(聊天|沟通|对话|会话|消息)(记录|内容|历史)|(说了|回了|聊了|问了)(些)?什么|回(复|消息)了(吗|没)|有没有回(复|消息)",
        args=("candidate",),
    ),
    T(
        "reviews",
        "待复核 AI 结果",
        "read",
        "待复核的 AI 结果或 AI 任务。",
        "待我复核的 AI 结果",
        r"复核|待审核|待确认的(建议|结果)|AI.{0,6}(结果|任务)",
    ),
    T(
        "cards",
        "待处理决策",
        "read",
        "等 HR 决定的决策卡、提醒（如超时未推进、候选人要求处理）。",
        "有哪些决策卡要处理",
        r"决策卡|待决策|要我(决定|拍板)|提醒卡",
    ),
    T(
        "interviews",
        "面试安排",
        "read",
        "面试安排、日程、有几场面试（keyword 可填 今天/明天/本周/下周/我的）。",
        "本周的面试安排",
        r"面试(安排|日程|计划|列表|情况)|(今天|明天|后天|本周|这周|下周|最近|我的|有哪些|有几场|几场).{0,6}面试",
        args=("candidate", "position", "keyword"),
    ),
    T(
        "hires",
        "录用进展",
        "read",
        "录用、入职、移交的进展（只查看，不做录用决定）。",
        "录用待办",
        r"录用|offer|入职|移交",
        args=("candidate",),
    ),
    T(
        "requisitions",
        "招聘需求",
        "read",
        "招聘需求、需求审批走到哪一步（keyword 逐字复制需求名称）。",
        "招聘需求审批到哪了",
        r"招聘需求|需求单|需求审批|用人需求|编制申请",
        args=("keyword",),
    ),
    T(
        "headcount",
        "编制",
        "read",
        "部门编制（HC）总数、已用、剩余。",
        "各部门编制还剩多少",
        r"编制|HC|hc|人头|headcount",
    ),
    T(
        "salary",
        "薪资带宽",
        "read",
        "查看薪资带宽/薪酬标准（只查看，不定薪）。",
        "客服的薪资带宽是多少",
        r"薪资(带宽|范围|区间|标准|档)|薪酬(带宽|范围|标准|区间)|工资(范围|标准|区间)",
        args=("keyword",),
    ),
    T(
        "automation",
        "自动化设置",
        "read",
        "自动化/AI 托管设置：自动回复、自动推进等开关现状。",
        "现在的自动化设置是什么",
        r"自动化|自动(回复|推进|筛选|评估).{0,3}(设置|开关|规则|开|关)|托管设置|AI.{0,4}(设置|开关)",
    ),
    T(
        "org",
        "组织架构",
        "read",
        "部门列表、组织架构。",
        "有哪些部门",
        r"组织架构|有哪些部门|部门(列表|有哪些|结构)",
    ),
    T(
        "stats",
        "招聘数据",
        "read",
        "招聘数据和图表：漏斗、各阶段转化、来源/渠道分布、淘汰原因、每周新增趋势（只要数据，不要分析建议）。",
        "看看客服专员的招聘漏斗",
        r"报表|统计|数据看板|看板|图表|可视化|趋势|来源分布|渠道分布|淘汰.{0,6}原因|转化(率|情况|数据)|漏斗|招聘数据",
        args=("position",),
    ),
    T(
        "overview",
        "今日待办",
        "read",
        "今天的待办、要处理的事、工作概览。",
        "今天有什么要处理",
        r"今天.{0,4}(要|有什么|有啥|待|该|做|安排|干|忙)|待办|要处理|概览|总览|日报|汇总|工作台|有什么事|忙什么|该做什么",
    ),
    T(
        "pipeline",
        "岗位候选人",
        "read",
        "列出某岗位的候选人名单，或某阶段有哪些人（keyword 可填阶段名：触达/沟通/评估/面试）。",
        "客服专员面试阶段有哪些人",
        r"(有哪些|有谁|都有谁|哪些)(候选人|人)|(候选人|人选)(名单|分布)|(触达|沟通|评估|面试|经理评估)(阶段|中)的(人|候选人)",
        args=("position", "keyword"),
    ),
    T(
        "candidates",
        "找候选人",
        "read",
        "在候选人库里按技能/经历找人、列出候选人（keyword 逐字复制技能或经历词）。",
        "找会 Excel 的候选人",
        r"找.{0,12}(的候选人|的人)|有没有.{0,12}(候选人|的人)|候选人(列表|库)|人才库里|最近.{0,4}(的)?候选人",
        args=("keyword",),
    ),
    # ----- AI work (rules live in intent.RULES) --------------------------------------------
    T(
        "A1",
        "写 JD 与画像",
        "ai",
        "为某岗位生成或改写任职要求、加分项、JD、必问问题。",
        "帮客服专员写一版 JD",
        args=("position",),
    ),
    T(
        "A2",
        "人才搜索建议",
        "ai",
        "为某岗位给出外部渠道的人才搜索关键词、城市、排除词，或问去哪里找人。",
        "给客服专员出一份人才搜索关键词",
        args=("position",),
    ),
    T(
        "A3",
        "提取简历",
        "ai",
        "从某候选人的简历提取技能、经历、学历等信息到档案。",
        "提取张三的简历信息",
        args=("candidate",),
    ),
    T(
        "A4",
        "起草回复",
        "ai",
        "请 AI 起草回复某候选人消息的话术（HR 没有给出具体内容）。",
        "帮我回复张三的消息",
        args=("candidate",),
    ),
    T(
        "A5",
        "评估候选人",
        "ai",
        "评估某候选人是否符合岗位要求、匹配度、能否通过初筛。",
        "评估一下张三是否符合要求",
        args=("candidate", "position"),
    ),
    T(
        "A7",
        "岗位数据洞察",
        "ai",
        "岗位数据洞察：问为什么招得慢、瓶颈在哪、怎么改进（需要 AI 分析和建议）。",
        "为什么夜班客服招得慢",
        r"为什么|瓶颈|分析|洞察|卡在|怎么办|改进|太慢|很慢",
        stage="post",
        args=("position",),
    ),
    T(
        "positions",
        "岗位进度",
        "read",
        "岗位招聘进度、还差几人、招满没有、有哪些在招岗位（只问数字和现状）。",
        "白班客服还差几个人",
        r"还差|缺几|差几|多少人|几个人|几人|招满|到岗|进度|岗位(列表|情况)|哪些岗位|在招",
        stage="post",
        args=("position",),
    ),
    T(
        "candidate",
        "候选人进展",
        "read",
        "某位候选人的进展、到哪一步、基本情况、经历时间线。",
        "张三到哪一步了",
        r"到哪(一步|了)|什么阶段|哪个阶段|进展|状态|情况|怎么样|是谁|简介",
        stage="post",
        args=("candidate",),
    ),
]
TOOLS = {t.name: t for t in CATALOG}
PRE_RULES = [(t.name, t.pattern) for t in CATALOG if t.pattern and t.stage == "pre"]
POST_RULES = [(t.name, t.pattern) for t in CATALOG if t.pattern and t.stage == "post"]
CAPABILITIES = [
    ("查进展", "今天有什么要处理 / 客服专员还差几个人 / 张三到哪一步了 / 张三最近说了什么"),
    ("看数据", "看看客服专员的招聘漏斗 / 淘汰原因统计 / 各部门编制还剩多少"),
    ("找人", "找会 Python 的候选人 / 客服专员面试阶段有哪些人 / 本周的面试安排"),
    ("让 AI 干活", "帮客服专员写一版 JD / 评估一下张三 / 帮我回复张三的消息"),
    ("直接办", "把张三设为重点候选人 / 给张三打个标签：沟通好 / 接管张三的会话"),
    ("确认后办", "把张三加到客服专员岗位 / 推进张三 / 淘汰张三 / 暂停夜班客服的招聘"),
    ("沟通", "给张三发消息：明天上午 10 点电话沟通"),
]


def router_lines():
    """The intent list of the A0 router prompt, one line per tool."""
    return "\n".join(f"{t.name} {t.router}" for t in CATALOG)


def router_examples():
    return "；".join(f"“{t.example}” → {t.name}" for t in CATALOG if t.example)
