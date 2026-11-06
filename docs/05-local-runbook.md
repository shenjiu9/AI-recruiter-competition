# 本机运行与验证

以下命令从项目根目录运行。Windows 使用 `backend\.venv\Scripts\python.exe`（Python 3.12）；依赖由项目锁文件安装。

## 招聘系统

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

DeepSeek 插件已安装，A1–A7 草稿已导入。目前缺少模型密钥。将自己的密钥填入 `backend/.env` 的 `DEEPSEEK_API_KEY` 后运行：

```powershell
backend\.venv\Scripts\python.exe deploy/provision_dify_local.py --configure-model --publish
```

脚本向本机 Dify 保存并验证模型凭据，再发布七个工作流，将每个工作流的 API Key 保存在后端 `.env` 的 `DIFY_API_KEYS` JSON 中。重复执行复用已生成的应用与 API Key；模型密钥变更使用指纹识别，不回显密钥。模型地址与名称依据 [DeepSeek 官方接口说明](https://api-docs.deepseek.com/)。

工作流未实测成功之前保持 `AI_WORKER_ENABLED=false` 与组件关闭。模型验证后，可将其改为 `true`，重建 API 容器，通过管理员的“自动化策略”先开启所需组件并选择影子模式。从岗位／候选人／面试详情进入“AI 任务与复核”，核对真实模型输出。质量验收后再决定是否允许特定节点自动执行。

工作流模板位于 `deploy/dify/workflows`。需要用项目模板更新已有草稿时明确执行 `--sync-drafts`，这会覆盖相应草稿；普通部署不会覆盖人工编辑。生成模板：

```powershell
Push-Location backend
.venv\Scripts\python.exe scripts/generate_dify_workflows.py
Pop-Location
backend\.venv\Scripts\python.exe deploy/provision_dify_local.py --sync-drafts
```

模型执行全部在服务端。招聘系统无需引入额外 Agent 框架；Dify 的模型编排与后端确定性业务状态机分工。

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
