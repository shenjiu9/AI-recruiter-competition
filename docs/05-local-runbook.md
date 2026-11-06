# 本机运行与验证

以下命令从项目根目录运行。Windows 使用 `backend\.venv\Scripts\python.exe`（Python 3.12）；依赖由项目锁文件安装。

## 招聘系统

本机已配置完成后，可以一次启动招聘系统和 Dify：

```powershell
.\deploy\start_local.ps1
# 更新代码后需要重新构建镜像时：
.\deploy\start_local.ps1 -Rebuild
```

脚本保留数据库与配置，等待 API 和 Dify 就绪后输出入口。招聘系统常驻容器使用 `unless-stopped` 重启策略；Docker Desktop 本身仍须处于运行状态。

```powershell
docker desktop start --timeout 60
docker compose --env-file backend/.env -f deploy/compose.yaml --profile demo --profile web up -d --build
docker compose --env-file backend/.env -f deploy/compose.yaml ps --all
```

入口：HR http://localhost:5173 ，业务 H5 http://localhost:5174 ，候选人 H5 http://localhost:5175 。候选人必须使用 HR 生成的签名链接。API 就绪检查：http://localhost:8000/health/ready 。演示登录口令在 `backend/.env` 的 `DEV_LOGIN_PASSWORD`，请勿复制到聊天或提交 Git。

Compose 使用独立 PostgreSQL 库，原 SQLite 开发文件保留。迁移服务完成后 API 才启动。本次数据库版本为 `0013`。

## 本机 Dify 与 DeepSeek

