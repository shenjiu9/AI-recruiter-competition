# 前端

AI 招聘官系统的前端 monorepo：3 个可独立构建、独立部署的应用，共用 9 个基础包。架构依据 [详细实现文档第 8 节](../docs/03-implementation-design.md)。界面使用定制 Ant Design 5 与 Ant Design Mobile：深色侧栏、浅色卡片、青绿色品牌、轻量轨道装饰，保留证据高亮和业务状态语义。

## 快速开始

```bash
pnpm install
pnpm dev:hr          # HR Web       http://localhost:5173
pnpm dev:biz         # 飞书内 H5     http://localhost:5174
pnpm dev:candidate   # 候选人 H5     http://localhost:5175
pnpm typecheck && pnpm lint && pnpm build
```

默认使用内存 mock 数据，不需要后端。接后端时在各应用目录下建 `.env.local`：

```
VITE_USE_MOCK=false
VITE_API_BASE_URL=https://recruiter.example.com
```

开发服务器会把 `/api` 代理到 `http://localhost:8000`。演示开关：URL 加 `?theme=dark` 强制深色模式，加 `?degraded=1` 查看 AI 降级横幅。

## 目录

```
frontend/
├── apps/
│   ├── hr-web/         HR 端（React + Ant Design 5）
│   ├── biz-h5/         飞书内 H5：业务方待办、候选人精简视图、面评（antd-mobile）
│   └── candidate-h5/   候选人端：授权、会话、选面试时间（antd-mobile）
└── packages/
    ├── domain/         领域类型、枚举文案、格式化、查询键工厂
    ├── api-client/     ApiClient 接口；HTTP 实现与内存 mock 实现；幂等键；统一错误
    ├── auth/           飞书 SSO、飞书 H5 免登、候选人签名链接
    ├── permissions/    权限判断 hooks 与 <Can>（只控制显示，校验在后端）
    ├── realtime/       SSE 订阅与轮询降级
    ├── telemetry/      埋点（PRD 21.2），不含个人信息
    ├── i18n/           文案；首期简体中文
    ├── ui-kit/         设计 token、antd 主题、业务组件
    └── mobile-ui/      antd-mobile 主题变量与移动端组件
```

## 已实现的页面

| 应用 | 页面 | 路由 |
| --- | --- | --- |
| hr-web | HR 工作台 WB-01：AI 简报、分诊队列 + 决策卡（键盘 J/K/Enter/D/1–3）、转人工、异常、岗位健康、AI 动态（撤销 / 纠正） | `/workbench` |
| hr-web | 候选人详情 CD-02：投递横条、评估与简历并排（证据点击定位高亮）、会话接管与交还、投递记录、操作记录 | `/candidates/:id` |
| hr-web | 人才库 CD-01 | `/candidates` |
| hr-web | 岗位列表 JB-01、岗位详情 JB-02（漏斗、候选人、画像与知识库、暂停 / 恢复 / 关闭） | `/positions`、`/positions/:id` |
| hr-web | 招聘需求列表 RQ-01、发起需求 RQ-02（AI 一句话填表、来源标签、待决定项、AI 预检、审批链预览） | `/requisitions`、`/requisitions/new` |
| hr-web | 面试日程 IV-01 | `/interviews` |
| hr-web | 自动化策略 ST-01（硬性上限不可选） | `/settings/automation` |
| biz-h5 | 业务待办 BZ-01（卡片内直接操作）、候选人精简视图 BZ-02、面评填写 | `/`、`/brief/:appId`、`/feedback/:appId` |
| candidate-h5 | AI 身份说明 → 授权 → 会话；会话内选面试时间；转人工 | `/?t=<签名令牌>` |

渠道、数据洞察为第二期，路由已占位。

## 设计 token

定义在 `packages/ui-kit/src/theme/tokens.ts`（antd 主题）、`packages/ui-kit/src/workspace.css`（浅色变量与共享布局）和 `packages/ui-kit/src/styles.css`（深色基础变量与证据组件），改动需同步；移动端由 `packages/mobile-ui/src/mobile.css` 与 `refresh.css` 提供。

