# Cloud115Port 契约

**性质**: 后端内部端口，不是公共 HTTP API

**参考实现**: `https://github.com/tinypinglite/sakuramediabe.git` revision
`670ca75b2d35b606ffc0caa6fd47fd04c4c95870` 的
`sakuramediabe/src/lib/cloud115`

**就绪变更**: [TASK-101 Cloud115 协议就绪边界](../changes/2026-07-27--task-101-cloud115-readiness.md)、
[TASK-106 来源拒绝确定性边界](../changes/2026-07-28--task-106-source-rejection-determinism.md)、
[TASK-109 HLS 回退确定性边界](../changes/2026-07-28--task-109-hls-fallback-boundaries.md)、
[TASK-213 Cloud115 能力域兼容边界](../changes/2026-07-31--task-213-cloud115-capability-host-compatibility.md)、
[TASK-226 115 离线确认及时性与协议兼容](../changes/2026-08-03--task-226-cloud115-offline-confirmation.md)

## 1. 目标与分层

领域层只依赖本契约，不依赖 115 非官方字段、errno、加密细节、httpx 或任意 JSON。
TASK-101 适配器负责请求、响应校验、Cookie 合并和稳定 DTO/错误映射，只返回 Cookie
snapshot；TASK-102 的应用服务与加密仓储负责 credential version 和数据库 CAS。

## 2. 精确端口签名

```python
class Cloud115Port(Protocol):
    async def create_qr_session(self) -> QrSession: ...
    async def poll_qr_session(self, token: QrToken) -> QrStatus: ...
    async def finish_qr_session(self, token: QrToken) -> QrLoginResult: ...
    async def probe_credentials(self) -> CredentialProbe: ...
    def credential_snapshot(self) -> str | None: ...
    async def find_or_create_directory(
        self, parent_cid: str, name: str
    ) -> RemoteDirectory: ...
    async def directory_info(self, cid: str) -> DirectoryInfo: ...
    async def submit_offline(self, magnet: str, task_cid: str) -> OfflineSubmission: ...
    async def list_offline_tasks(
        self, page: int = 1, page_size: int = 100
    ) -> OfflineTaskPage: ...
    async def cancel_offline(self, info_hash: str) -> None: ...
    def list_files_recursive(self, cid: str) -> AsyncIterator[RemoteFile]: ...
    async def resolve_original(self, pickcode: str, user_agent: str) -> OriginalUrl: ...
    async def resolve_hls(self, pickcode: str, user_agent: str) -> HlsInfo: ...
    async def download_small_file(
        self, pickcode: str, user_agent: str, max_bytes: int
    ) -> bytes: ...
    async def delete_managed_entries(
        self, file_ids: tuple[str, ...], verified_parent_cid: str
    ) -> None: ...
```

- `finish_qr_session` 固定使用 `alipaymini` 登录槽，调用方不能指定其他 app。
- `credential_snapshot` 只导出当前调用作用域合并后的内存 Cookie；没有凭据时返回 None，
  不执行加密、版本读取或数据库写入。
- `cancel_offline` 底层固定 `delete_source_files=False`，不得删除已生成云盘文件。
- `find_or_create_directory` 只在给定父 CID 直接子级查找；同名超过一个抛
  `cloud115_directory_ambiguous`，不得任选一个。
- `delete_managed_entries` 的 `verified_parent_cid` 是已完成应用层归属证明后的限定输入，
  适配器仍必须把它作为上游删除的 parent/pid 限制。

## 3. 稳定 DTO

所有 DTO 都是 `frozen=True, slots=True` 的 dataclass；集合使用 tuple，状态使用字符串 Enum。

