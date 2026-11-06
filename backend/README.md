# 后端：招聘需求审批与组织规则

当前已交付招聘需求审批、年度编制、职级薪资规则、代理修改确认，以及组织目录只读展示 / 权限 / 审批人配置管理。完整任务、依赖和剩余范围见 [交付任务](../docs/04-delivery-plan.md)。

## 已实现

- FastAPI、SQLAlchemy 2、Alembic，生产目标 PostgreSQL 16；SQLite 仅作为本地过渡和快速测试适配器。
- `org`、`req`、`platform` 三个 schema；模块门面与仓储端口；事务中一起保存业务数据、审计、事件和幂等响应。
- JWT 8 小时会话，每次请求重新读取在职状态与角色；开发登录默认关闭，必须同时配置开发环境和口令；尚未接入飞书 SSO。
- 24 小时幂等，重复内容返回第一次结果，复用键修改内容返回 409；数据库 CAS 版本冲突；统一错误信封与 trace ID。
- 薪资等完整需求字段、审批记录、幂等响应用 AES-GCM 加密；事件仅存 ID/版本；PostgreSQL 触发器禁止修改/删除审计行。
- 需求草稿保存/恢复/修改、分页列表、详情、基础预检、组织审批链、提交/撤回/重新提交、当前审批人通过/驳回；本批提交支持“新增”，替补和追加可存草稿。
- HR Web 与业务 H5 已接真实接口，浏览器测试覆盖保存恢复、驳回重提、三级审批；原模拟模式仍可用于其他页面演示。

## Windows 本地运行

工作目录为仓库内的 `backend`。本机已安装 Python 3.12.10；不要用系统默认 Python 3.15。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock -e .
.\.venv\Scripts\python.exe scripts/setup_local.py
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.dev_seed
.\.venv\Scripts\uvicorn.exe app.main:create_app --factory --host 127.0.0.1 --port 8000
```

`setup_local.py` 生成 `.env` 中的随机会话密钥、加密密钥和开发登录口令，已有文件时不会覆盖。默认连接本机 PostgreSQL。没有可用 PostgreSQL 时，可在首次生成环境时加 `--sqlite`；这不能替代 PostgreSQL 并发与部署验收。本机已有 `.env` 保留早期 SQLite 开发配置；Docker Compose 使用独立的 PostgreSQL 数据卷，两者数据不会自动合并。

另开终端，在仓库根目录启动前端：

```powershell
$env:VITE_USE_MOCK = 'false'
npx.cmd --yes pnpm@10.28.0 dev:hr
# 另一终端同样设置 VITE_USE_MOCK=false，再运行 dev:biz
```

HR：[http://localhost:5173](http://localhost:5173)，业务端：[http://localhost:5174](http://localhost:5174)，API 文档：[http://localhost:8000/docs](http://localhost:8000/docs)。登录页面选择开发账号，口令在本地 `backend/.env` 的 `DEV_LOGIN_PASSWORD` 中。不要把该文件提交到 GitHub。

演示组织账号：`hr`（林悦）、`manager`（何美玲/客服中心）、`director`（部门负责人）、`hrbp`、`hrd`；开发编制数据为各部门可用 HC 2、薪资上限 20K。种子数据只能在显式开发模式下导入。它们不是公司真实通讯录/编制规则。

手填示例：客服中心、正式、新增、2 人、客服专员、客服序列、P3、深圳、何美玲、未来至少 7 天的 `YYYY-MM-DD`、薪资 `8-12K/月×13`、招聘原因/职责/资格。由 HR 提交后，依次切换到 `manager → director → hrbp` 审批。

## Docker

本机 Docker Desktop、Docker CLI、Compose 和 WSL 已安装，Linux 引擎已启动并完成项目容器验收。2026-11-05 复查确认虚拟化平台和 WSL 已启用，启动 Docker Desktop 后即可正常运行，无需再次重启 Windows。数据库、Redis、API 和三个前端均已启动，迁移和演示目录初始化成功。

日常启动，在仓库根目录执行：

```powershell
docker desktop start --timeout 60
docker version
docker compose --env-file backend/.env -f deploy/compose.yaml --profile demo --profile web up -d --build
docker compose --env-file backend/.env -f deploy/compose.yaml ps
```

访问 HR `http://localhost:5173`、业务 H5 `http://localhost:5174`、候选人 H5 `http://localhost:5175` 和 API `http://localhost:8000/docs`。候选人需通过 HR 生成的专属链接进入，直接访问首页会显示链接缺失提示。开发登录口令沿用本地 `.env`，不写入文档。

