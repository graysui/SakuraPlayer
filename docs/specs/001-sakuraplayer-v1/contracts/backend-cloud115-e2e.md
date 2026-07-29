# 115 缓存播放后端 E2E 契约

**性质**: Phase 2 自动验收与跨边界组合契约

**边界变更**: [TASK-113 115 缓存播放后端 E2E 边界](../changes/2026-07-29--task-113-backend-e2e-boundaries.md)

## 1. 范围

TASK-113 验证 TASK-101 至 TASK-112 已交付的后端可观察切片，以及 AC-132 的 Phase 2 观察点。
前序任务的 Focused/Fast/Final 继续作为各 `[IMP]` 的逐项实现证据；本套件只增加以下组合证据：

```text
empty PostgreSQL -> Alembic head -> bootstrap -> QR binding/root
  -> source play request -> offline -> resolve/select -> ready
  -> original/HLS -> subtitle -> progress/heartbeat
  -> event/notification/snapshot -> ownership proof -> cleanup
```

Windows/HarmonyOS 页面、60 秒客户端倒计时、全屏等待、通知展示、自动播放决策、播放器菜单、
seek、内嵌轨道和本地字幕文件删除不属于本套件。真实 115 行为由 TASK-213 显式门禁验证。

## 2. 隔离与生产组合

- 每次测试创建唯一 PostgreSQL 数据库，从真实 Alembic head 迁移，并在 `finally` 定向删除。
- 使用生产 AuthService、BindingService、PlayRequestService、worker pipeline、播放/字幕/进度服务、
  EventLog、Notification 和 FastAPI composition；不得复制领域状态机或 SQL。
- Fake 只在现有 Cloud115Port 构造边界注入；禁止新增生产环境变量、测试路由或运行时后门。
- Compose Final 继续验证真实容器进程、Schema 门禁、启动恢复、健康、重启、ready 降级和资源清理；
  pytest E2E 不启动第二套进程树。

## 3. 状态化 Fake 模型

Fake 必须能够确定性表示并查询：

| 状态 | 最小字段/行为 |
|---|---|
| 凭据 | alive/expired/unavailable；Cookie 仅作为私有输入，不进入 repr |
| 目录 | cid、parent cid、name、存在/移动/删除状态 |
| 离线任务 | info hash、task cid、queued/running/completed/failed、文件定位 |
| 文件 | file id、parent cid、pickcode、大小、类型、blocked、字幕正文的不可打印句柄 |
| 播放能力 | original/HLS 结果与稳定故障；完整 URL 不进入可查询摘要或 repr |
| 删除 | 请求目标、验证父 CID、成功/失败、删除后的存在性 |

状态推进由测试显式调用；不得依赖真实 sleep、线程竞争或网络。现有脚本返回队列与
`FakeCloud115Call` 脱敏记录保持兼容。完整磁力只允许作为端口调用参数短暂存在，调用记录只保存摘要。

## 4. 场景与证据矩阵

| 场景 | 后端观察点 | 主要 AC |
|---|---|---|
| 扫码与主链 | binding/root、started、offlining、selection/ready、original/HLS、subtitle、progress、cleaned | AC-013..017, AC-035, AC-079..102, AC-107..113 |
| 容量与后台恢复 | 2 running/10 queued、复用、无 timer transition、started/ready notification、snapshot counts、无自动 session | AC-084..091, AC-115..118 |
| 安全与故障 | 账号/根/父目录变化、活跃 lease、cleanup failure/retry、startup recovery fencing | AC-081, AC-082, AC-094..098, AC-121, AC-122, AC-127..129 |
| 来源拒绝 | blocked/确定性 invalid 清除活动载荷并保持拒绝事实，普通失败不误拒绝 | AC-036 |
| 故障隔离 | 元数据/AI/GFriends 固定故障事实存在时，同一 core_ready 影片仍可完成 115 播放闭环 | AC-132 |

每个关键状态转换至少断言 PostgreSQL 与一个公开观察面（API、事件、通知或快照）。涉及远端副作用时
同时断言 Fake 状态。测试函数或参数 ID 必须包含对应 `AC-xxx`。

## 5. 60 秒证据边界

- 后端创建响应只证明 `started` 或 `queued` disposition。
- 可控时钟经过 60 秒不应写 CacheJob 状态、不应发布 timer 事件或把任务标为失败。
- queued 开始、后台 ready 和失败通过持久事件/通知/快照可恢复。
- ready 事务不得创建 PlaybackSession；只有后续显式播放会话 API 可以创建。
- 客户端何时退出等待、是否展示全屏、是否导航播放器由 TASK-209/309 和最终客户端 E2E 验证。

## 6. 安全与 Runner

- 默认测试不读取真实凭据，不访问真实 115、JavDB 写操作或付费 AI。
- fixture、repr、pytest node ID、异常、日志、数据库扫描和快照不得包含 Cookie、完整磁力、token、
  密码、API key、DSN、字幕正文或完整能力 URL。
- `backend/tests/e2e` 使用 `integration` marker，由唯一 Final PostgreSQL 步骤收集。任一失败都会结束
  当前 Final 尝试；修复后必须重新通过受影响 Fast 与审计，再开始新的 Final。
