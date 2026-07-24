# SakuraPlayer v1 稳定错误码

**版本**: 1.1.0

**适用契约**: REST、WebSocket、Windows、HarmonyOS

## 1. 错误结构

```json
{
  "code": "cloud115_credentials_expired",
  "message": "115 credentials are expired",
  "details": {"binding_status": "expired"},
  "request_id": "01J..."
}
```

- `code` 是客户端分支依据，在 v1 内不可改变语义。
- `message` 是安全的后端摘要，不是最终中文文案；客户端按 `code` 本地化。
- `details` 只能包含安全的字段、状态和重试提示。
- 禁止包含 Cookie、完整磁力、AI key、Bearer/刷新令牌、完整签名 URL、115 上游响应正文。

## 2. 通用错误

| HTTP | code | 客户端行为 |
|---:|---|---|
| 400 | `invalid_request` | 标记请求无效，不自动重试 |
| 401 | `authentication_required` | 尝试一次 refresh；失败后回登录页 |
| 401 | `session_revoked` | 清除本机令牌和字幕缓存 |
| 403 | `operation_forbidden` | 显示无权或状态不允许 |
| 404 | `resource_not_found` | 返回上一页并允许刷新 |
| 409 | `state_conflict` | 拉取最新 REST 快照 |
| 409 | `idempotency_conflict` | 使用原请求结果或更换幂等键 |
| 422 | `validation_failed` | 标记字段错误 |
| 429 | `rate_limited` | 使用 `Retry-After`，不连续重放 |
| 500 | `internal_error` | 显示 request ID，不暴露异常 |
| 503 | `service_unavailable` | 保留现有页面数据并允许重试 |

## 3. 初始化与运行配置

| HTTP/位置 | code | 语义/客户端行为 |
|---|---|---|
| 401 | `bootstrap_token_invalid` | 初始化口令缺失或错误，不创建管理员；不得提示哪一部分错误 |
| 409 | `bootstrap_already_completed` | 管理员已存在，初始化入口永久关闭 |
| 启动 | `startup_configuration_invalid` | 必需配置或 secret 缺失、格式错误或密钥复用；进程拒绝启动 |

## 4. AVdb、发现与元数据

| HTTP/位置 | code | 语义 |
|---|---|---|
| 409 | `avdb_release_already_imported` | 同一 Release 已完成，幂等成功 |
| 422 | `avdb_asset_invalid` | 资产名、manifest 或内层格式不合法 |
| 422 | `avdb_asset_digest_mismatch` | 主备或下载摘要不匹配，停止导入 |
| 422 | `avdb_decryption_failed` | GCM 认证或解密失败 |
| 404 | `source_not_found` | AVdb 来源不存在或已拒绝 |
| 409 | `source_rejected` | 来源有永久拒绝标记，不能重新提交 |
| 409 | `source_already_identified` | 待识别资源已关联影片 |
| 409 | `movie_merge_conflict` | 合并会违反规范化番号或关系约束 |
| 404 | `metadata_job_not_found` | 元数据任务不存在 |
| 409 | `metadata_job_not_failed` | 只有失败任务可手动完整重试 |
| 409 | `metadata_job_no_retryable_enrichment` | warning 任务没有所选的失败/缺失可选阶段 |
| 409 | `metadata_job_already_active` | 同一番号已有 queued/running 任务 |
| 504 | `metadata_timeout` | 单影片任务达到 600 秒并已强制终止 |
| 502 | `javdb_upstream_error` | JavDB 临时失败 |
| 401 | `javdb_credentials_invalid` | 可选 JavDB 凭据失效 |
| 502 | `dmm_upstream_error` | DMM 富化失败，不隐藏核心影片 |
| 502 | `gfriends_upstream_error` | GFriends 索引/图片失败，不隐藏核心影片 |
| 502 | `translation_upstream_error` | AI 翻译失败，不隐藏核心影片 |
| 任务 | `translation_guardrail_failed` | AI 改写 protected 字段或返回非法结构，拒绝译文并保留原文 |
| 503 | `ranking_snapshot_unavailable` | 所选榜单/年份从未有成功快照；details 说明凭据未配置或同步尚未成功 |

