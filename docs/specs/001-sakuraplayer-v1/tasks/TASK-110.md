---
id: TASK-110
title: "字幕下载、音轨契约与生命周期"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-105, TASK-108]
ac-mapping: [AC-107, AC-108, AC-109, AC-110, AC-114]
imp-requirements: [REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [subtitle options and download API, client cleanup lifecycle signals]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-110: 字幕下载、音轨契约与生命周期

**功能描述**: 为播放器发布内嵌字幕/音轨能力、115 外置字幕选项和有上限的鉴权下载，并在缓存/登录生命周期变化时通知客户端删除副本。

**规格映射**: AC-107 至 AC-110、AC-114

## 外部依赖风险

- **依赖**: 115 小文件 downurl/download 和字幕编码质量。
- **状态**: 字幕可能损坏、超大或不存在。
- **缓解**: 四格式白名单、8 MiB 上限、同 UA、失败不阻断视频和客户端可切换。

**冻结边界**: [TASK-110 字幕下载与生命周期边界](../changes/2026-07-28--task-110-subtitle-contract.md)。

## 验收条件

- [x] manifest 表达内嵌字幕/音轨由播放器枚举；对应 AC-107、AC-114。
- [x] 外置 srt/ass/ssa/vtt 通过已认证 API 下载到客户端私有缓存；对应 AC-108。
- [x] 同名优先、多个可切换，任一字幕失败不阻止视频；对应 AC-109。
- [x] 115 缓存清理、退出登录或本地过期产生删除对应副本的稳定信号；对应 AC-110。

## Definition of Ready

- [x] TASK-105 RemoteSubtitle 和 TASK-108 PlaybackSession owner 可用。
- [x] 字幕 MIME、Content-Disposition、大小上限和错误码已由变更规格冻结。
- [x] 客户端只下载到私有缓存后交应用内播放器，不把鉴权 URL 直接交外部播放器。

## 技术上下文

- 后端只流式返回小文件字节，不落盘字幕正文。
- 下载必须验证 subtitle 属于 session/cache 且 parent 仍受管。
- manifest 提供 subtitle ID/cache job ID 映射和本地过期时间，不含客户端路径。
- logout 204 清理本机全部字幕；TASK-112 的 `cache.job.cleaned.v1.resource.id` 清理对应 job；本地期限到期清理对应副本。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/playback/subtitles.py` - 选项、鉴权和小文件下载。
- `backend/src/sakuraplayer/playback/subtitle_lifecycle.py` - 清理/注销事件。
- `backend/src/sakuraplayer/playback/subtitle_api.py` - 下载路由。
- `backend/tests/unit/playback/test_subtitle_options.py` - 同名/多字幕/格式。
- `backend/tests/integration/playback/test_subtitle_download.py` - owner、大小、失败隔离。

## 测试说明

**单元测试**:

- 四格式、同名排序、多字幕、unsupported/too_large 错误。
- 内嵌 track 由客户端枚举，后端不伪造轨道。

**集成测试**:

- 正常下载、文件删除、跨 session、目录 detached、Cookie expired，视频流仍可创建。
- cache cleaned/logout 事件触发指定副本清理，不影响永久图片。

## Definition of Done

- [x] 字幕/音轨契约、下载和生命周期完成。
- [x] 后端卷/数据库没有字幕正文。
- [x] 字幕错误不阻断播放测试通过。

## 完成证据

- Fast 为 729 passed、8 deselected；全仓 Ruff format/lint、5 个播放生产模块 mypy、宿主
  Docker 配置、完整差异和只读审计通过，无剩余 P0/P1/P2。
- 隔离 PostgreSQL 字幕安全集 8 项通过，覆盖 owner/epoch/session/cache/media、root/task/file
  实时归属、8 MiB、上游错误、原样字节、安全响应头及字幕失败后视频 302。
- Compose Final 首次尝试通过：自包含 729 passed、8 deselected，PostgreSQL
  integration/E2E 113 passed、15 deselected；迁移、五服务健康、认证 canary、秘密扫描、重启、
  ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**依赖**: TASK-105, TASK-108

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-110.md"`
