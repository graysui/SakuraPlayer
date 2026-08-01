# Change Specification: TASK-213 Range seek 证据串行化

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-213 曾用三个并发原画 Range 作为快速 seek 证据。真实 115 新一轮验证表明，即使三个本地
stream 请求各自签发独立能力 URL，上游仍可能随机返回两个 `206` 和一个 `403`。该并发探针绕过了
TASK-210 已冻结并实现的 `ThrottlingPlayer`：生产 Windows 任意时刻最多执行一个 seek，在途期间
只保留最后目标。批准参考项目 `avmedia` 也采用相同串行 seek 约束。本变更只校正 TASK-213 的真实
验收模型，不回退后端每请求独立签发能力 URL 的并发安全边界。

## ADDED

- 真实 Range 证据按多个不同偏移顺序执行，每个偏移都重新请求 SakuraPlayer stream 入口并跟随
  本次返回的能力 URL。
- 每个请求仍要求 `206`、非空正文和 `Content-Range`，不得把上游 `403` 记为通过或自动吞掉。
- 后端单元与 PostgreSQL 集成测试继续验证多个并发本地 stream 请求分别调用 downurl，且不共享、
  持久化或记录能力 URL。

## MODIFIED

- TASK-213 的“快速连续 seek”真实证据由三个并发上游 Range 改为与生产 `ThrottlingPlayer` 一致的
  首目标/最终目标串行执行；验收仍覆盖至少三个偏移。
- 验收清单不再要求同一能力 URL 并发 Range；每个 Range 使用独立签发的能力 URL。

## Acceptance Criteria

- [ ] 三个不同偏移依次取得独立本地 `302`，上游均返回 `206`、`Content-Range` 和非空正文。
- [ ] probe 中下一次 Range 只在前一次完成后开始，不使用 `Future.wait` 制造并发 seek。
- [ ] `ThrottlingPlayer` 的 30 至 60 次输入只执行首尾目标回归继续通过。
- [ ] 后端并发 stream 请求独立签发回归继续通过，不引入 resolver single-flight 或能力 URL 缓存。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-020 / AC-105 / AC-130 | MODIFIED | HIGH |
| TASK-213 real115 probe / checklist | MODIFIED | MEDIUM |
| TASK-210 ThrottlingPlayer contract | UNCHANGED | LOW |
| backend OriginalStreamResolver | UNCHANGED | LOW |

## Testing Strategy

- 工具契约固定真实 probe 的顺序 Range 结构并禁止 `Future.wait`。
- Windows seek 单元测试继续覆盖高频输入合并、失败清 pending 和后续恢复。
- 后端 playback 测试继续覆盖并发三请求分别签发；真实 runner 使用已确认 binding 重跑 Range、HLS、
  进度、租约和清理。

## Rollback Plan

若顺序 Range 仍失败，保留脱敏阶段、序号和状态码并阻断 TASK-213；不得加入无限重试、接受 `403`、
共享能力 URL 或代理视频字节。

## Task Impact

不新增任务。TASK-213 只校正真实 Range 证据的执行形态，TASK-108 后端签名、TASK-210 Windows seek
实现和 TASK-214 后续清理边界不变。
