---
id: TASK-105
title: "视频字幕解析与媒体选择"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-104]
ac-mapping: [AC-035, AC-092, AC-093, AC-108, AC-109]
imp-requirements: [REQ-007, REQ-018, REQ-020]
cross-boundary: false
external-dependency-risk: true
provides: [remote file scanner, media scorer, segment queue, subtitle locator]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-105: 视频字幕解析与媒体选择

**功能描述**: 离线完成后递归枚举受管目录，识别有效视频/字幕、真实大小、主视频、多个候选和连续分段队列。

**规格映射**: AC-035、AC-092、AC-093、AC-108、AC-109

## 外部依赖风险

- **依赖**: 115 目录/文件元数据字段与文件命名质量。
- **状态**: 远端文件可能含广告、样片、子目录和不规则分段。
- **缓解**: 技术计划白名单/阈值、可解释评分、真实命名 fixture 和无法判断时强制用户选择。

## 验收条件

- [ ] 完成后显示 115 真实视频文件大小，离线前仍显示资源大小；对应 AC-035。
- [ ] 递归识别视频/字幕并排除明显广告、样片和低于阈值文件；对应 AC-092。
- [ ] 明确主视频自动选择，多个有效候选要求选择，连续分段组成有序队列；对应 AC-093。
- [ ] 识别 srt/ass/ssa/vtt，同名优先且多个可切换；对应 AC-108、AC-109。

## Definition of Ready

- [ ] TASK-104 能确认离线完成并提供 task_dir_cid。
- [ ] 文件扩展名、256 MiB 阈值和广告/分段 fixture 已冻结。
- [ ] RemoteMedia/RemoteSubtitle Schema 已迁移。

## 技术上下文

- 评分必须可解释并保留证据，不通过 AI 猜测主文件。
- 文件只按稳定 ID/pickcode/parent CID 保存，不保存短链。
- `awaiting_selection` 仍占就绪容量，选择后原子进入 ready。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/file_scanner.py` - 递归枚举和白名单。
- `backend/src/sakuraplayer/cloud_cache/media_selection.py` - 评分、候选和分段排序。
- `backend/src/sakuraplayer/cloud_cache/subtitle_locator.py` - 四格式和同名匹配。
- `backend/src/sakuraplayer/cloud_cache/media_selection_api.py` - 用户选择媒体队列。
- `backend/tests/unit/cloud_cache/test_media_selection.py` - 广告/正片/分段样本。
- `backend/tests/integration/cloud_cache/test_file_resolution.py` - 115 tree 到 ready。

## 测试说明

**单元测试**:

- 单正片、多候选、CD1/CD2/part、广告/样片、小文件、嵌套目录评分。
- 同名字幕优先、多个字幕排序和四扩展名大小/格式。

**集成测试**:

- Fake 目录解析后验证真实大小覆盖展示字段、awaiting_selection/ready 转换和选择归属校验。
- 连续分段保存 sequence_no 并按顺序返回播放 manifest。

**边界条件**:

- 无有效视频、违规标记、重名文件、字幕无对应视频、目录在解析时移动。

## Definition of Done

- [ ] 文件/字幕/大小/选择/分段完成。
- [ ] 无法明确识别时不擅自播放错误文件。
- [ ] 真实文件树 fixture 测试通过。

**依赖**: TASK-104

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-105.md"`
