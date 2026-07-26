# Change Specification: TASK-011 目录查询与补全确定性边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-063 至 AC-068、AC-074 至 AC-078 已要求去重目录、组合筛选、全局搜索、补全入队、聚合详情和单一收藏，但原任务没有冻结多来源筛选相关性、去重排序键、游标绑定、Phase 1 可播放/进度端口、已有队列任务提升、失败任务展示、嵌套集合上限、`pg_trgm` 与收藏 Schema 归属。本变更补齐可执行边界，不增加新的页面或产品能力。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 2 |
| REMOVED | 0 |

## ADDED

### 确定性目录、搜索、详情与收藏协议

**Requirements**:

- REQ-CHG-084: TASK-011 交付 `0011_catalog_discovery` 迁移，拥有 `pg_trgm` 扩展、影片标题/演员姓名/别名 trigram 索引和 `favorite` 表。迁移不得提前建立 Phase 2 的 cache 或 playback 表；SQLite 自包含模型可忽略 PostgreSQL 专用扩展与 GIN 索引。
- REQ-CHG-085: 媒体库只输出至少一条活动 identified/manual AVdb 来源的 `core_ready` 影片。`categories` 内是 OR，`labels` 内是 AND；category、全部 label、website、size 和 playable 条件必须由同一来源同时满足，禁止把多条来源拼成不存在的资源组合。空数组等同未提供，重复值规范化去重，min 大于 max 返回 `validation_failed`。
- REQ-CHG-086: `publish_date_desc/asc` 使用满足当前来源筛选的 `MAX(resource_source.publish_date)`，null 永远最后，再以 movie ID 做稳定 tie-breaker；`number_asc` 使用规范化番号和 movie ID。影片与演员 cursor 是版本化 Base64URL JSON，绑定完整规范化查询、筛选、排序和 favorite 状态；格式错误、版本错误或跨查询复用返回 `validation_failed`。
- REQ-CHG-087: 目录/发现通过 [Catalog 与 Discovery 只读端口](../contracts/catalog-discovery-ports.md) 获取来源 availability 和影片 progress。TASK-011 的 Phase 1 默认 availability 为 `available`、progress 为 null，因此 `playable=true` 返回空集合、`playable=false` 返回尚未 ready 的匹配来源；TASK-103/105 和 TASK-111 后续只替换端口适配器，不改变公开 DTO。
- REQ-CHG-088: 全局搜索先尝试现有番号规范化器；规范化番号精确命中使用 B-tree 并排在影片组首位。其余影片标题、演员中日文名和权威别名使用 trigram/规范化包含搜索；同一歧义别名命中的全部演员都可返回，不套用 GFriends 的唯一匹配丢弃规则。`limit` 独立限制 movies、actors 和 pending_metadata 三组，每组最多 100。
- REQ-CHG-089: 番号精确命中 raw-only 影片时，数据库事务锁定影片和当前活动 attempt。queued attempt 原子改为 `priority=10, reason=manual_or_search`；running attempt 原样复用；没有任何 attempt 时创建 priority 10；最近 attempt 已 failed 时不得自动重试，返回 `state=failed` 和该 job ID。并发搜索不得产生重复活动 attempt。
- REQ-CHG-090: `favorite` 唯一键为 `(target_type,target_id)`，只接受可见 `core_ready` 影片或至少关联一部可见影片的演员。PUT/DELETE 都幂等；目标不可见返回 `resource_not_found`。`favorite=true` 过滤单一收藏集合，false 或省略表示不按收藏过滤；影片收藏保留当前影片排序，演员收藏按规范化展示名和 actor ID 稳定分页。
- REQ-CHG-091: 影片详情的演员、标签、剧照和来源，以及演员详情的别名、写真和关联 `core_ready` 影片，都使用确定性顺序且每个集合最多 100 项。详情仍返回总 source_count；v1 不在嵌套详情中新增独立分页端点。
- REQ-CHG-092: DTO 只发布持久目录图片的应用相对 URL、受验证 GFriends HTTPS URL 和安全来源字段。不得返回磁力 envelope、detail/preview URL、翻译 reservation、provider 快照证据、claim 字段、上游正文或完整文件系统路径。
- REQ-CHG-092A: 永久目录图片通过已认证 `GET /catalog/images/{image_id}` 读取。服务端只按数据库图片 ID 解析受管根内的 JPEG/PNG/WebP 相对路径，重新验证 resolved path 位于根目录且文件存在；响应不得暴露 relative_path、绝对路径或上游 source URL。
- REQ-CHG-093: PostgreSQL 真实规模 fixture 至少包含 289,858 条来源和可重复的 core-ready/actor 子集；分别测量媒体库/演员列表、番号精确搜索和标题/别名模糊搜索的 p95，并验证查询计划使用对应 B-tree/GIN 索引。性能目标沿用 NFR-001，不以 SQLite 计时代替。
- REQ-CHG-094: `/movies`、`/actors`、`/search` 和收藏写入在 OpenAPI 中声明认证、422 校验及适用的 404；所有普通数组显式 `maxItems: 100`。搜索 GET 的补全入队是幂等副作用，响应使用 `Cache-Control: no-store`。

