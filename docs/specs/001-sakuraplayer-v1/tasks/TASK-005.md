---
id: TASK-005
title: "六分类导入、番号与首次范围"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-004]
ac-mapping: [AC-025, AC-026, AC-027, AC-028, AC-029, AC-030]
imp-requirements: [REQ-006, REQ-007]
cross-boundary: false
external-dependency-risk: false
provides: [source importer, number normalizer, initial metadata selector, pending identification]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-005: 六分类导入、番号与首次范围

**功能描述**: 流式导入六个目标分类全部历史来源，规范化番号，建立去重影片骨架，并实现最近 90 天/最多 5000 的首批元数据选择和待识别流程。

**规格映射**: AC-025 至 AC-030

## 验收条件

- [ ] 只导入亚洲有码、亚洲无码、中文字幕、4K原版、素人有码、FC2 的全部历史来源；对应 AC-025。
- [ ] 首批队列只取最近 90 天且最多 5000 个唯一番号，之后继续无总量上限的历史补齐；对应 AC-026、AC-027。
- [ ] 无番号或无法规范化的来源进入可搜索、可分页的待识别列表，不进入正式媒体库和自动元数据队列；管理员可手动关联；对应 AC-028、AC-029。
- [ ] 同一规范化番号只有一部影片骨架，并保留原始番号和别名；对应 AC-030。

## Definition of Ready

- [ ] TASK-004 能提供验证后的 CSV 行流和同步批次。
- [ ] 番号规范化规则与特殊 FC2 格式已有固定样本。
- [ ] 29 万级目标数据量作为容量基线。

## 技术上下文

- `resource_source` 以 website + tid 唯一；`movie` 以 normalized_number 唯一。
- 初始选择先按发布日期降序去重，再截断 5000；不能按来源帖子数截断。
- 处理采用批次提交，内存中不构造全部 CSV 行列表。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/resources/number_normalizer.py` - 番号解析和规范化。
- `backend/src/sakuraplayer/resources/source_importer.py` - 六分类流式 upsert。
- `backend/src/sakuraplayer/resources/initial_scope.py` - 90 天/5000 与历史补齐选择器。
- `backend/src/sakuraplayer/resources/identification_api.py` - 待识别查询和手动关联。
- `backend/tests/integration/resources/test_identification_api.py` - 安全字段、分页、搜索和关联。
- `backend/tests/unit/resources/test_number_normalizer.py` - 番号/FC2/空值样本。
- `backend/tests/integration/resources/test_source_importer.py` - 分类、范围、待识别和唯一性。

## 测试说明

**单元测试**:

- 覆盖标准番号、大小写/空白/分隔符、FC2、缺失和不可可靠解析样本。
- 验证 90 天边界日、重复番号、超过 5000 和不足 5000 的选择顺序。

**集成测试**:

- 混合六目标和非目标分类导入，验证只保留目标来源且全部历史来源可持续补齐。
- 并发导入相同番号/帖子，验证电影和来源唯一约束；手动关联后进入影片关系。
- 查询待识别列表时确认响应不含磁力、上游正文或预览原始载荷。

**边界条件**:

- 同一番号多原始写法、空发布日期、无番号约 2813 条规模、批次中途失败。

## Definition of Done

- [ ] 六分类、规范化、首批范围和待识别流程完成。
- [ ] 29 万级 fixture/生成数据验证采用流式或分批处理。
- [ ] 正式查询不能看到待识别来源。

**依赖**: TASK-004

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-005.md"`