| 名称 | 用途 | 浅色 | 深色 |
| --- | --- | --- | --- |
| 墨 | 正文 | #20343B | #E6EAF0 |
| 纸 | 页面背景 | #F3F6F6 | #13171D |
| 品牌 | 主按钮、选中 | #16776B | #8FA8D9 |
| 批注黄 | 只用于证据高亮 | #F5D76E 55% | #D6B548 32% |
| AI 青 | 标记 AI 产出 | #16776B | #6FC3CC |
| 成功 / 警告 / 危险 | 语义 | #2E7D4F / #A86200 / #B3362F | #6BC28D / #E0A94F / #EE8A82 |

字体使用系统中文无衬线回退，数字统一等宽；字号按信息层级区分，控件高度 40px，控件与面板圆角以 10 / 16px 为主；减少动效模式下关闭装饰动画。

## 2026-11 界面更新

- 登录页、HR 导航、真实数据工作台、AI 任务、录用与面试共享组件、自动化设置统一视觉。顶部搜索跳转候选人查询，消息入口展开审批消息。
- 业务 H5 增加固定底部导航；候选人端增加分区入口和区分发送者的会话气泡。权限、授权、幂等重试与人工复核逻辑继续使用现有 API。
- 自动化设置支持按岗位名称搜索选择；未选对象时显示引导，避免初次打开即请求空岗位 ID。
- `workspace.spec.ts` 覆盖真实统计、搜索与消息入口、390px 业务导航和策略选择；原有业务流程继续由完整 E2E 套件回归。
- 本地容器运行方式见 [运行手册](../docs/05-local-runbook.md)。渠道、洞察及未配置外部服务仍保留原有边界。

## 界面规范补充

本轮界面优化参考了三个 UI/UX skill：Anthropic `frontend-design`（克制、只在一处用力、结构即信息）、`ui-ux-pro-max`（可访问性、触控、响应式、表单反馈等优先级清单）、Vercel `web-interface-guidelines`（代码级检查：焦点、`aria-label`、`text-wrap`、`color-scheme`、`Intl` 格式化等）。落到本项目的约定：

- **导航**：保留青绿色工作空间侧栏和管理区，每个入口用不同图标；二期模块显示“二期”标记。小于 992px 时侧栏收进左侧抽屉；顶部 AI 按钮进入任务与复核页。
- **状态**：列表中的状态用 `.rc-status[data-tone]`（文字 + 小圆点，空心表示结束或驳回），不只靠颜色。
- **移动端**：antd-mobile 变量用 `:root:root` 覆盖，保证 H5 使用定制青绿色；按钮按下有轻微缩放，成对的次要操作等宽并排；保留底部导航和新版登录页。
- **窄屏表格**：HR Web 在窄屏下表格横向滚动，不把中文挤成一字一行。
- **空消息不占位**：没有审批与交接消息时默认不渲染消息条；点击消息中心后可主动展开并查看空状态。

## 约定

- **依赖边界**：`app → pages → features → packages`，功能切片之间不得互相引用，由 `eslint-plugin-boundaries` 强制（见根目录 `eslint.config.js`）。
- **数据**：服务端数据全部走 TanStack Query，查询键来自 `@recruiter/domain` 的 `qk`；所有请求经 `@recruiter/api-client`，组件不直接 `fetch`。
- **写操作**：一律带幂等键（`useIdempotencyKey`，重复提交复用同一个键）和对象 `expectedVersion`；409 版本冲突给出“已被修改”提示并刷新。
- **可访问性**：把握度、健康度、评估结论都用“形状或图标 + 文字 + 颜色”表达；所有操作可用键盘完成；移动端触控目标 ≥ 44px。
- **文案**：按钮以动词开头写清结果；错误说清发生了什么和怎么办；不用“智能”“赋能”。

## 验证状态

初始前端提交仅使用类型桩检查；后端首批联调已安装真实依赖并加入锁文件，修复移动端事件回调类型和不规则空格问题。当前检查命令为 `pnpm typecheck && pnpm lint && pnpm build`。

招聘需求的分页列表、详情、编辑/保存草稿、提交/撤回、HR 审批及业务 H5 审批/驳回已接真实 API。真实模式启动与开发登录见 [后端说明](../backend/README.md)。其他模块的真实 API 仍按 [交付任务](../docs/04-delivery-plan.md) 分批建设；默认 mock 可以继续演示原界面。

`pnpm test:e2e` 会启动隔离测试 API 和 HR/业务前端，用真实 HTTP 验证草稿恢复、提交、驳回、重提、三级审批，以及 AI 未配置时保留手工输入的降级流程。测试会话不会写入你的业务数据库。