PostgreSQL 使用 `ai-recruiter_postgres-data` 命名卷。已验证容器重启后迁移版本 `0012`、11 名目录人员及 4 个部门保持不变，API 恢复正常；HR／业务端真实登录和深层路由已通过浏览器检查。容器库初始化为演示组织，原 SQLite 数据库仍原样保留，没有执行数据迁移或覆盖。

本机容器 PostgreSQL 的独立临时测试库已跑通全部 311 项后端测试，无跳过，并通过迁移回退／升级及 schema 一致性检查；测试库已清理。此验收不替代 B10 的生产负载、备份恢复及上线检查。

Compose 包含 PostgreSQL、Redis、一次性迁移、显式演示组织种子、API、HR／业务／候选人前端；服务端口只绑定到 `127.0.0.1`。容器强制使用 PostgreSQL，忽略本地 `.env` 中可能配置的 SQLite URL。数据保存于命名卷。Redis 当前仅预留给后续限流/缓存模块。

Docker Compose 是本地开发配置，不是生产部署模板；默认本地数据库口令不能用于公开部署。正式环境必须关闭开发登录、配置正式组织/身份来源及独立数据库角色，并接入密钥服务。

## 测试与检查

```powershell
# backend 下
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check app tests migrations scripts
.\.venv\Scripts\lint-imports.exe
.\.venv\Scripts\alembic.exe check

# 仓库根目录
npx.cmd --yes pnpm@10.28.0 typecheck
npx.cmd --yes pnpm@10.28.0 lint
npx.cmd --yes pnpm@10.28.0 build
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npx.cmd --yes pnpm@10.28.0 test:e2e
```

E2E 启动独立的临时数据库及 8010/5183/5184/5185 端口，不使用本地 `.env` 的业务数据库。未安装 Chrome 时先 `pnpm exec playwright install chromium`，不要设置 `PLAYWRIGHT_CHANNEL`。CI 会自动安装 Chromium。

PostgreSQL 验证：设置 `DATABASE_URL` 和 `TEST_DATABASE_URL` 为同一个隔离测试库 URL，先 `alembic upgrade head` 再 `pytest -q`。测试库名必须以 `_test` 结尾；测试会清空该库的业务表。GitHub Actions 使用临时 PostgreSQL 16，运行同一套测试及额外的四并发幂等/审计不可变测试，再验证迁移回退、升级、schema 一致性和镜像构建。

## 本批边界

