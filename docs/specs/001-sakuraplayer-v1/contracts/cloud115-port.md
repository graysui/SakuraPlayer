# Cloud115Port 契约

**性质**: 后端内部端口，不是公共 HTTP API

**参考实现**: `avmedia/sakuramediabe/src/lib/cloud115`

## 1. 目标

领域层只依赖本契约，不依赖 115 非官方字段、errno、加密细节或 httpx。适配器负责把上游响应转换为稳定类型和错误码，并在每次调用结束时安全回写最新 Cookie 快照。

## 2. 端口操作

| 操作 | 输入 | 输出 | 失败 |
|---|---|---|---|
| `create_qr_session` | 无 | QR token + PNG bytes | unavailable/protocol |
| `poll_qr_session` | QR token | waiting/scanned/confirmed/expired/canceled | unavailable |
| `finish_qr_session` | token + 固定 app | account key + cookie snapshot | expired/protocol |
| `probe_credentials` | encrypted binding | alive/expired/unavailable + new snapshot | protocol |
| `find_or_create_directory` | parent CID + server-generated name | CID | auth/not_found/rate_limited |
| `directory_info` | CID | CID、parent、路径 | auth/not_found |
| `submit_offline` | magnet + task CID | remote task ID | invalid/auth/quota/rate_limited/uncertain |
| `list_offline_tasks` | page cursor | task snapshots | auth/unavailable |
| `cancel_offline` | remote task ID | confirmed cancellation | not_found/unavailable |
| `list_files_recursive` | task CID | async file stream | auth/not_found/rate_limited |
| `resolve_original` | pickcode + fixed UA | URL + expiry | auth/not_found/rate_limited |
| `resolve_hls` | pickcode + fixed UA | ordered variants | membership/not_ready/not_video |
| `download_small_file` | pickcode + fixed UA + byte limit | bytes | too_large/not_found/auth |
| `delete_managed_entries` | file IDs + verified parent CID | confirmed deletion | ownership/not_found/unavailable |

## 3. 稳定类型

```text
CloudCredentialStatus = alive | expired | unavailable
QrStatus = waiting | scanned | confirmed | expired | canceled
OfflineStatus = queued | running | completed | failed

RemoteFile {
  file_id, parent_cid, name, size_bytes,
  pickcode, sha1?, is_directory, is_video?,
  duration_seconds?, blocked?
}

OriginalUrl {
  url, expires_at, pickcode, file_size, user_agent
}

HlsVariant {
  url, bandwidth, resolution, label, user_agent
}
```

短期 `url` 类型只能存在于适配器调用栈和 `302` 响应构造中，不得进入 repository、事件或日志。

## 4. Cookie 并发规则

1. 创建适配器时读取 `credential_version` 和解密 Cookie。
2. 适配器合并响应中的 `Set-Cookie`。
3. 关闭时只在数据库版本仍等于原版本时 CAS 写回新密文并递增版本。
4. CAS 失败表示管理员重新扫码或另一请求先更新；丢弃旧快照，不覆盖新凭据。
5. `unavailable` 不得把绑定状态改成 `expired`。

## 5. 离线提交不确定性

若提交请求超时，不能立即用相同磁力重提。调用方先使用任务 CID、远端任务列表和可用 remote ID 对账：

- 找到匹配任务：记录 remote ID，继续 `offlining`。
- 明确未受理：保持可观察失败，由管理员重新点击或重试产品操作。
- 无法确认：标记 `cloud115_submit_uncertain`，不自动重复扣配额。

v1 不对影片元数据任务做自动重试；115 内部轮询不是“元数据重试”，其状态机独立。

## 6. 安全删除前置条件

调用 `delete_managed_entries` 之前，应用服务必须提供并验证：

```text
binding.account_key == cache_job.account_key
binding.cache_root_cid == cache_job.cache_root_cid
directory_info(task_dir_cid).parent_id == cache_root_cid
cache_job.task_dir_cid == requested_task_dir_cid
remote_file.parent_cid 位于 task_dir_cid 子树
database owner == cache_job.id
```

任一条件不成立：不调用 115 删除，任务进入 `detached` 或 `cleanup_failed`。目录不存在可视为已清理，但必须由明确 not-found 响应证明。

## 7. User-Agent 与播放

- Windows 固定 UA 和 HarmonyOS 固定 UA 分别由公共契约常量定义。
- `resolve_original` 的参数 UA 必须与播放器后续 Range GET 完全一致。
- `resolve_hls` 的 master、variant 和 segment 请求必须使用同一 UA。
- 同一原画 URL 上的 seek 通过客户端串行合并，不能用高并发 Range 探测。
- 原画/HLS 响应不得携带 115 Cookie 给客户端。

## 8. 测试替身

Fake 115 必须可编排：扫码状态、Cookie 刷新/CAS 冲突、提交成功/超时不确定、排队进度、失效/违规、目录移动、多个视频、连续分段、字幕、原画、HLS、限流、清理失败和明确 not-found。默认测试禁止真实网络。
