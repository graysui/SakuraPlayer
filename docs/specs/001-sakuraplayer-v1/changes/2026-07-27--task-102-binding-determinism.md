# Change Specification: TASK-102 绑定与缓存根确定性边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-102 预审确认通用加密设置仓储已提供独立事务 CAS，但单一 115 binding 尚无
Schema，Cookie 密文版本和 binding `credential_version` 的原子关系、QR 会话寿命、换账号
冲突与缓存根并发也未冻结。直接实现可能形成双版本真相、覆盖重扫 Cookie，或在并发首次
绑定时创建多个远端根。本变更只补齐既有 AC-013 至 AC-016、AC-079 至 AC-082 的
确定性实施边界，不增加产品功能。

## ADDED

### 单例 binding 与单事务凭据版本

- `cloud115_binding` 使用固定 `singleton_key=true` 唯一约束，整表最多一行。
- Cookie 固定保存到 `encrypted_setting` 键 `cloud115.cookie`；其 `version` 是唯一凭据版本
  真相，binding `credential_version` 必须在同一 PostgreSQL 事务中镜像相同值。
- 所有 snapshot 写回先锁 binding 与 encrypted setting，并同时比较作用域起始版本；任一
  不一致即丢弃 snapshot，不更新 binding 状态。
- 同账号重新扫码允许原子轮换；不同账号不能覆盖现有 binding，必须先显式解绑。解绑有
  活动缓存任务时返回 `cloud115_rebind_has_active_jobs`。TASK-103 交付 cache_job 前通过只读
  guard 端口保留该边界。

### QR 会话

- QR token 和上游状态只存在于 API 进程内的有界内存 store，不入 PostgreSQL、日志、
  事件或响应；客户端取得随机 UUID，创建响应可携带用于展示的 QR PNG，后续状态响应
  不再重复 PNG。
- 会话固定 5 分钟、本地最多 8 个；创建时清除过期终态。超过容量返回
  `cloud115_qr_session_capacity`。重启后旧 UUID 视为不存在。
- `confirm` 只接受上游状态 `confirmed` 的未消费会话；成功消费后重复 confirm 返回
  `cloud115_qr_session_consumed`。不存在、未确认分别返回稳定错误。

### 缓存根

- `SakuraPlayer-Cache` 只在 115 顶层 CID `0` 的直接子级 find-or-create，不递归扫描。
- v1 单 API 进程以 async mutex 串行远端 find-or-create；数据库提交再使用固定 PostgreSQL
  advisory transaction lock 和行锁原子更新，不在网络等待期间持有数据库事务。
- 同名超过一个返回 `cloud115_directory_ambiguous`；不得任选、移动或删除。
- 已持久根明确不存在或 parent 不再为 `0` 时 binding 标记 `detached`，不追踪移动后的
  目录，不按名称自动把其他目录认作旧根。重新扫码可显式确保新的受管根。

## MODIFIED

- `EncryptedSettingRepository` 增加调用方事务内 CAS 原语；现有独立事务 API 行为不变。
- Cloud115 公共 REST 补齐 QR/binding 稳定错误响应；响应不返回 Cookie、account key、
  root CID 或上游 token。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| cloud115 binding Schema/repository | ADDED | HIGH |
| encrypted setting session CAS | MODIFIED | HIGH |
| QR store / binding API | ADDED | MEDIUM |
| OpenAPI / error codes / data model | MODIFIED | MEDIUM |

## Task Synchronization

本变更不创建独立任务；规格、契约、迁移、实现、测试、追踪元数据和交接全部进入
TASK-102 的同一中文提交。

## Testing Strategy

- Schema 测试固定单例、状态、版本和 secret 外键/键约束。
- PostgreSQL 集成覆盖重扫、并发 snapshot、解绑、回滚与 advisory lock。
- FakeCloud115 覆盖 QR 全状态、容量、根存在/缺失/移动/歧义和凭据三态。
- API/日志/数据库扫描证明 Cookie、QR token、account key 和 root CID 不进入公开响应。