- 需求表单部门树、汇报对象及保密可见人员已接入本地组织目录，两端确认支持稳定人员 ID、搜索分页、失效值提示；服务端在写入 / 提交时校验在职和部门范围。兼容旧姓名字段，但重名须重选。无需新迁移，详见 `docs/adr/0007-requisition-form-directory.md`；本地有效授权范围不等于真实飞书任职关系。
- 岗位已接通审批事件生成、同岗合并 / 新建与 3 工作日超时、负责 / 共享 HR、画像生效版本与经理修改确认、知识披露与失效引用、JD 版本审批、内部发布 / 暂停 / 恢复 / 关闭、经理关闭确认及面试流程版本。升级至 `0007` 后执行 `python -m app.position_worker --sync-source-access` 重建历史岗位来源需求的额外读权限。API 默认每 2 秒处理事件和超时；详见 `docs/adr/0008-position-generation.md`、`0009-position-content-and-collaboration.md`。
- 工作日日历默认周末休息，部署方用 `POSITION_HOLIDAYS` / `POSITION_WORKDAYS` JSON 日期数组配置节假日 / 调休。知识披露预览不等于 Dify 已同步或消息已发送；共享和留言目前仅站内可见。
- 年度编制维护和终审原子预占/加签已交付，HRBP / 编制负责人可使用 HR Web `/settings/headcount`。部署升级后先录入真实编制；迁移不推断预算、不追溯补扣既有审批通过需求。
- 职级薪资维护与独立 HRD 加签已交付，招聘负责人 / 薪酬负责人使用 `/settings/salary`；支持版本、生效日期与历史。薪资缺行阻止提交，月薪 / 年薪越界加签 HRD。本机开发库已升级 `0003`。真实环境需录入薪资行和部门策略 `hrd_id`；演示账号 `salary_hrd` 负责审批，`payroll` 负责维护。详见 `docs/adr/0003-salary-bands.md`。
- 组织权限与审批人配置页 `/settings/organization` 已交付：开发账号 `admin` 维护，招聘负责人只读授权范围；支持版本历史、恢复为新版本和审批试算。迁移 `0004` 分离目录派生角色与人工授权，真实部署首位管理员使用 `python -m app.bootstrap_admin`，详见 `docs/adr/0005-organization-permissions.md`。
- 人工审批转交、离职 / 调岗内部事件接续及负责人交接已交付，两端支持转交和站内消息；迁移至 `0005`。内部重放命令 `python -m app.process_directory_change --file verified-directory-event.json` 要求先核验并导入目录版本，不提供修改在职状态的业务接口。详见 `docs/adr/0006-approval-transfers.md`。
- 正式飞书 SSO/通讯录同步与事件验签、飞书通知、催办和草稿自动保存尚未交付。编制当前仅支持年度；待审批投影、季度/结转、Excel 导入及录用转已用后续完成。岗位关闭剩余预占释放已在 B04a 接通。
- 预检仅有确定性基础规则；替补/追加关系、相似需求识别和 AI 复核尚未接入；不能当作完整 PRD 验收通过。
- Dify 未配置时 AI 填表返回 `503 AI_DEGRADED`，不会生成伪造的 AI 结果。
- 候选人 / 简历 / 应聘核心接口已接通，升级至 `0009`；HR Web 支持上传、解析核对、去重、合并撤销、授权证据、挂人、冷却、阶段操作和删除，业务 H5 查看脱敏资料。原件用数据库加密 BLOB 保存，PDF / DOCX 提取文本；图片、扫描件和旧 Word 待人工补全，尚未接 OCR / S3。详见 `docs/adr/0010-candidates-and-applications.md`。
- 候选人签名链接、授权和 HR／候选人 H5 双向沟通，以及内部预约／面评流程已实现，详见 ADR 0011／0012；短信、邮件、真实会议／日历适配器和 AI 回复尚未接入。
- 升级至 `0012` 后，HR Web 和业务 H5 `/hiring` 可处理面评后的经理决定、录用审批、名额占用；HR 登记实际移交并回填结果，支持 Excel 移交单导出。`/workbench` 展示真实权限范围的岗位／卡片／录用数据，自动化设置支持策略及历史恢复。后台同步复用 `CONVERSATION_WORKER_ENABLED` 循环，页面请求也会刷新待办。AI 执行及外部移交仍未配置，详情与边界见 `docs/adr/0013-hiring-decisions-and-automation.md`。默认 mock 模式保留原前端演示。
- 代理修改确认已交付：HR Web 详情 / 业务 H5 待办的“修改并确认”支持预检、条件加签、字段差异；重提也记录相对上次提交的差异。详情、规则快照和差异加密保存，通用审计仅记录状态 / 版本。旧载荷原样确认兼容，修改须撤回重提。详见 `docs/adr/0004-proxy-confirmation.md`。
- 已实现岗位专用持久化 inbox / 重试；通用分区 worker、运维看板、过期幂等清理、限流、生产角色隔离与监控仍在后续任务中。
