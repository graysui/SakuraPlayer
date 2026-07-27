# 后端基础与元数据 E2E 契约

**性质**: Phase 1 自动验收与进程边界验证契约

## 1. 范围

TASK-014 验证 TASK-001 至 TASK-013 已交付的后端能力及 AC-023、AC-058、AC-132 的
Phase 1 观察点。115 绑定/缓存/播放、Windows/HarmonyOS UI、客户端本地状态和真实
外部门禁不属于本套件。

前序任务的测试继续作为各 `[IMP]` 的逐项证据；本套件增加以下跨边界证据：

```text
empty PostgreSQL -> Alembic head -> bootstrap
  -> AVdb decrypt/import -> initial metadata queue -> core_ready
  -> catalog/search/ranking -> events/snapshot/diagnostics
```

## 2. 隔离与组合

- 每次测试创建唯一 PostgreSQL 数据库并在 `finally` 中终止连接、删除数据库。
- 行为 E2E 使用生产应用服务和仓储组合，不复制领域状态机或 SQL。
- 外部 HTTP 只在适配器已有的 `http_client`/port 构造参数注入 fake；禁止新增生产环境
  变量、provider URL 覆盖、DNS 劫持或付费/账号访问。
- Compose Final 验证真实 API/worker/scheduler/migrate/PostgreSQL 容器、健康、重启、
  ready 降级和资源清理。pytest 不启动重复进程树。

## 3. Fixture 矩阵

| 类别 | 必须覆盖 |
|---|---|
| AVdb | 合法加密包、六分类、重复 Release/来源、摘要不一致 |
| JavDB | 核心成功、429/不可用、结构变化、无可选凭据 |
| DMM/图片 | 成功与单源失败 warning，失败不回滚 core_ready |
| Actor Mapping/GFriends | 成功、XXE/非法结构、唯一与歧义匹配、最近成功回退 |
| AI | 成功或明确不可用、无付费真实请求、秘密不出现在报告 |
| 元数据 | 已持久化 metadata_timeout 后显式 retry，父 attempt 保持不可变 |
| 事件 | sequence/stream_version、断线跳号、REST snapshot 水位恢复 |

静态文件保存脱敏上游结构；429、超时和连接错误可以由确定性 fake handler 产生。

## 4. 证据归属

- TASK-007 继续拥有真实 600 秒硬截止、进程组终止和三槽 supervisor 的门禁证据。
- TASK-005/TASK-011/TASK-012 继续拥有规格规模容量、p95 和查询计划证据。
- TASK-014 不真实等待 600 秒，不重复 289,858 行或 100,000 别名性能基准。
- E2E 测试函数或参数 ID 必须包含验证的 `AC-xxx`，失败报告不得只显示模糊场景名。

## 5. Runner

`backend/tests/e2e` 全部标记 `integration`。Final 的 PostgreSQL pytest 命令必须同时
收集 `tests/integration` 和 `tests/e2e`；不得通过单独第二次 Compose 冒充 E2E 门禁。

任何 E2E 失败都会结束当前 Final 尝试。修复后必须重跑受影响的 Fast 与审计，再开始
新的 Final 尝试。

## 6. 安全

- 默认测试不读取真实凭据，不访问真实 115、JavDB 写操作或付费 AI。
- fixture、pytest node ID、异常、日志和快照不得包含完整磁力、Cookie、token、密码、
  API key、DSN 或完整签名 URL。
- 测试生成的 secret 和数据库只存在于隔离运行目录/数据库，结束后必须清理。
