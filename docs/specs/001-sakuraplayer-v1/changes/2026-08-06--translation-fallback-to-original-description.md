# Change Specification: 详情页翻译缺失时回退显示原文简介

**Type**: Delta
**Date**: 2026-08-06
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-227 冻结"详情 `description` 只投影 `description_zh`，Windows 不显示 `description_original`；缺失译文显示'暂无中文简介'"。AI 翻译失败时 `description_zh` 为 NULL，详情页只显示"暂无中文简介"，用户完全看不到已刮削到的原文简介（`description_original`，来自 JavDB/DMM），体验不合理。修改为：译文缺失时回退显示原文简介并标注"（原文）"，Windows 与 HarmonyOS 两端行为一致。后端详情接口已同时返回 `description` 与 `description_original`，无需后端改动。

## ADDED

- REQ-CHG-328：详情页"简介"区显示优先级改为 `description_zh` → `description_original`（标注"（原文）"）→ "暂无简介"。TASK-227 的"Windows 不显示 `description_original`"条款作废；`description_original` 为空时仍显示空态文案。翻译成功时仍只显示中文译文，不显示原文。

## Unchanged Behavior

- 后端 `MovieDetailOutput.description` 仍只投影 `description_zh`，`description_original` 字段继续返回。
- 数据库与翻译记录不变；本变更只影响详情页展示层。

## Acceptance Criteria

- [x] 译文缺失时详情页显示原文简介并标注"（原文）"；译文存在时只显示中文译文。
- [x] Windows 与 HarmonyOS 两端显示规则一致，空态文案更新为"暂无简介"。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| Windows 影片详情页 | MODIFIED | LOW |
| HarmonyOS 影片详情页 | MODIFIED | LOW |

## Testing Strategy

- Windows widget 测试覆盖译文缺失回退原文、译文存在优先中文两种状态。
- HarmonyOS JsUnit/UiTest 覆盖 description 为空回退原文逻辑。

## Rollback Plan

实现提交前可整体回退，恢复"缺失译文显示暂无中文简介"。
