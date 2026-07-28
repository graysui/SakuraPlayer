# SourceRejectionPort 契约

**性质**: 后端内部应用端口，不是公共 HTTP API

**所有者**: Resources 上下文

**调用方**: Cloud Cache 上下文；TASK-106 负责把明确的 115 确定性失败映射为本端口调用。

**确定性变更**: [TASK-106 来源拒绝确定性边界](../changes/2026-07-28--task-106-source-rejection-determinism.md)

## 1. 操作

```text
reject(
  website: string,
  external_post_id: int64,
  reason_code: stable_snake_case
) -> void
```

- 调用只携带来源网站、帖子 ID 和稳定原因码，不携带磁力、标题、上游正文或 115 原始错误对象。
- 来源不存在或已被拒绝时分别使用 `source_not_found`、幂等成功语义；格式错误使用 `validation_failed`。
- 只有明确失效、违规或无法离线可调用本端口。网络错误、限流、5xx、未知错误和提交不确定不得调用。
- v1 初始稳定 reason 只允许 `cloud115_source_unavailable` 与
  `cloud115_source_blocked`；普通远端下载失败不得调用。
- `SourceSubmissionPort.load_submission_ref(movie_id, source_id)` 只投影来源身份与可选的首次
  `rejection_reason_code`，即使来源已拒绝也可读取；它不得解密或返回磁力。Cache worker 每次
  领取先检查该 reason，以便前次拒绝后崩溃时补齐 CacheJob failed 与事件。

## 2. 事务不变量

1. Resources 按 `(website, external_post_id)` 获取与导入相同的事务锁。
2. 同一事务内清空活动来源的磁力 envelope，将来源标记为 `rejected`，并创建唯一拒绝记录。
3. 重复调用不新增记录、不恢复磁力，也不覆盖首次确定性拒绝事实。
4. 增量和全量导入在写影片或来源前检查拒绝记录；拒绝提交后不得重建来源或磁力。
5. Cache 客户必须先提交本端口，再在独立 claim-fenced 事务提交 CacheJob failed 与唯一事件；
   两步之间崩溃时，来源身份读取和本端口重复调用必须允许重试收敛。

## 3. 安全边界

- `source_rejection` 只保存 `website`、`external_post_id`、`reason_code`、拒绝时间和可选 Release 游标。
- 端口参数、异常、日志、事件和测试快照均不得包含磁力、可还原摘要或上游响应正文。
- 默认测试使用 Resources fixture 或 Fake 调用方，不访问真实 115。
