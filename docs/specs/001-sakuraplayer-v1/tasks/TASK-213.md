---
id: TASK-213
title: "Windows 端到端与真实 115 门禁"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-201, TASK-202, TASK-203, TASK-204, TASK-205, TASK-206, TASK-207, TASK-208, TASK-209, TASK-210, TASK-211, TASK-212, TASK-113]
ac-mapping: [AC-005, AC-018..AC-021, AC-059..AC-122, AC-128, AC-129, AC-130, AC-132, AC-133..AC-135]
imp-requirements: [REQ-002, REQ-005, REQ-012..REQ-025]
cross-boundary: false
external-dependency-risk: true
provides: [Windows E2E suite, AC-130 real115 evidence]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-213: Windows 端到端与真实 115 门禁

**功能描述**: 先用 Fake 后端完成 Windows 用户旅程，修复真实门禁发现的 AVdb 官方资产名、manifest 与 Cloud115 能力域兼容阻断，再用真实 115 专用目录验证 AC-130；全部通过才允许 HarmonyOS 工作流进入。

**规格映射**: Windows/后端适用 `[IMP]`、AC-130 `[EXT]`、AC-132 `[SEF]`

## 外部依赖风险

- **依赖**: 真实 Windows 10/11、115 账号和单/多/分段/字幕样本。
- **状态**: 外部协议与媒体解码是发布关键风险。
- **缓解**: 专用 `SakuraPlayer-Cache` 测试目录、显式 marker、受控删除、脱敏证据和失败即阻断。
- **AVdb 阻断**: 官方现行 release 使用带连字符时间戳；只按 [TASK-213 AVdb 资产名兼容边界](../changes/2026-07-31--task-213-avdb-asset-name-compatibility.md) 扩展全名白名单。
- **AVdb manifest 阻断**: 官方现行公开信封增加四个固定声明字段；只按 [TASK-213 AVdb manifest 兼容边界](../changes/2026-07-31--task-213-avdb-manifest-compatibility.md) 扩展严格字段白名单。
- **Cloud115 能力域阻断**: 真实 downurl 返回批准参考实现已记录的 `*.115cdn.net`；只按 [TASK-213 Cloud115 能力域兼容边界](../changes/2026-07-31--task-213-cloud115-capability-host-compatibility.md) 扩展精确 HTTPS 子域白名单。
- **外置字幕样本豁免**: 当前真实来源没有 `.srt` / `.ass`；本轮只按 [TASK-213 外置字幕真实证据豁免](../changes/2026-08-01--task-213-external-subtitle-evidence-waiver.md) 使用默认关闭的显式 marker，并记录操作者批准的跳过证据。
- **Range 并发阻断**: 三条独立能力 URL 的上游并发仍可能随机 403；真实 probe 按 [TASK-213 Range seek 证据串行化](../changes/2026-08-01--task-213-range-seek-evidence-serialization.md) 与生产 `ThrottlingPlayer` 一致地顺序验证多个偏移，后端并发独立签发回归不变。

## 验收条件

- [x] Fake E2E 完成登录、三导航、搜索、榜单、女优、详情、多来源、等待、播放器、字幕、进度、设置和清理。
- [x] 真实 115 验证扫码、离线、原画、HLS 回退、Range seek、字幕下载和安全清理；本轮 `.srt` / `.ass` 可按批准 Delta 显式记录 `subtitle_external_skipped`，不得伪装为下载通过；对应 `[EXT]` AC-130。
- [x] Windows 核心链路失败时不进入 HarmonyOS 功能开发；对应发布门禁。
- [x] 单个可选元数据源故障不影响已有目录/榜单/播放；对应 `[SEF]` AC-132。
- [x] 首次连接覆盖后端地址测试、bootstrap token、登录以及换地址后的本机状态清理；对应 AC-133 至 AC-135。
- [x] 隔离验收库可从主源或备用源导入官方现行 30D 资产名与 manifest，且非白名单名称/声明继续拒绝；对应 AC-018 至 AC-021 的 TASK-213 阻断验证。

## Definition of Ready

- [x] TASK-113 和 TASK-201 至 TASK-212 已实现并评审。
- [x] 真实账号、测试来源和专属根目录由操作者确认。
- [x] 测试不会接触根目录外任何用户文件。

## 技术上下文

- 真实 E2E 必须运行 release 产物或等价配置，不用 debug shortcut。
- Range seek 顺序验证多个偏移、每次独立签发以及 206/Content-Range；HLS 验证最高 variant 与固定 UA。后端测试继续覆盖并发 stream 请求不得共享能力 URL。
- 清理后再查 parent/root，确认只删除任务目录。

