# 新加坡云端演示环境

服务器：Vultr Singapore，45.76.191.78，Ubuntu 24.04 LTS，6 vCPU / 16 GB / 320 GB。部署目录 `/opt/ai-recruiter`。

## 入口与权限

- HR：https://hr.45-76-191-78.sslip.io
- 业务端：https://biz.45-76-191-78.sslip.io
- 候选人：https://candidate.45-76-191-78.sslip.io（须 HR 签发的个人链接）
- Dify：https://dify.45-76-191-78.sslip.io

暂用 sslip.io 免费 DNS；域名可用性依赖该服务。HTTPS 证书由 Caddy 自动签发和续期。后续可换为自有域名。

当前是比赛演示账号模式，使用独立随机口令；持有招聘系统口令的人可选择演示角色。正式团队使用前应接入企业身份认证。Dify 使用独立管理员密码，只交给需要管理工作流的人。A0–A7 的匿名 Web App 分享入口已关闭，保留管理员工作流编辑和携带 API Key 的服务端调用。

云端使用新建数据库，只有初始化组织、演示账号和明确标识的合成联调候选人；没有迁移本机招聘资料。本机配置及数据库保留。未提供的飞书、腾讯会议、短信、邮件和渠道凭据继续预留。

## SSH 与更新

本机 PowerShell：`ssh ai-recruiter-sgp`，用户 `deploy`，密钥位于本机 `~/.ssh/ai_recruiter_sgp`。服务器禁用 SSH 密码及 root 登录；`deploy` 可 sudo。公网仅开放 TCP 22、80、443；数据库、Redis、API、Dify 原始端口仅绑定回环地址。Docker 内网通过独立网络连接 Dify nginx；Dify API 使用专用 DNS 别名，避免与招聘 API 同名冲突。

部署分支 `deploy/vultr-singapore` 整合最新 main 的 PR #5（自然语言任务）和前端改版分支。不要直接切回不含改版的 main。服务器 GitHub 部署密钥仅能读取本仓库，不能推送。

更新服务器：

```bash
bash /opt/ai-recruiter/app/deploy/cloud/update.sh
```

Dify 固定 1.19.0，目录 `/opt/ai-recruiter/dify`。启动：

```bash
docker compose -f /opt/ai-recruiter/dify/docker/compose.local.json up -d
```

容器设有自动重启策略，Docker、Caddy、fail2ban 随系统启动。不要执行 `down -v`。数据在 Docker 卷中；未购买 Vultr 自动备份，也尚未配置异地备份。

## 密钥与工作流

招聘环境变量在 `/opt/ai-recruiter/app/backend/.env`，Dify 管理员资料在同目录 `.env.dify-local`；Dify 解析配置在 `/opt/ai-recruiter/dify/docker/compose.local.json`。这些文件包含敏感信息，不提交仓库。私密本机副本在原项目 `backups/cloud-singapore`。

A0/A2/A3/A4 使用 deepseek-flash；A1/A5/A6/A7 使用 deepseek-v4-pro。A1–A7 已启用、采用人工复核模式。更新 DSL 会覆盖草稿，只有确定使用仓库版本时执行：

```bash
cd /opt/ai-recruiter/app
/opt/ai-recruiter/venv/bin/python deploy/provision_dify_local.py --sync-drafts --publish
/opt/ai-recruiter/venv/bin/python deploy/cloud/activate.py
docker compose --env-file backend/.env -f deploy/compose.yaml -f deploy/cloud/compose.yaml --profile web up -d
```

`activate.py` 设回云端 Docker 地址并启用人工复核策略。新环境首次安装模型还需 `--install-model`，待插件安装完成后运行 `--configure-model --publish`。

## 验证

本次整合：后端 SQLite 回归 395 通过、3 跳过；三端类型检查和 lint 通过；新版界面浏览器测试 6 项及 AI 流程 2 项通过。3 项跳过不计作通过；本轮没有重新执行 PostgreSQL 专用测试。

云端 A1–A7 真实 DeepSeek 测试通过（A5 三次采样，共 9 次模型调用）。四个公网 HTTPS 入口通过证书校验并返回 200；真实 A0 路由调用后创建 A3 任务，后台处理后停在待人工复核。报告位于 `test-results/dify-live-smoke.json` 和 `test-results/cloud-live-smoke.json`。

```bash
curl --fail http://127.0.0.1:8000/health/ready
docker ps --format 'table {{.Names}}\t{{.Status}}'
sudo journalctl -u caddy --since '10 minutes ago'
```

`deploy/cloud/smoke.py` 会新建明确标识的合成候选人并产生付费模型调用，仅手动运行。`backend/scripts/smoke_dify.py` 只发送合成资料，不写业务数据。
