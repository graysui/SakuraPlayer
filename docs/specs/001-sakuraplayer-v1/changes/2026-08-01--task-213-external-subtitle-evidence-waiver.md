# Change Specification: TASK-213 外置字幕真实证据豁免

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)
**Approved By**: 操作者于 2026-08-01 明确批准

## Summary

TASK-213 使用的真实 115 验收来源没有外置字幕记录，无法为同一受管任务提供 `.srt` 与 `.ass`
下载证据。操作者批准本轮 TASK-213 跳过这两项外部样本证据，使已通过的扫码、离线、原画、HLS、
Range、进度、租约和安全清理证据可以完成门禁。本变更不删除或放宽产品的四格式字幕支持、安全下载、
私有缓存和默认自动测试，只为本轮真实 runner 增加默认关闭、显式启用且可审计的豁免。

## ADDED

- 本轮 TASK-213 真实 runner 允许设置 `SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES=1`。
- 启用后必须输出脱敏证据 `subtitle_external_skipped state=operator_approved`，不得输出
  `subtitle_download`，也不得把缺失的 `.srt` / `.ass` 写成已通过。
- 验收清单必须记录此豁免；它只覆盖真实样本下载证据，不覆盖字幕 API、格式校验、大小限制、
  私有缓存、播放器接入或默认自动回归。

## MODIFIED

- AC-130 的 TASK-213 本轮完成条件允许以操作者批准的显式豁免替代 `.srt` 与 `.ass` 真实下载证据。
- 未设置 marker 时，runner 继续要求两种格式均存在、通过会话授权接口下载且内容非空。
- marker 仅接受精确值 `1`；其他非空值必须拒绝启动，默认测试仍不得访问真实 115。

## Acceptance Criteria

- [ ] 未设置 `SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES` 时，缺少 `.srt` 或 `.ass` 仍使真实门禁失败。
- [ ] 设置为 `1` 时不调用真实字幕下载探针，只输出 `subtitle_external_skipped state=operator_approved`。
- [ ] runner 对其他非空 marker 值失败关闭，且输出不包含 Cookie、密码、字幕正文或完整上游 URL。
- [ ] 四格式字幕产品契约和既有单元、Widget、Fake E2E 测试保持不变并继续通过。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-024 / AC-130 | MODIFIED | HIGH |
| TASK-213 / traceability matrix | MODIFIED | MEDIUM |
| Windows real115 runner / checklist | MODIFIED | MEDIUM |
| 字幕产品与自动测试契约 | UNCHANGED | LOW |

## Testing Strategy

- 工具契约测试固定 marker 名称、精确值检查、默认强制字幕探针和显式跳过证据。
- 默认 Fast 继续运行现有字幕 API、四格式解析、私有缓存和播放器测试，且不访问真实 115。
- TASK-213 Final 显式设置 marker，完成二维码及其余真实 AC-130 链路，并记录批准跳过证据。

## Rollback Plan

移除 marker 和 runner 分支即可恢复无例外的真实 `.srt` / `.ass` 下载门禁；不得删除字幕测试、降低
下载断言或把 `subtitle_external_skipped` 改写成下载成功。

## Task Impact

不新增任务。TASK-213 可在本轮显式豁免下完成；TASK-211 的字幕实现责任和 TASK-312 的真实设备
ASS 探针不变，后续真实字幕专项验收不得自动继承本豁免。
