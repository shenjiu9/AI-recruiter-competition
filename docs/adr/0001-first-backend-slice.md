# ADR 0001：首批后端纵向切片

状态：首批实现记录，不变更 PRD 业务目标。

1. 采用详细设计的模块化单体目录，bootstrap 唯一装配 SQLAlchemy 仓储、组织门面、加密与事务。业务状态机/预检为纯函数。暂时只有 org、requisition 和平台持久化，后续按任务表加入其他模块。
2. 保留前端已有 camelCase 响应 DTO，写命令版本字段遵循 `expected_version`。招聘需求列表改为服务端分页，旧 `listRequisitions()` 是最多 100 条的过渡兼容接口；当前列表页面使用 `requisitionPage()`，无截断问题。全量 OpenAPI 客户端生成另批实施。
3. 草稿编辑加提交支持同一 POST 内原子完成，避免前端先 PATCH 成功、提交失败后产生隐含的新版本。失败时字段更新、事件、审计及幂等记录全部回滚。
4. 使用开发数据库目录与显式开发登录进行联调，不模拟飞书 OAuth 成功。开发开关默认关闭，非 development 环境拒绝启用，token 校验后从数据库加载最新用户状态。
5. 需求完整表单和审批历史以 AES-GCM 密文存储，状态/版本/部门用于索引；避免尚未落地薪资独立表时明文存储薪资。后续查询投影和字段级授权继续按 PRD 补齐。加密 key 存环境变量仅用于开发，生产由 KMS 适配。
6. Windows 的 WSL 启用要求重启。为继续联调，SQLite schema translation 只用于快速测试和本地临时运行；PostgreSQL CAS、并发幂等、审计触发器由独立 PostgreSQL 测试验证，不能用 SQLite 测试替代。
7. 事件表目前只承担事务 outbox 持久化；没有 worker，不声称已投递/消费。岗位生成和 worker/inbox 按后续批次交付。
