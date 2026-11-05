# 前端

AI 招聘官系统的前端 monorepo：3 个可独立构建、独立部署的应用，共用 9 个基础包。架构依据 [详细实现文档第 8 节](../docs/03-implementation-design.md)，视觉与交互依据 UI/UX 设计计划（冷静、可信、高信息密度；决策卡与证据高亮是唯一醒目的元素）。

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

定义在 `packages/ui-kit/src/theme/tokens.ts`（antd 主题）和 `packages/ui-kit/src/styles.css`（CSS 变量），两处需同步；移动端在 `packages/mobile-ui/src/mobile.css`。

| 名称 | 用途 | 浅色 | 深色 |
| --- | --- | --- | --- |
| 墨 | 正文 | #1C2533 | #E6EAF0 |
| 纸 | 页面背景 | #F5F6F8 | #13171D |
| 藏青 | 品牌、主按钮、选中 | #24427A | #8FA8D9 |
| 批注黄 | 只用于证据高亮 | #F5D76E 55% | #D6B548 32% |
| AI 青 | 标记 AI 产出 | #1D6F7A | #6FC3CC |
| 成功 / 警告 / 危险 | 语义 | #2E7D4F / #A86200 / #B3362F | #6BC28D / #E0A94F / #EE8A82 |

字体 HarmonyOS Sans SC，两个字重（400 / 500），数字统一等宽；字号 12 / 14 / 16 / 20 / 24 / 30；圆角按层级 4 / 8 / 12；阴影两级；减少动效模式下关闭动画。

## 约定

- **依赖边界**：`app → pages → features → packages`，功能切片之间不得互相引用，由 `eslint-plugin-boundaries` 强制（见根目录 `eslint.config.js`）。
- **数据**：服务端数据全部走 TanStack Query，查询键来自 `@recruiter/domain` 的 `qk`；所有请求经 `@recruiter/api-client`，组件不直接 `fetch`。
- **写操作**：一律带幂等键（`useIdempotencyKey`，重复提交复用同一个键）和对象 `expectedVersion`；409 版本冲突给出“已被修改”提示并刷新。
- **可访问性**：把握度、健康度、评估结论都用“形状或图标 + 文字 + 颜色”表达；所有操作可用键盘完成；移动端触控目标 ≥ 44px。
- **文案**：按钮以动词开头写清结果；错误说清发生了什么和怎么办；不用“智能”“赋能”。

## 验证状态

本次提交在不能访问 npm 仓库的环境中完成：已用 TypeScript 对全部源码做过类型检查（第三方库用类型桩代替），但还没有实际安装依赖、构建和在浏览器中运行。第一次拉取后请执行 `pnpm install && pnpm typecheck && pnpm build`，CI（`.github/workflows/frontend.yml`）也会做同样的检查。
