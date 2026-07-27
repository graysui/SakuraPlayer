# SourceSubmissionPort 契约

**性质**: 后端内部应用端口，不是公共 HTTP API

**所有者**: Resources 上下文

**调用方**: Cloud Cache 上下文

**确定性边界**: [TASK-103 缓存容量与幂等](../changes/2026-07-27--task-103-cache-capacity-idempotency.md)

## 1. 操作

```text
validate_for_play(session, movie_id, source_id) -> SourceSubmissionRef
load_submission_payload(movie_id, source_id) -> SourceSubmissionPayload
```

- `validate_for_play` 在调用方现有事务中锁定来源，只接受属于指定 movie 的
  `identified/manual` AVdb source，且磁力 envelope 必须完整、未被拒绝。
- `SourceSubmissionRef` 只包含 `source_id/website/external_post_id`，不包含磁力、上游正文、
  URL 或密文。
- `load_submission_payload` 由 TASK-104 在任务目录创建后调用；它重新验证同一来源并只在
  调用作用域解密，返回上述引用和 `repr=False` 的 magnet。
- missing、跨影片、pending 或未知来源返回 `resource_not_found`；rejected 或缺少有效磁力
  返回 `source_permanently_unavailable`。错误不披露来源是否属于其他影片。

## 2. 事务与并发

1. `validate_for_play` 与 CacheJob 创建使用同一 SQLAlchemy Session 和 PostgreSQL 事务。
2. 来源锁与 Resources 导入/拒绝使用相同来源行，创建事务提交前不得被并发拒绝。
3. `load_submission_payload` 每次重新读取当前事实；被拒绝后不得使用旧 envelope。
4. 本端口不创建 CacheJob、不计容量、不调用 115，也不修改来源状态。

## 3. 安全边界

- Cloud Cache 不直接读取 `resource_source` 表或调用 `SecretCipher`。
- magnet 明文、密文、nonce、key ID 和可还原摘要不得进入 DTO repr、日志、事件、异常、
  API 响应或测试快照。
- 默认测试使用加密 fixture，不访问真实 115。
