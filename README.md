# AI 招聘官系统

AI 招聘官系统的需求、MVP 规划与详细实现设计。三份文档从上到下逐层细化：PRD 定义要做什么，MVP 规划定义先做哪一段、用什么技术，详细实现文档定义模块、函数与工程规范。

| 文档 | 内容 | 适合谁读 |
| --- | --- | --- |
| [01 · PRD V3.2](docs/01-prd-v3.2.md) | 完整业务需求：角色权限、页面、全局规则、各模块需求与验收标准、AI 实现方案、数据字典、集成、非功能需求、上线计划 | 产品、设计、研发、测试、业务 |
| [02 · MVP 实现规划](docs/02-mvp-plan.md) | MVP 范围与取舍、总体架构、技术栈、工程结构、数据模型、核心引擎、AI 组件、外部集成、页面、迭代计划与风险 | 产品负责人、技术负责人 |
| [03 · 详细实现文档](docs/03-implementation-design.md) | 分层与模块地图、模块内部结构规范、全部公开函数清单（后端与前端）、接口与事件契约、高可用与可扩展设计、开发规范、部署运维 | 全体研发 |

## 代码

| 目录 | 内容 |
| --- | --- |
| [frontend/](frontend/README.md) | 前端 monorepo（pnpm + Turborepo）：HR Web、飞书内 H5、候选人 H5，以及共享的领域、接口、主题与组件包 |
| [backend/](backend/README.md) | 后端基础与招聘需求首批流程：草稿、预检、审批、权限、幂等、审计、迁移与测试 |
| [deploy/](deploy/compose.yaml) | 本地 Docker Compose：PostgreSQL、Redis、API、HR 与业务 H5 |
| [交付任务](docs/04-delivery-plan.md) | 后端、联调、测试的分批任务与剩余范围 |

```bash
pnpm install
pnpm dev:hr   # 默认使用 mock 数据，无需后端
```

## 约定

- 三份文档冲突时：业务规则以 PRD 为准；实现范围以 MVP 规划为准；模块边界、函数签名与工程规范以详细实现文档为准。
- 技术栈：Python 3.12 + FastAPI、PostgreSQL、Redis、Dify、React + Ant Design；集成飞书、腾讯会议、短信服务。
- 图表在 `docs/images/` 下，以图片形式嵌入文档。

## 说明

- PRD 由纯文本整理为 Markdown，表格按原文逐格还原，原文每一行都已核对保留。
- 修改文档时请同步更新对应章节的交叉引用（如“PRD 17.10”）。