```text
QrToken { uid, time, sign }
QrSession { token, image_png }
QrStatus = waiting | scanned | confirmed | expired | canceled
QrLoginResult { account_key, cookie_snapshot }

CloudCredentialStatus = alive | expired | unavailable
CredentialProbe { status, cookie_snapshot? }

RemoteDirectory { cid, parent_cid, name }
DirectoryBreadcrumb { cid, name }
DirectoryInfo { cid, parent_cid, name, path }

OfflineStatus = queued | running | completed | failed
OfflineSubmission { info_hash }
OfflineTaskSnapshot {
  info_hash, name, size_bytes, status, percent_done,
  file_id?, pickcode?, task_cid?, failure_reason?
}
OfflineTaskPage { page, page_count, page_size, total_tasks, tasks }

RemoteFile {
  file_id, parent_cid, name, size_bytes, pickcode,
  sha1?, is_directory, is_video?, duration_seconds?, blocked?
}

OriginalUrl {
  url, expires_at, file_id, file_name, file_size_bytes,
  sha1, pickcode, user_agent
}
HlsVariant { url, bandwidth, resolution, label, user_agent }
HlsInfo { pickcode, variants }
```

`QrToken` 不包含上游二维码正文；二维码只以 PNG bytes 返回。`OfflineTaskSnapshot` 不得
包含磁力、原始 source URL、Cookie、errno 或 raw response。离线状态允许协议上等价的数字或
稳定字符串表示，以及 TASK-226 明确的非敏感字段别名；未知表示仍必须拒绝。`failure_reason` 只允许稳定的
非敏感小写蛇形值。短期 URL 只能存在于调用栈、播放会话内存对象和 `302` 构造中，禁止
进入 repository、事件、普通日志、异常或测试快照。

`list_files_recursive` 必须真正遍历直接子目录，只 yield 文件并逐目录校验分页声明和
`parent_cid`；固定最多 16 层、1024 个目录和 100000 个文件。重复目录 CID、目录环、空页
未达声明总数或超限均映射 `cloud115_protocol_error`，不能返回部分成功结果。TASK-105
resolver 在遍历前后重新验证任务目录仍是缓存根的直接子目录。

## 4. 稳定错误

适配器只抛 `Cloud115Problem(code, retry_after_seconds=None)`。异常字符串等于稳定 code，
不得保存 endpoint、完整 URL、请求/响应正文、Cookie、磁力、errno 或上游 detail。