**Acceptance Criteria**:

- [x] 多来源 fixture 证明所有来源条件由同一来源满足，稳定游标不能跨筛选/排序复用。
- [x] 0011 从 0010 和空库升级成功，PostgreSQL 含 pg_trgm、GIN/B-tree 索引和 favorite 唯一约束。
- [x] 搜索 queued 任务提升、running 复用、failed 不重试和并发单活动 attempt 全部通过。
- [x] Phase 1 空 availability/progress 端口、收藏幂等、core_ready 可见性和安全 DTO 测试通过。
- [x] 真实规模 PostgreSQL fixture 达到 NFR-001，普通及嵌套集合均不超过 100。

**Impact**: AC-063 至 AC-068、AC-074 至 AC-078、TASK-011、OpenAPI、错误码、数据模型、架构、任务索引、追踪矩阵、迁移、目录/发现服务和测试；Breaking: NO，客户端尚未实现。

## MODIFIED

### TASK-011 Schema 与跨上下文归属

**Previous Behavior**: `pg_trgm` 和游标被写成无人交付的 DoR；任务同时创建 catalog/discovery 文件却标记 `cross-boundary: false`。

**New Behavior**: TASK-011 自身交付 0011 Schema 并标记跨边界。目录与元数据拥有 core-ready 聚合读取，发现拥有搜索协调和收藏；Phase 2 availability/progress 只通过只读端口接入。

### 搜索失败与已有队列任务

**Previous Behavior**: 搜索只声明 queued/running 补全状态，未说明已有低优先级任务和失败历史。

**New Behavior**: queued 原子提升、running 复用、failed 显式返回且不自动重试，保持 AC-040 与 AC-066 同时成立。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| catalog/discovery read ports | ADDED | MEDIUM |
| 0011 Schema and indexes | ADDED | HIGH |
| catalog/search/favorite/image APIs | MODIFIED | HIGH |
| metadata queue promotion | MODIFIED | MEDIUM |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。功能规格、架构、OpenAPI、错误码、数据模型、端口契约、任务索引、TASK-011 和追踪矩阵在 TASK-011 同一中文提交中同步；AC 映射保持不变。

## Testing Strategy

- SQLite 自包含测试覆盖游标、组合筛选、DTO、搜索分组、空端口和收藏幂等。
- PostgreSQL 集成测试覆盖 0011、trigram、键集分页、queued 提升并发和 favorite 唯一约束。
- 289,858 来源 fixture 记录 p95 与 EXPLAIN 索引证据。
- Final 使用隔离 Compose，不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

TASK-011 提交前可整体回退本变更和实现。提交后只能通过前向迁移调整索引或公开查询语义，不得单独回退 OpenAPI、端口契约或 0011。
