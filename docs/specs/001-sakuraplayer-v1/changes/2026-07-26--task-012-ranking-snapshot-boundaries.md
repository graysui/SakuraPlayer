# Change Specification: TASK-012 排行榜快照确定性与执行边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-046、AC-069 至 AC-073 已要求 JavDB 本地排行榜快照、年度 TOP250、
priority 20 元数据联动和失败保留，但原 TASK-012 没有冻结 Ranking Schema
归属、scheduler 到 worker 的持久请求、四榜单上游映射、年度范围、current
唯一性、快照游标、MovieSummary 读取端口和稳定不可用 details。本变更补齐可执行
边界，不增加榜单类型或页面能力。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### 排行榜持久同步与查询协议

**Requirements**:

- REQ-CHG-095: TASK-012 自身交付 0012 迁移、Discovery ORM、
  `ranking_sync_request`、`ranking_snapshot` 和 `ranking_entry`。原 DoR 只要求
  设计和约束已由本变更冻结，不要求不存在的前序迁移。
- REQ-CHG-096: scheduler 每天 01:45 `Asia/Shanghai` 只持久入队目标；worker
  claim 后访问 JavDB。请求按 `(board, year, scheduled_for)` 幂等，使用 owner、
  token、lease 和 heartbeat fencing；同一 `(board, year)` 最多一个 queued/claimed
  请求。明确 failed 请求可由下一调度槽创建新请求，但不能修改旧失败事实。
- REQ-CHG-097: 每日目标固定为 `daily/weekly/monthly`、TOP250 总榜
  `(year=null)` 和 TOP250 当前年。TOP250 支持 2008 至服务器当前年；缺少成功
  current 的历史年份才入队一次。未配置凭据时不入队 TOP250，公开三榜不受影响。
- REQ-CHG-098: `daily/weekly/monthly` 固定请求 JavDB playback 榜
  `filter_by=all` 和同名 period。TOP250 先用单载荷加密凭据登录，再请求总榜或
  年度榜；每页 50、最多 5 页。HTTP/JSON 上限、登录 token、密码和上游正文不得
  进入日志或持久失败详情，默认测试只使用固定脱敏 fixture。
- REQ-CHG-099: provider 输出带原始正整数 rank 的规范化番号。缺失或非法番号
  单条跳过；重复番号只保留第一次出现并保留原始 rank，因此允许名次间隙。响应
  为空或校验后没有任何条目视为 `javdb_upstream_error`，不得激活空快照。
- REQ-CHG-100: 每个目标独立获取和激活。候选条目在短事务内完整写入后，旧
  current 变为 superseded，候选变为 current。数据库必须保证每个
  `(board, normalized_year)` 最多一个 current；失败请求不修改既有 current。
- REQ-CHG-101: `/rankings` 的 `year` 只允许与 `board=top250` 组合；省略 year
  表示 TOP250 总榜，显式 year 只允许 2008 至服务器当前年。其他组合、未来年份、
  畸形或跨榜单 cursor 返回 `validation_failed`。响应返回 TOP250 可选年份降序，
  非 TOP250 返回空列表。
- REQ-CHG-102: 排行榜 cursor 是版本化 Base64URL JSON，绑定 board、year、
  immutable snapshot ID 和最后一个可见原始 rank。current 在翻页期间切换时，
  后续页继续读取 cursor 指向的 superseded 快照；不得混合两个快照。
- REQ-CHG-103: 排行榜只输出存在 identified/manual AVdb 来源且
  `catalog_state=core_ready` 的影片，并通过 TASK-011 目录批量端口按输入顺序生成
  MovieSummary。发现上下文不得复制目录私有投影或直接读取未来 cache/playback 表。
- REQ-CHG-104: 排行榜命中的有来源非 core-ready 影片使用
  `ensure_ranking_priority` 幂等协调元数据任务：无 attempt 创建 priority 20；
  queued 且优先级大于 20 时提升；priority 10 保持；running 复用；failed 不自动
  重试；并发下仍只有一个活动 attempt。
- REQ-CHG-105: 从未有成功快照时返回 HTTP 503
  `ranking_snapshot_unavailable`，details.reason 只允许
  `credentials_not_configured/credentials_invalid/never_synced/sync_failed`，可选
  `last_error_code` 只能是稳定错误码。已有 current 时即使最近同步失败仍返回旧快照。
- REQ-CHG-106: Ranking API 需要管理员认证，页面请求期间不得访问 JavDB，响应
  使用 `Cache-Control: no-store`。普通数组、目录批量端口和 `limit` 均最多 100；
  已缓存排行榜 API 保持 NFR-001 的 p95 小于 500 ms。

**Acceptance Criteria**:

- [ ] 0012 从 0011 和空库升级成功，约束 current 唯一、活动请求唯一、状态形状、
  claim fencing、条目 rank/番号唯一和 downgrade 对称。
- [ ] scheduler 只入队，worker 可 claim、续租、崩溃恢复并独立完成或失败目标；
  01:45、历史一次性和无凭据跳过测试通过。
- [ ] 四榜单 fixture 覆盖成功、登录失败、上游失败、结构变化、空响应、重复和非法
  番号，失败不替换 current。
- [ ] API 覆盖认证、board/year、snapshot-bound cursor、rank 间隙、MovieSummary、
  priority 20 提升和结构化不可用原因。
- [ ] PostgreSQL 并发、迁移和已缓存查询性能通过，默认测试不访问真实 JavDB。

**Impact**: AC-046、AC-069 至 AC-073、TASK-012、OpenAPI、错误码、元数据与
目录发现端口、数据模型、架构、任务索引、追踪矩阵、scheduler/worker、迁移和测试；
Breaking: NO，排行榜客户端尚未实现。

## MODIFIED

### TASK-012 依赖与 Schema 归属

**Previous Behavior**: 任务要求 Ranking 迁移在开始前已确认，但没有任务拥有该
迁移；依赖也未声明实际复用的 TASK-011 MovieSummary 投影。

**New Behavior**: TASK-012 正式依赖已完成的 TASK-011，自身交付 0012、排名模型、
目录批量端口扩展和公开 API，并标记为跨 Catalog/Discovery 边界。

### 排行榜队列优先级

**Previous Behavior**: 只声明创建 priority 20，未说明已有 queued/running/failed
attempt。

**New Behavior**: 按 REQ-CHG-104 提升或复用，保持 AC-040 与 AC-072 同时成立。

### TOP250 与不可用响应

**Previous Behavior**: 年份适用范围和 503 details 未结构化，客户端无法稳定区分
未配置、凭据失效和从未同步。

**New Behavior**: 冻结 2008..当前年、总榜 null 语义和稳定 reason 枚举。

## REMOVED

无。

## Task Synchronization

本变更不创建独立 `TASK-CHG`。功能规格、架构、技术计划、OpenAPI、错误码、
provider/目录端口、数据模型、任务索引、TASK-012 和追踪矩阵在 TASK-012 同一中文
提交中同步；AC 映射保持不变。

## Testing Strategy

- SQLite 自包含测试覆盖 provider fixture、参数、游标、DTO、队列协调和失败保留。
- PostgreSQL 集成测试覆盖 0012、current/active 唯一、claim fencing、并发提升和查询。
- Final 使用隔离 Compose，验证迁移、API/worker/scheduler、重启恢复和秘密扫描；
  不访问真实 JavDB、115 或付费 AI。

## Rollback Plan

TASK-012 提交前可整体回退本变更和实现。提交后 Schema 只能用前向迁移修正，
不得单独回退公开 cursor、错误 reason 或持久请求语义。