## 5. 115 与缓存

| HTTP/位置 | code | 语义/客户端行为 |
|---|---|---|
| 409 | `cloud115_binding_exists` | 已有活动单账号绑定 |
| 422 | `cloud115_credentials_expired` | 明确提示重新扫码，不当作播放失败 |
| 503 | `cloud115_unavailable` | 上游暂不可用，不把 Cookie 标过期 |
| 429 | `cloud115_rate_limited` | 服从 `Retry-After` |
| 404 | `cloud115_directory_not_found` | 根或任务目录不存在 |
| 409 | `cloud115_rebind_has_active_jobs` | 有活动任务时禁止重绑 |
| 409 | `cache_queue_full` | 固定 10 个排队任务已满，提示切换已缓存资源或稍后再试 |
| 404 | `cache_job_not_found` | 缓存任务不存在 |
| 409 | `cache_job_not_ready` | 尚不能创建播放会话 |
| 409 | `cache_media_selection_required` | 多个候选需要用户选择 |
| 409 | `cache_cancel_confirmation_required` | 客户端必须完成二次确认后重提 |
| 409 | `cache_active_lease` | 正在播放，拒绝立即清理 |
| 409 | `cache_ownership_mismatch` | 受管目录证明不成立，标记 detached，不删除 |
| 502 | `cloud115_offline_failed` | 115 明确离线失败 |
| 任务 | `cloud115_submit_uncertain` | 离线提交结果无法确认；禁止自动重复提交，等待人工重新操作 |
| 422 | `source_permanently_unavailable` | 失效/违规/无法离线；创建拒绝标记 |
| 500 | `cache_cleanup_failed` | 删除未确认成功，容量不释放 |

## 6. 播放与字幕

| HTTP | code | 语义/客户端行为 |
|---:|---|---|
| 401 | `playback_signature_invalid` | 重新创建播放会话 |
| 401 | `playback_signature_expired` | 重新创建播放会话 |
| 401 | `playback_session_revoked` | 登录态已撤销，退出播放器 |
| 403 | `playback_user_agent_mismatch` | 固定平台 UA 配置错误，阻断播放 |
| 409 | `playback_media_detached` | 远端文件不再属于受管任务 |
| 404 | `playback_media_not_found` | 远端视频不存在 |
| 422 | `cloud115_original_unavailable` | 原画不可用，可显示“兼容播放” |
| 422 | `cloud115_hls_membership_required` | HLS 需要会员；不提示重新登录 |
| 503 | `cloud115_hls_not_ready` | HLS 未转码完成，可继续尝试原画 |
| 502 | `cloud115_hls_unavailable` | 没有可用 HLS variant |
| 404 | `subtitle_not_found` | 忽略该字幕，视频继续播放 |
| 413 | `subtitle_too_large` | 不下载该字幕，视频继续播放 |
| 422 | `subtitle_format_unsupported` | 不加载该字幕，视频继续播放 |
| 409 | `progress_version_conflict` | 客户端拉取最新影片进度后继续 |

## 7. WebSocket 关闭码

| close code | 含义 | 客户端动作 |
|---:|---|---|
| 4401 | 未认证或访问令牌过期 | refresh 后重连 |
| 4403 | 会话已撤销 | 退出登录并清理本地字幕 |
| 4409 | `after_event_id` 过旧 | 拉 REST 快照，再无游标重连 |
| 4429 | 重连过快 | 指数退避，最大 30 秒 |
| 4500 | 服务端异常 | 保留页面，拉 REST 快照并退避 |

## 8. 兼容性规则

- 可以新增错误码，但不得把已有 code 改成另一语义。
- 可以向 `details` 增加可选字段，不能让客户端依赖未声明的自由文本。
- HTTP 状态可在修复协议错误时调整，但客户端的首要分支依据始终是 `code`。