已部署官方 [Dify 1.19.0](https://github.com/langgenius/dify/releases/tag/1.19.0)，目录为项目同级 `dify-local`。访问 http://localhost:8080 。管理员邮箱及随机口令在 `backend/.env.dify-local`，该文件已忽略。

```powershell
backend\.venv\Scripts\python.exe deploy/setup_dify_local.py ..\dify-local
docker compose -f ..\dify-local\docker\compose.local.json up -d
docker compose -f ..\dify-local\docker\compose.local.json ps --all
```

`compose.local.json` 包含解析后的凭据，只留本机。所有对外端口绑定回环地址。不要执行 `down -v`，这会删除持久化数据。

本机 DeepSeek 凭据已验证，A1–A7 工作流已发布，后端已配置各工作流 Key。凭据保留在本机，不随 Git 提交。新环境或更换密钥时，将自己的密钥填入 `backend/.env` 的 `DEEPSEEK_API_KEY` 后运行：

```powershell
backend\.venv\Scripts\python.exe deploy/provision_dify_local.py --configure-model --publish
```

脚本向本机 Dify 保存并验证模型凭据，再发布 A0 指令路由和 A1–A7 共八个工作流，将每个工作流的 API Key 保存在后端 `.env` 的 `DIFY_API_KEYS` JSON 中。重复执行复用已生成的应用与 API Key；模型密钥变更使用指纹识别，不回显密钥。模型地址与名称依据 [DeepSeek 官方接口说明](https://api-docs.deepseek.com/)。

本机已开启 AI worker 和七个组件，采用人工复核模式：显式发起任务后，后台调用真实模型；业务写入须复核后确认。单次 Dify 请求超时为 120 秒。新环境默认仍关闭 AI worker；需要按本机验证步骤配置后启用。影子模式只记录结果，质量验收后再决定是否允许特定节点自动执行。

### 一句话发起 AI 任务

HR 端顶部的 AI 指令栏（⌘K / Ctrl+K）和“AI 任务与复核”页可以直接输入一句话，如“白班客服还差几个人”“评估一下张三”。后端 `POST /api/v1/hr/ai-intents` 先由 A0 工作流识别要做的任务，再在当前账号可见的岗位、候选人、应聘与面试中匹配对象：唯一匹配时直接创建任务，多个或缺少对象时返回可选项。A0 只看到脱敏后的这句话，看不到业务数据；它给出的姓名、岗位必须在原句中逐字出现，否则作废。A0 未发布或调用失败时自动改用关键词规则，功能不中断。创建出的任务与手动发起完全相同，仍经过权限、授权、阶段、组件开关和人工复核。

`deploy/dify/workflows/A0.yml` 已随代码提交。已部署的本机环境执行一次下列命令导入并发布 A0，后端 `DIFY_API_KEYS` 会自动加入 A0 的 Key，重启 API 后生效：

```powershell
backend\.venv\Scripts\python.exe deploy/provision_dify_local.py --sync-drafts --publish
```

路由效果可用 `DEEPSEEK_API_KEY=... python backend/scripts/eval_router_direct.py --report test-results/router.json` 直接对 DeepSeek 抽查。

模型分配保存在 `deploy/dify/model-routing.json`。当前两种模型都已通过账号可用性和 Dify 插件检查：

| 工作流 | 模型 | 当前用途 |
| --- | --- | --- |
| A1、A5、A6、A7 | `deepseek-v4-pro` | 画像／JD、证据评估、面试记录整理、岗位数据分析 |
| A0、A2、A3、A4 | `deepseek-flash` | 指令路由、搜索关键词建议、职业字段提取、受限知识答复 |

两个模型均使用非思考模式和 JSON 输出，输出长度按组件设置；这是当前子功能的运行配置，不代表完整工作流的质量评测结论。调整路由后需重新生成 DSL、同步草稿并发布。

工作流模板位于 `deploy/dify/workflows`。需要用项目模板更新已有草稿时明确执行 `--sync-drafts`，这会覆盖相应草稿；普通部署不会覆盖人工编辑。生成模板：

```powershell
Push-Location backend
.venv\Scripts\python.exe scripts/generate_dify_workflows.py
Pop-Location
backend\.venv\Scripts\python.exe deploy/provision_dify_local.py --sync-drafts --publish
```

模型执行全部在服务端。招聘系统无需引入额外 Agent 框架；Dify 的模型编排与后端确定性业务状态机分工。

## 真实模型与本机演示验证

以下命令会调用付费模型，仅手动执行，不进入 CI：

```powershell
backend\.venv\Scripts\python.exe backend/scripts/smoke_dify.py
backend\.venv\Scripts\python.exe deploy/local_demo.py
```

第一条只发送合成资料，逐项检查七个组件的实际结果；A5 调用三次。网络失败最多重试两次，报告记录重试次数及运行编号。报告在 `test-results/dify-live-smoke.json`，该目录会被浏览器测试清理。

第二条在本机开发账号下创建明确标记的合成需求、岗位、候选人、应聘和面试数据，将七个组件设为人工复核模式，并执行真实 AI 任务。它验证 A3 更新、A5 推进面试、A6 整理、A4 候选人 H5 回复及 A1/A2/A7 建议；A1 草稿保留待复核。中间状态与候选人专属链接保存在被 Git 忽略的 `backups/local-demo.json`，再次运行复用既有对象。此脚本会改变本机演示数据和策略，不用于真实业务环境。

本机联调通过不代表完整 PRD 已实现：A1 对话式需求、A2 检索排名、A6 完整初面等仍有开发缺口，见 [ADR 0014](adr/0014-dify-jobs-and-local-operations.md)。未配置的飞书、腾讯会议、短信／邮件、渠道保持预留，不将站内行为描述为外部服务成功。

## 数据备份与恢复演练

```powershell
backend\.venv\Scripts\python.exe deploy/backup_local.py backup backups/recruiter-new.backup.enc
backend\.venv\Scripts\python.exe deploy/backup_local.py verify backups/recruiter-new.backup.enc
```

备份不可覆盖已有文件。恢复演练只创建随机临时测试库，并在结束后删除；不会恢复到现有项目库。另行保存 `ENCRYPTION_KEY`，否则备份和业务加密数据都无法解密。当前脚本仅备份招聘系统 PostgreSQL；Dify 数据库、存储卷和模型配置需要独立备份策略，不能以本脚本代替。

## 检查与故障处理

```powershell
Push-Location backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check app tests migrations scripts
.venv\Scripts\lint-imports.exe
.venv\Scripts\python.exe scripts/export_openapi.py --check
Pop-Location
npx.cmd --yes pnpm@10.28.0 typecheck
npx.cmd --yes pnpm@10.28.0 lint
$env:PLAYWRIGHT_CHANNEL='chrome'
npx.cmd --yes pnpm@10.28.0 test:e2e
backend\.venv\Scripts\python.exe backend/scripts/load_smoke.py
```

完整 PostgreSQL 测试须将 `TEST_DATABASE_URL` 和 `DATABASE_URL` 指向独立、以 `_test` 结尾的数据库，先迁移后测试。严禁用业务库跑测试。

管理员 API `/api/v1/hr/operations` 可检查排队、重试、失败与积压。AI 任务失败先看错误码和 Dify 运行记录；上下文变化应重新生成，不强行重试旧结果。`AI_NOT_CONFIGURED` 表示后端未配置工作流 Key，不是模型成功。后台死信可在任务页说明原因后重新排队。停用组件或切回人工模式会使旧策略下的任务失效。

本机验证不等同生产上线。当前缺少真实外部应用配置，H5 消息不等于短信送达，内部发布不等于渠道上线，开发登录不等于飞书 SSO。
