# Change Specification: TASK-104 离线执行与取消确定性边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-104 预审确认 TASK-103 已交付持久容量类别、来源提交端口和 `claim_token` 字段，但
提交调用前后的崩溃事实、`cloud115_submit_uncertain` 的持久状态、claim fencing 形状以及
取消与后续安全清理的任务边界仍未冻结。直接实现会造成旧 worker 写回、提交结果不确定后
自动重复扣配额，或 TASK-104 提前接管 TASK-107 的证明式删除。本变更只补齐 AC-084、
AC-086 至 AC-091、AC-097 的确定性实施边界，不增加产品功能。

## ADDED

### 提交派发事实与不确定状态

- CacheJob 新增 `submit_started_at`。worker 创建并持久化 `task_dir_cid` 后，在发出唯一一次
  `submit_offline` 前先提交 `submit_started_at`；只有该字段为空时才允许自动提交。
- 新增 `submit_uncertain` 状态：必须有 `task_dir_cid`、`submit_started_at`，不得有
  `remote_info_hash`，`failure_code` 固定为 `cloud115_submit_uncertain`。
- `submit_uncertain` 保留 running 容量、属于活动复用状态且阻止解绑；自动 worker 不再次
  领取或重新提交。管理员确认取消可触发一次只读对账；仍找不到时回到
  `submit_uncertain`，等待后续人工操作。
- 提交不确定对账使用 `page_size=1000` 从第一页读取到上游声明的最后一页，只按
  `task_cid == cache_job.task_dir_cid` 匹配。页码形状矛盾、超过 1000 页或同目录出现多个任务
  均视为 `cloud115_protocol_error`，不得猜测或重提。

### Claim fencing

- claim 的 `owner/token/expires_at` 必须同时为空或同时非空；每次首次领取或过期接管都生成
  新 token。
- 领取使用 `FOR UPDATE SKIP LOCKED`。续租、目录 CID、派发事实、remote info hash、进度、
  状态、错误和释放 claim 的所有写入都必须匹配 `id + owner + token + 未过期 lease`。
- TASK-104 worker 只领取 `submitting/offlining/cancelling`；`resolving` 由 TASK-105 消费，
  `cleaning` 由 TASK-107 消费，`submit_uncertain` 只由显式取消重新进入 `cancelling`。
- 瞬时 unavailable/rate-limit 保留当前状态与 claim，使用有界 lease 作为退避；确定性
  invalid/quota/offline-failed/protocol/source-unavailable 进入失败或待清理路径，不自动重跑。

### Disposition 映射

- 新建 running 返回 `started`，并只在该响应返回服务端当前时间加 60 秒的
  `wait_deadline`；该时间不落库、不创建 timer 或事件。
- 新建 queued 返回 `queued`；已有 ready 返回 `ready`；其他已有活动任务或同幂等键重放
  返回 `reused`。`queued/reused/ready` 的 deadline 均为空。
- 后端只发布状态事实。60 秒内是否自动导航、超时后是否仅提示和后台完成通知分别由客户端
  TASK-209/TASK-309 与事件通知 TASK-112 实现。

## MODIFIED

- `resolving -> cancelling` 和 `cancelling` 的持久原容量归属继续沿用 TASK-103 已冻结规则。
- queued 或尚未领取、尚未创建任务目录、尚未派发的 running 取消可在同一事务确认无远端
  副作用后终结；已领取但 mkdir 尚未落库的窗口属于可能存在远端副作用，必须保留 claim、
  登记确定性目录后进入 `cleaning`。已有任务目录或其他可能存在远端副作用时也只能进入
  `cleaning`。
- TASK-104 负责二次确认、状态竞争、远端 `cancel_offline(delete_source_files=False)` 和
  cancellation application service。TASK-107 负责目录归属证明、删除和最终
  `cleaned/cleanup_failed/detached`；TASK-112 的管理 API 只复用这些业务用例。
- TASK-104 的 worker 重启只恢复自己拥有的 claim/提交/轮询步骤；跨所有缓存阶段的启动总
  对账、持久事件、通知和 REST snapshot 仍由 TASK-112 负责。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| CacheJob Schema / 状态机 | MODIFIED | HIGH |
| claim / offline worker | ADDED | HIGH |
| cancellation service | ADDED | HIGH |
| play disposition / OpenAPI | MODIFIED | MEDIUM |
| TASK-107/TASK-112 ownership | MODIFIED | MEDIUM |

## Task Synchronization

本变更不创建或拆分正式任务。变更规格、迁移、实现、测试、TASK-104 状态、追踪矩阵和交接
进入 TASK-104 同一中文提交；TASK-107 和 TASK-112 只同步职责文字，不提前实现其功能。

## Testing Strategy

- 领域/Schema 测试覆盖 `submit_uncertain` 形状、claim 三元组、派发事实和 disposition。
- PostgreSQL 测试覆盖并发 `SKIP LOCKED`、过期接管、旧 token 拒写、queued 提升和取消竞态。
- FakeCloud115 覆盖提交成功、超时已受理、超时未找到、分页歧义、轮询完成/失败、取消
  not-found、瞬时失败和 Cookie snapshot；调用记录不得包含磁力正文。
- 60 秒测试只验证响应字段和后端状态不因时间经过而改变；客户端自动导航留给客户端任务。
