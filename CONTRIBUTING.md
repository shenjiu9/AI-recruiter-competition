# 参与贡献

欢迎任何人参与 AI 招聘官系统。无需申请仓库成员资格：可以提交 Issue、参与 Discussions，或 Fork 后发起 Pull Request（PR）。功能、缺陷修复、文档、测试和交互改进都欢迎。

## 从哪里开始

1. 阅读 [README](README.md)、[交付任务与剩余范围](docs/04-delivery-plan.md) 和相关设计文档。
2. 在 Issues 搜索已有讨论。较大的功能或架构调整请先开 Issue，说明问题、方案和影响范围，避免重复开发。
3. Fork 本仓库，从上游 `main` 创建功能分支。PR 的目标分支默认选 `shenjiu9/AI-recruiter-competition:main`；针对尚未合并的功能，请先在对应 PR 讨论。

```bash
git clone https://github.com/<你的用户名>/AI-recruiter-competition.git
cd AI-recruiter-competition
git remote add upstream https://github.com/shenjiu9/AI-recruiter-competition.git
git fetch upstream
git switch -c feat/your-change upstream/main
```

## 开发与验证

- 前端：Node.js 22、pnpm 10.28.0。运行 `pnpm install --frozen-lockfile`，然后 `pnpm dev:hr`；默认 mock 模式不需要模型密钥。
- 后端：Python 3.12；创建自己的虚拟环境，按 [后端说明](backend/README.md) 安装依赖和运行测试。
- 真实 API、Docker 和 Dify 的配置见 [本机运行手册](docs/05-local-runbook.md)。请使用自己的环境、模型账号和合成资料，测试不需要连接维护者的云服务器。
- 按修改范围验证：前端使用 `pnpm typecheck`、`pnpm lint`、`pnpm build`，涉及交互时运行 `pnpm test:e2e`；后端在 `backend` 目录运行 `pytest -q`，并执行对应的格式、模块边界和迁移检查。
- PR 中写清实际执行的检查、结果，以及未验证部分。不要把未运行的测试写成通过。

## 提交 PR

```bash
git add <修改的文件>
git commit -m "fix: describe the change"
git push -u origin feat/your-change
```

在 GitHub 点击 **Compare & pull request**，填写 PR 模板。一个 PR 尽量解决一个明确问题；界面改动附截图，接口或数据结构变化说明兼容性及迁移方式。

维护者会审查改动、测试与讨论。首次外部贡献的 GitHub Actions 可能需要维护者批准运行；这不影响任何人提交 PR。根据反馈在同一分支继续提交即可更新 PR。

`main` 要求 PR 审查及讨论解决，禁止强制推送和删除；仓库管理员保留必要的维护权限。公开可见不等于拥有上游写权限，贡献者通过 Fork 和 PR 协作，合并由维护者决定。PR 合并不会自动更新云端演示环境。

## 提交内容与讨论

- 不提交 `.env`、API Key、登录口令、SSH 私钥、数据库备份、真实简历或个人资料；使用示例配置和合成数据。
- 不在公开 Issue、PR、截图或日志中贴出凭据。若发现凭据泄露，请使用仓库 Security 页面的私密漏洞报告入口。
- 尊重不同观点，讨论具体问题；避免人身攻击、骚扰和与项目无关的推广。
- 本贡献说明不新增或替代代码的许可证授权；如需明确的再分发或商业使用许可，请先与维护者确认。
