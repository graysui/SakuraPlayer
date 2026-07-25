---
id: TASK-006
title: "影片多来源、标签和拒绝标记"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-005]
ac-mapping: [AC-031, AC-032, AC-033, AC-034, AC-035, AC-036]
imp-requirements: [REQ-007]
cross-boundary: false
external-dependency-risk: false
provides: [movie-source relation, source labels, merge split, source rejection port]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-006: 影片多来源、标签和拒绝标记

**功能描述**: 建立影片与独立 AVdb 帖子的多来源关系、叠加标签证据、后台合并拆分和不含磁力的永久来源拒绝端口。

**规格映射**: AC-031 至 AC-036

## 验收条件

- [x] 每条来源按 website + tid 独立保存并可关联同一影片，后台可事务性合并或拆分错误关系；对应 AC-031、AC-032。
- [x] 字幕、破解、4K、有码是可叠加标签；严格按 section/category/标题或明确元数据证据生成；对应 AC-033、AC-034。
- [x] 离线前 API 将 AVdb size 标为资源大小，预留真实视频文件大小字段；对应 AC-035。
- [x] 确定性失效/违规/无法离线可擦除活动来源磁力并保存不含磁力的拒绝标记，后续导入跳过；对应 AC-036。

## Definition of Ready

- [x] TASK-005 的来源和影片唯一键已迁移。
- [x] 破解/字幕/4K/有码真实字段样本已固定。
- [x] Cloud/cache 后续调用所需 [`SourceRejectionPort`](../contracts/source-rejection-port.md) 契约已确认。

## 技术上下文

- 整个亚洲无码不能推断为破解；4K 历史空 category 不能推断为有码。
- 拒绝表只保存 website、tid、reason_code 和时间；磁力密文从活动来源清空。
- 合并/拆分必须修正来源关系而不丢播放进度、收藏或元数据任务历史。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/resources/source_labels.py` - 证据化标签规则。
- `backend/src/sakuraplayer/resources/movie_source_service.py` - 来源关系、合并和拆分。
- `backend/src/sakuraplayer/resources/rejection.py` - 拒绝端口及导入 anti-join。
- `backend/src/sakuraplayer/resources/admin_api.py` - identify/merge/split 管理 API。
- `docs/specs/001-sakuraplayer-v1/contracts/source-rejection-port.md` - 跨上下文最小输入和原子拒绝语义。
- `backend/tests/unit/resources/test_source_labels.py` - 真实分类组合测试。
- `backend/tests/integration/resources/test_movie_source_admin.py` - 多来源和拒绝持久化。

## 测试说明

**单元测试**:

- 验证中文字幕、无码破解、4K原版、有码证据的所有叠加组合和禁止推断样本。
- 验证资源大小命名与真实视频文件大小不混用。

**集成测试**:

- 合并/拆分多来源后检查关系、番号别名和原始帖子均保留。
- 创建拒绝标记后验证磁力密文清空、事件/日志无磁力、后续增量/全量不重建来源。

**边界条件**:

- 同一来源重复拒绝、拒绝与导入并发、合并目标已存在、拆分番号冲突。

## Definition of Done

- [x] 多来源、标签、合并拆分和拒绝端口完成。
- [x] 17,202 破解与 4K/有码事实可由 fixture 正确分类。
- [x] 拒绝记录不含磁力或可还原摘要。

**依赖**: TASK-005

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-006.md"`