| 操作 | 允许的稳定错误 |
|---|---|
| QR 创建/轮询/完成 | `cloud115_unavailable`, `cloud115_rate_limited`, `cloud115_protocol_error`, `cloud115_credentials_expired` |
| 凭据探活 | `cloud115_protocol_error`; alive/expired/unavailable 是正常三态结果 |
| find/create directory | `cloud115_credentials_expired`, `cloud115_directory_not_found`, `cloud115_directory_ambiguous`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |
| directory info / recursive files | `cloud115_credentials_expired`, `cloud115_directory_not_found`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |
| submit offline | `cloud115_credentials_expired`, `cloud115_source_unavailable`, `cloud115_offline_quota_exceeded`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_submit_uncertain`, `cloud115_protocol_error` |
| list offline | `cloud115_credentials_expired`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |
| cancel offline | `cloud115_credentials_expired`, `cloud115_offline_task_not_found`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |
| original | `cloud115_credentials_expired`, `cloud115_file_not_found`, `cloud115_rate_limited`, `cloud115_original_unavailable`, `cloud115_unavailable`, `cloud115_protocol_error` |
| HLS | `cloud115_credentials_expired`, `cloud115_file_not_found`, `cloud115_rate_limited`, `cloud115_hls_membership_required`, `cloud115_hls_not_ready`, `cloud115_hls_unavailable`, `cloud115_unavailable`, `cloud115_protocol_error` |
| small file | `cloud115_credentials_expired`, `cloud115_file_not_found`, `cloud115_original_unavailable`, `cloud115_small_file_too_large`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |
| managed delete | `cloud115_credentials_expired`, `cloud115_file_not_found`, `cache_ownership_mismatch`, `cloud115_rate_limited`, `cloud115_unavailable`, `cloud115_protocol_error` |

网络连接、5xx 和无法判定的非业务 HTTP 失败映射 `cloud115_unavailable`；HTTP 429 映射
`cloud115_rate_limited` 并仅保留有界非负 `Retry-After` 秒数。非法/未知 errno、字段缺失、
未知 QR status、非法 JSON 和 downurl 解密失败映射 `cloud115_protocol_error`。离线 POST
在发送后超时或断连而无法确认结果时必须映射 `cloud115_submit_uncertain`，不能映射普通
unavailable 后自动重提。

离线提交端点只有固定 revision 已观察并反向验证的 not-found errno
`20121,20125,990002,4100003,4100008` 映射 `cloud115_source_unavailable`。HTTP 400/422、
缺失 `info_hash`、errno `990005`、未知 errno 和普通离线任务 `status=failed` 均不能证明来源
永久失效；前三类映射 `cloud115_protocol_error`，普通 failed 只返回稳定
`failure_reason=offline_failed`。递归文件的 `blocked=true` 是独立违规证据，不转换为 adapter
异常，由 TASK-106 在过滤前分类。

## 5. Cookie snapshot 与 CAS

1. TASK-102 解密当前 Cookie，创建一次 TASK-101 适配器调用作用域。
2. 适配器合并作用域内每个响应的 `Set-Cookie`，删除过期项并保留未变化项。
3. `probe_credentials` 返回三态和可选新 snapshot；扫码完成返回新 snapshot；其他操作后
   TASK-102 可在作用域退出前调用 `credential_snapshot()` 取得合并结果。
4. TASK-101 不读取 credential version，不 import 仓储或 SQLAlchemy，不写数据库。
5. TASK-102 仅在数据库版本仍等于作用域起始版本时加密 CAS 写回并递增版本。
6. CAS 失败表示重新扫码或另一请求先更新；丢弃旧 snapshot，不覆盖新凭据。
7. `unavailable` 不得把绑定状态改成 `expired`。
8. Cookie 固定使用 `encrypted_setting.key=cloud115.cookie`；setting version 是唯一版本真相，
   binding `credential_version` 只在同一事务中镜像。

## 5.1 TASK-102 调用作用域

- 应用组合根以 `cookies: str | None -> async Cloud115Port context` 工厂创建短生命周期调用
  作用域；领域/应用服务不得直接 import 具体适配器。
- QR token 和 PNG 只保存在 API 进程内有界 store，固定 5 分钟、最多 8 个，不入数据库。
- 缓存根固定从顶层 CID `0` 的直接子级查找；v1 单 API 进程以 async mutex 串行远端
  find-or-create，短数据库提交再使用 PostgreSQL advisory transaction lock。

## 6. 协议主机与秘密边界

协议请求和逐跳重定向必须是 HTTPS，且精确主机只允许：

- QR：`qrcodeapi.115.com`、`passportapi.115.com`
- 目录/离线/文件/探活：`my.115.com`、`webapi.115.com`、`115.com`、`proapi.115.com`
- 原画/HLS 元数据：`proapi.115.com`、`v.anxia.com`
- 上游返回的原画/HLS 能力 URL：`*.115.com`、`*.115cdn.com`、`*.115cdn.net` 的 HTTPS 子域；只作为
  `OriginalUrl`/`HlsVariant` 返回，不由带 Cookie 的协议 client 跟随到未批准主机。

禁止 `follow_redirects=True` 的无条件跟随。每一跳在发出下一请求前重新校验 scheme、
hostname、无 userinfo，并限制最多 3 跳。普通日志只记录稳定操作名、code、状态和安全
计数，不记录 URL、query、Cookie、磁力、token、pickcode 或响应正文。

## 7. 离线提交与取消

离线提交成功只返回 `info_hash`。若请求超时，调用方使用任务 CID 与类型化分页快照对账：

- 找到属于任务目录的既有任务：保存 `info_hash`，继续 `offlining`。
- 上游明确 invalid/quota：保存相应稳定失败，不自动重提。
- 无法确认：进入持久 `submit_uncertain`，保留 running 容量与活动复用，等待人工产品操作。
- 对账固定使用 `page_size=1000` 完整读取上游声明页，只接受唯一 `task_cid` 匹配；分页形状
  异常、超过 1000 页或多个匹配均为 `cloud115_protocol_error`。

取消只按 `info_hash` 调用上游，并固定 `delete_source_files=False`。远端明确不存在映射
`cloud115_offline_task_not_found`；调用方结合本地状态决定是否视为幂等完成。
没有 `info_hash` 的不确定提交在显式取消时只做一次分页对账；仍找不到不能伪装成已取消，
必须回到 `submit_uncertain`。

离线任务处于 `queued/running` 时，worker 的下一次状态观察目标间隔不超过 2 秒；该目标不
改变 Cloud115Port 的 HTTP 超时、限流退避或提交不确定语义。状态确认完成后仍由 resolving
阶段负责文件扫描和媒体选择。

## 8. 安全删除前置条件

调用 `delete_managed_entries` 之前，TASK-107 应用服务必须验证：

```text
binding.account_key == cache_job.account_key
binding.cache_root_cid == cache_job.cache_root_cid
directory_info(task_dir_cid).parent_cid == cache_root_cid
cache_job.task_dir_cid == requested_task_dir_cid
remote_file.parent_cid 位于 task_dir_cid 子树
database owner == cache_job.id
```

任一条件不成立时不调用 115 删除并使用 `cache_ownership_mismatch`。目录/文件明确不存在
可由应用层视为已清理，但必须由 `cloud115_directory_not_found` 或
`cloud115_file_not_found` 证明，不能由 transport failure 推断。

## 9. User-Agent 与播放

- Windows 固定 UA 为 `SakuraPlayer/1.0 (Windows; x64)`；HarmonyOS 固定 UA 为
  `SakuraPlayer/1.0 (HarmonyOS; API 24)`。二者均为协议常量，不接受客户端覆盖。
- `resolve_original` 参数 UA 必须与播放器后续 Range GET 完全一致。
- Cloud115 适配器独占 HLS video info/master 请求、master 解析和 capability URL 校验；播放层只
  消费 `HlsInfo/HlsVariant`，不得再次解析 m3u8。
- `resolve_hls` 返回的每个 variant 带相同 UA；播放层校验 pickcode、非空 variants 和 variant UA，
  再按最大 bandwidth 选择首个最高项。master/variant/segment 请求必须复用该 UA。
- original 自动 HLS fallback 白名单仅含 `cloud115_original_unavailable`；凭据失效、文件不存在、
  限流、上游不可用和协议错误不得自动回退。显式 compatibility 会话直接调用 HLS。
- 同一原画 URL 的 seek 串行合并，禁止 5 个以上突发并发 Range。
- 原画/HLS 返回不得携带 115 Cookie 给客户端。
- TASK-109 证明 master 与选中 variant 的 UA 契约；客户端 variant/segment UA 分别由
  TASK-210/310 实现，并由 TASK-213/312 的真实链路门禁验证。

## 10. 测试替身与真实门禁

FakeCloud115 必须实现同一 Protocol，并可编排：QR 状态、Cookie snapshot、凭据三态、
同名目录、提交成功/不确定、分页进度、取消 not-found、目录移动、多个视频/字幕、原画、
HLS、限流、小文件过大和清理失败。Fake 的调用记录不得保存完整磁力或能力 URL。

无网络协议 fixture 位于 `backend/tests/unit/cloud115/`，默认 Fast/Final 收集。真实测试
位于 `backend/tests/real115/`，必须带 `real115` marker，并同时要求显式环境开关、外部
凭据和应用管理测试根；默认 runner 不收集该目录。TASK-213 才是发布级真实验收门禁。
