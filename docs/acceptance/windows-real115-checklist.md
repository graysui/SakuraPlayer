# Windows 真实 115 验收清单

此清单用于 TASK-213 / AC-130。证据必须脱敏：只记录阶段、HTTP 状态码、应用内部 UUID、文件格式和最终状态；不得记录 Cookie、账号密码、磁力、二维码内容、完整签名 URL、上游 URL 或字幕正文。

## 前置确认

- [x] 在真实 Windows 10/11 上使用私有 release 包，或由 `run_task213_acceptance.ps1` 先构建 release 再用 Flutter 支持的 profile 配置驱动同一套验收测试。
- [x] 操作者确认测试影片来源包含单文件、多文件或分段文件；默认还需包含 srt 与 ASS 字幕。本轮若样本缺少两种外置字幕，必须按批准 Delta 显式设置字幕豁免 marker 并记录操作者批准。
- [x] 操作者确认 115 中的受管根目录、任务 parent/root 和 owner 均由 SakuraPlayer 创建并管理。
- [x] 记录受管 parent/root 的脱敏前置快照：根目录存在、测试任务目录存在、其他目录数量，不记录完整远端路径。
- [x] `SAKURAPLAYER_TEST_REAL115=1` 与受管根目录确认 marker 仅在本次验收进程中设置。
- [x] `SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES=1` 仅用于 2026-08-01 批准的 TASK-213 本轮；未设置时必须继续下载 srt/ASS，其他非空值拒绝启动。
- [x] 默认必须扫码；仅当同一隔离验收库已保存 `qr_confirmed` 证据时，允许显式设置 `SAKURAPLAYER_REAL115_REUSE_BINDING=1` 继续后续链路，且必须记录 `binding_reused/active`，不得把它写成新的扫码证据。

## 自动证据

| 阶段 | 通过条件 | 脱敏证据 |
|---|---|---|
| QR 扫码 | 二维码由操作者扫码，绑定状态为 active 且根目录 ready | `qr_ready`、`qr_confirmed`、状态码、session UUID |
| 离线任务 | 任务从立即、排队或复用状态进入 ready，选中媒体非空 | `play_request`、`cache_ready`、job UUID、状态 |
| 原画 Range | 固定 Windows UA；三个偏移按生产 seek 合并规则顺序执行，每次独立签发，均为 206 且含 Content-Range | `original_range`、请求序号、状态码 |
| compatibility HLS | 固定 Windows UA 请求 manifest、最高带宽 variant 和媒体子资源，均可读取且 manifest 为 HLS | `hls_manifest`、`hls_child`、状态码 |
| 字幕 | 默认 srt 与 ASS 均通过会话授权接口下载且内容非空；本轮显式豁免时不发起下载 | 默认：`subtitle_download`、格式、状态码；豁免：`subtitle_external_skipped state=operator_approved` |
| 95% 进度 | heartbeat 返回 completed，随后释放 active lease | `progress_95`、completed 状态 |
| active lease | 播放 lease 存在时 cleanup 稳定返回 409 / `cache_active_lease` | `cleanup_blocked`、状态码、错误码 |
| 安全清理 | 释放 lease 后 cleanup 进入 cleaning 并最终为 cleaned | `cleanup_requested`、`cleanup_cleaned`、job UUID |

## 清理后复核

- [x] 再查同一个 parent/root：仅本次测试任务目录被删除，受管根目录仍存在。
- [x] 对比前后脱敏快照，确认其他同级目录数量和 owner 未变化。
- [x] 后端日志、数据库审计字段和 runner 输出均未出现 Cookie、密码、磁力、完整签名 URL 或完整上游 URL。
- [x] 二维码临时图片已从本机临时目录删除。
- [x] 任一项失败时保持 TASK-213 与 HarmonyOS 门禁为 blocked，不手工改写为 passed。

## 结果

- 执行时间：2026-08-01
- Windows 版本：Windows 11 专业版 10.0.26200（Build 26200）
- release 产物标识：SHA-256 `8427d65c09466c40b8991e944fa6956003e5ca232a32be64d8587b30a614108e`
- 操作者：用户扫码确认
- 结论：`passed`
- 阻断错误码（如有）：无
- 外置字幕证据：`operator_approved_skip`
