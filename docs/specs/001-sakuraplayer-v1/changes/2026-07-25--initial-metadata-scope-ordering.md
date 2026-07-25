# Change Specification: 首批元数据范围边界与排序

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-026 已冻结“最近 90 天、最多 5000 个唯一番号”，但没有定义边界日、同日稳定排序、空发布日期和首批截断后剩余候选的归属。TASK-005 需要确定性 PostgreSQL 查询和可重复测试，因此本变更补齐选择语义，不改变 90 天、5000 或历史无上限要求。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 0 |
| REMOVED | 0 |

## ADDED

### 确定性首次与历史候选

**Description**: 以 `Asia/Shanghai` 的基准日期选择首批唯一番号，并把其余可靠番号作为可流式消费的历史候选。

**Requirements**:

- REQ-CHG-039: 最近 90 天必须表示包含基准日在内的 90 个上海日历日，最早边界为 `as_of - 89 days`；边界日包含，未来发布日期不得进入首批。
- REQ-CHG-040: 每个规范化番号必须先取其来源中的最大非空发布日期，再按发布日期降序、规范化番号升序确定唯一稳定顺序，之后才能截断 5000。
- REQ-CHG-041: 未进入首批的可靠番号，包括超过 5000 的近期番号、早于边界的番号和发布日期为空的番号，必须进入无总量上限的历史候选；历史顺序同样按发布日期降序、空值最后、规范化番号升序，接口不得把全部结果构造成内存列表。
- REQ-CHG-042: 待识别来源和没有影片骨架的来源不得产生首次或历史候选；TASK-005 只输出 `movie_id/normalized_number/publish_date/reason`，持久队列由 TASK-007 建立。

**Acceptance Criteria**:

- [ ] 基准日、`as_of-89` 和 `as_of-90` 三个边界样本分别进入首批、进入首批和只进入历史。
- [ ] 5001 个近期唯一番号只产生 5000 个 `initial`，余下 1 个产生 `history`。
- [ ] 同番号多来源只产生一个候选并使用最大发布日期；同日结果按规范化番号稳定排序。
- [ ] 空发布日期可靠番号只进入历史；pending 来源不产生候选。

**Impact**: TASK-005 初始选择器、TASK-007 元数据队列输入；Breaking: NO，相关生产代码尚未实现。

## MODIFIED

无。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-005 首次范围选择 | ADDED | MEDIUM |
| TASK-007 队列输入 | ADDED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。TASK-005 提供候选选择器，TASK-007 只消费已冻结的原因和排序输入。

## Testing Strategy

- PostgreSQL 测试覆盖 90 日边界、未来日期、重复番号、5001 截断和空日期。
- 生成式测试验证历史结果分批迭代，不建立全量 Python 列表。

## Rollback Plan

在 TASK-007 消费前可与 TASK-005 选择器整体回退。若上线后调整窗口，只能通过新 Delta 生成新的队列尝试，不得改写已完成任务事实。
