# Change Specification: TASK-213 Cloud115 能力域兼容边界

**Type**: Delta
**Date**: 2026-07-31
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-213 真实原画门禁中，`proapi.115.com/app/chrome/downurl` 成功返回并解密了类型正确的
原画 DTO，但当前能力 URL 使用 `cdnfhnfile.115cdn.net`。既有白名单只接受
`*.115.com` 和 `*.115cdn.com`，因此安全校验把有效响应稳定映射为
`cloud115_protocol_error`。批准参考实现 revision `670ca75` 的 Cloud115 文档也明确记录了
相同 `*.115cdn.net` 原画地址。本变更只增加这一精确 HTTPS 子域后缀，不改变协议请求主机、
Cookie 边界、重定向次数或 URL 脱敏规则。

## ADDED

- 上游返回的原画/HLS 能力 URL 允许 `*.115cdn.net` 的 HTTPS 子域。
- `115cdn.net` 裸域、`attacker115cdn.net`、`115cdn.net.attacker.invalid` 和其他相似后缀继续拒绝。
- 并发本地 stream 请求必须各自解析能力 URL，不得把多个 Range 合并到同一上游直链。

## MODIFIED

- 能力 URL 白名单由 `*.115.com`、`*.115cdn.com` 扩展为
  `*.115.com`、`*.115cdn.com`、`*.115cdn.net`。
- 每一跳仍要求 HTTPS、无 userinfo、端口为空或 443，并在发出请求前重新校验；带 Cookie 的
  协议 client 不得跟随到能力域。
- 完整能力 URL、query、Cookie、pickcode 和响应正文继续不得进入数据库、普通日志、测试快照或回复。

## Acceptance Criteria

- [ ] `https://<subdomain>.115cdn.net/...` 能通过能力 URL 校验并进入原画 `302 no-store` 流程。
- [ ] 裸域、相似后缀、userinfo、HTTP、非 443 端口和未批准主机继续返回
  `cloud115_protocol_error`。
- [ ] 三个并发本地 stream 请求各自签发能力 URL，真实 Range 均成功且不持久化或记录完整上游 URL。
- [ ] 默认测试仍不访问真实 115；真实门禁只通过显式 marker 运行。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-020 / AC-105 / AC-130 | MODIFIED | HIGH |
| Cloud115Port contract | MODIFIED | HIGH |
| TASK-213 / traceability matrix | MODIFIED | MEDIUM |
| Cloud115 capability validator | MODIFIED | MEDIUM |

## Testing Strategy

- 单元测试允许真实观察到的 `*.115cdn.net` 子域，并拒绝裸域与后缀混淆样本。
- playback 单元与 PostgreSQL 集成测试覆盖并发请求独立签发、302 和 no-store。
- TASK-213 显式真实门禁复用当前 active binding，验证多个 Range 后继续执行 HLS、字幕、租约与清理。

## Rollback Plan

若真实能力 URL 仍无法完成 Range，请保留脱敏状态/错误码证据并回退本变更；不得允许任意
`115cdn.net` 相似后缀、关闭逐跳校验、代理视频字节或记录完整能力 URL。

## Task Impact

不新增任务。TASK-213 修复真实 AC-130 门禁发现的能力域兼容阻断；TASK-101/TASK-108/TASK-109
既有端口、原画与 HLS 主责不变，后续 TASK-214 仍依赖 TASK-213 完整完成。