## 实现文件（仅文件名）

**创建**:

- `windows/integration_test/windows_user_journey_test.dart` - Fake 全用户旅程。
- `windows/integration_test/windows_real115_e2e_test.dart` - AC-130 显式套件。
- `docs/acceptance/windows-real115-checklist.md` - 脱敏人工/自动证据表。

**修改**:

- `backend/src/sakuraplayer/resources/avdb_crypto.py` - 官方现行时间戳资产名与 manifest 兼容。
- `backend/src/sakuraplayer/shared/runtime.py` - 禁止第三方 HTTP 请求 URL 进入 INFO 日志。
- `backend/src/sakuraplayer/cloud_cache/qr_service.py` - 已确认二维码直接换取 Cookie，不重复轮询上游状态。
- `backend/src/sakuraplayer/cloud_cache/worker/offline.py` - 按 page/page_count 遍历真实离线任务，不将 115 月配额 total 误当任务总数。
- `backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/adapter.py` - 接受真实 `*.115cdn.net` 能力子域，继续拒绝相似后缀。
- `backend/tests/unit/resources/test_avdb_crypto.py` - 允许/拒绝资产名与 manifest 回归。
- `backend/tests/start/test_runtime_logging.py` - 第三方请求日志隔离回归。
- `backend/tests/unit/cloud_cache/test_qr_service.py` - 已确认状态不重复轮询回归。
- `backend/tests/unit/cloud_cache/test_offline_worker.py` - 配额 total 与分页一致性回归。
- `backend/tests/unit/cloud115/test_adapter_contract.py` - 能力域允许/拒绝边界回归。
- `backend/tests/unit/playback/test_hls_resolver.py` - 原画并发请求独立签发能力 URL 回归。
- `windows/lib/core/api/api_models.dart` - 兼容 play-request 省略 None 的三个 cache job 字段。
- `windows/lib/features/cache/data/play_request_api.dart` - 兼容 ready/reused play-request 省略 None 的 wait deadline。
- `windows/test/features/cache/play_request_controller_test.dart` - 真实 play-request DTO 省略字段回归。

## 测试说明

**Fake E2E**:

- 两个窗口尺寸、浅深主题、加载/空/错误/重连、60 秒边界和后台通知。

**真实 115**:

- 扫码 -> 立即/排队 -> 单/多/分段文件 -> 原画 -> compatibility HLS -> 快速连续 seek -> srt/ASS -> 95%进度 -> active lease 拒绝清理 -> 退出后安全清理。
- 未设置字幕豁免 marker 时仍强制下载 srt/ASS；本轮设置为 `1` 时只输出操作者批准的脱敏跳过证据，其他字幕自动测试保持不变。
- 真实操作全程扫描日志/数据库，确认无 Cookie、磁力、完整上游/签名 URL。

## Definition of Done

- [x] Fake Windows E2E 全部通过。
- [x] AC-130 每项有脱敏证据且真实目录清理确认；本轮外置字幕项允许使用批准 Delta 规定的显式跳过证据。
- [x] HarmonyOS 进入门禁标记为 passed。

## 实现证据

- Windows Fast：后端 AC-129 算法 180 项、`flutter analyze`、unit/widget 209 项、Fake smoke 1 项和
  TASK-213 Fake 用户旅程 4 项通过；默认 real115 套件只运行离线 HLS 算法并明确跳过真实网络。
- 真实 115：操作者完成新二维码扫码；ready 任务依次通过三个独立签发的 Range `206`、active lease
  cleanup `409`、HLS manifest/子资源 `200`、95% completed 和最终 `cleaned`。本轮只按批准 Delta
  输出 `subtitle_external_skipped state=operator_approved`，未伪装为字幕下载通过。
- 后端 Fast 为 787 passed/8 deselected，Ruff 290 文件格式与 lint 通过；PostgreSQL 聚焦为
  125 passed/16 deselected。
- Compose Final 第二次尝试通过 787 项自包含和 125 项 PostgreSQL integration/E2E，迁移、五服务
  健康、认证 canary、秘密日志扫描、重启持久化、ready 降级恢复和隔离资源清理全部完成。
- 专属 `sakuraplayer-task213` 验收 Compose 的 5 个容器、4 个卷和网络已删除；二维码临时文件、活动
  lease 和验收数据库残留均为 0，未触碰应用受管根外的用户文件。

**依赖**: TASK-201..TASK-212, TASK-113

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-213.md"`
