# Change Specification: 硅基流动 Qwen 翻译协议兼容

**Type**: Delta
**Date**: 2026-08-02
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

正式刮削中 AI 翻译没有产生 completed 结果，主要表现为 `translation_upstream_error` 和 `translation_guardrail_failed`。使用已配置的硅基流动 `Qwen/Qwen3.5-35B-A3B` 与合成文本复现后确认：当前 OpenAI-compatible HTTP 结构可被上游接受，但 `sakuraplayer-zh-v1` 没有向模型声明准确输出字段，模型把译文写回输入字段 `source_text` 并增加 `kind`，被后端严格输出 schema 拒绝；请求又没有关闭该模型支持的思考模式，短翻译生成大量思考内容并频繁达到 60 秒超时。本变更新增 TASK-225，以新的 prompt version 和受限 provider capability 修复兼容性，同时保留既有付费幂等与敏感数据边界。

## Observed Evidence

仅使用合成文本进行显式真实 provider 诊断，没有把 API Key、真实影片原文、译文或完整响应写入仓库：

| 请求 | HTTP | 耗时 | 安全结果 |
|---|---:|---:|---|
| 当前 adapter | 200 | 约 40 秒 | 返回合法 JSON，但缺少 `translated_text` 且包含额外字段，guardrail 拒绝 |
| 明确输出结构并关闭思考 | 200 | 约 1.3 秒 | 无思考内容，现有输出 schema 与 protected guard 通过 |

硅基流动官方 [创建对话请求（OpenAI）](https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions) 说明 `/v1/chat/completions`、`response_format` 和 `enable_thinking`；文档明确列出 `Qwen/Qwen3.5-35B-A3B` 支持思考模式开关。

## ADDED

- REQ-CHG-282：新增 TASK-225，负责硅基流动 Qwen3.5 翻译协议兼容、前向 prompt version、非思考请求和安全可诊断错误分类；TASK-225 在 TASK-224 独立完成并提交前保持 pending。
- REQ-CHG-283：新 prompt version 必须向模型给出唯一允许的输出对象 `{"schema_version":1,"translated_text":"...","protected":{"number":"...","actors":[],"maker":null,"series":null,"tags":[]}}`，明确禁止返回 `kind/source_text`、Markdown、代码围栏或其他字段。后端严格 `_OutputPayload` 和 protected 比较规则保持不放宽。
- REQ-CHG-284：当配置明确命中受支持的硅基流动 Qwen3.5 profile 时，请求必须发送 `enable_thinking=false`，避免翻译任务生成或等待推理内容。其他 OpenAI-compatible provider 不得无条件收到硅基流动扩展字段；provider/profile 识别规则必须由单元测试冻结。
- REQ-CHG-285：生产输出 token 边界必须根据翻译种类和有界输入确定，防止无界生成且不得把短句试验的 `max_tokens=512` 直接套用于最长 32,000 字符简介。截断、非 stop finish reason 或空译文仍按 guardrail 拒绝。
- REQ-CHG-286：翻译失败诊断必须在不保存请求或响应正文的前提下区分网络/超时、非 200 状态、响应超限、外层协议、content JSON、输出 schema 和 protected mismatch；允许记录耗时、稳定安全子分类、HTTP 状态和 `x-siliconcloud-trace-id`。不得记录 API Key、Authorization、base URL query、source/protected/translation、完整响应或 `reasoning_content`。

## MODIFIED

- REQ-CHG-287：`sakuraplayer-zh-v1` 和其既有 `reserved/dispatched/completed/rejected/unknown` 记录保持不可变。修复必须使用新的 prompt version 形成新业务键；部署不得自动批量重新派发旧失败记录，只有用户后续显式刮削或富化动作才能按既有队列规则创建新尝试。
- REQ-CHG-288：AC-054 至 AC-058 的 OpenAI-compatible 语义增加已验证 provider capability 边界。AI 失败仍只形成可选阶段 warning，不阻塞 `core_ready`、浏览或播放；默认自动测试继续禁止访问付费 AI。

## Unchanged Behavior

- AI 配置仍以单个加密载荷和版本 CAS 保存，API Key 不进入日志、异常、快照或 Git。
- 请求仍为一次只翻译一个字段，`temperature=0` 和 `response_format={"type":"json_object"}` 保持不变。
- 输出仍禁止额外字段，protected 仍按 NFKC、casefold、空白折叠和无序 actors/tags 比较。
- 同一 `(owner_type, owner_id, source_hash, model, prompt_version)` 最多自动派发一次；dispatched 后结果不确定时不得自动重试。
- Actor Mapping 中文简介继续优先于 AI，AI 失败不改变影片可见性。

## Acceptance Criteria

- [x] 当前曾返回 `kind/source_text` 的 fixture 被新 prompt 约束为 `translated_text`，严格 schema 和 protected guard 通过且断言未放宽。
- [x] 硅基流动 Qwen3.5 profile 请求包含 `enable_thinking=false`；普通 OpenAI-compatible profile 的既有 body 不增加未知扩展字段。
- [x] 标题、简介和演员简介的输出 token 边界覆盖短文本、长文本、截断和非 stop 响应，不删除或降低 32,000 字符与 256 KiB 既有上限测试。
- [x] prompt version 前向升级后可创建新业务键，旧 v1 的 unknown/rejected/dispatched 记录不被修改或自动重派。
- [x] Docker 日志可用安全子分类区分超时、HTTP、JSON、schema 和 protected 失败，并通过秘密与真实元数据扫描。
- [x] 显式真实 provider 门禁只使用一条合成文本，在关闭思考后于配置超时内返回并通过后端校验；默认测试保持离线。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| translation prompt/output protocol | MODIFIED | HIGH |
| OpenAI-compatible request adapter | MODIFIED | HIGH |
| translation diagnostics | ADDED | MEDIUM |
| paid dispatch/idempotency records | MODIFIED | HIGH |
| default offline tests | MODIFIED | LOW |

## Testing Strategy

- 单元测试冻结 prompt 完整输出结构、硅基流动 profile、普通 provider body、finish reason、输出上限和安全诊断分类。
- service 与 PostgreSQL 集成测试证明新 prompt version 使用新业务键，旧终态和 dispatched 事实不变且不自动重派。
- Fast/Final 只使用 MockTransport；真实硅基流动验证必须显式启用，只发送一条合成文本并且不写业务翻译记录。
- 完整秘密扫描拒绝 Authorization、API Key、请求/响应正文、真实元数据和思考内容进入日志或测试快照。

## Rollback Plan

实现提交前可整体移除 TASK-225 代码变更。实现提交后不得把新协议原地改回 `sakuraplayer-zh-v1`，也不得删除旧 translation records；若 provider capability 发生变化，使用新的前向 prompt/profile 变更并保留历史付费派发事实。
