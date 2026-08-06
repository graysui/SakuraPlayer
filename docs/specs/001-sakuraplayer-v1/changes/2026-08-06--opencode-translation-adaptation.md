# Change Specification: OpenCode Go deepseek-v4 翻译适配与占位符保护移除

**Type**: Delta
**Date**: 2026-08-06
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

Windows 管理员按 OpenCode Go 官方端点配置 AI 翻译（`https://opencode.ai/zen/go/v1` + `deepseek-v4-flash`）后，翻译任务全部失败。显式 provider 诊断确认两个独立原因：① `deepseek-v4-flash` 是思考模型，思考 token 计入 `max_tokens`，按文本长度估算的输出预算被 `reasoning_content` 耗尽，返回 `finish_reason="length"` 且 `content` 为空；② 简介中受保护元数据（如标签 `絶倫`）与相邻汉字构成复合词（`絶倫性交`）时，模型把粘合占位符整体意译丢弃，触发 `protected_mismatch`。用户决策：保留思考关闭，**完全移除占位符保护**——译文只写 `title_zh`/`description_zh`，不写任何元数据字段，因此模型自由翻译演员名/tag 不影响数据库中的番号、演员等数据；prompt 协议前向升级为 v4。

## Observed Evidence

仅使用用户授权的 API Key 与用户提供的合成测试简介进行显式真实 provider 诊断；API Key 不写入仓库、日志或快照：

| 请求 | HTTP | finish_reason | 结果 |
|---|---:|---|---|
| adapter 复现（max_tokens 估算，思考未关） | 200 | `length` | `content` 为空，`reasoning_content` 占用全部预算 |
| max_tokens=2048 | 200 | `length` | `reasoning_tokens=2048`，`content` 为空 |
| + `thinking={"type":"disabled"}` | 200 | `stop` | 无 `reasoning_tokens`，译文 JSON 完整返回 |
| 占位符保护下翻译 `絶倫性交` | 200 | `stop` | 模型稳定丢弃粘合占位符（10 个缺 1），重试无效 |
| 移除占位符保护，原文直发 | 200 | `stop` | 译文完整返回，无任何占位符校验失败 |

OpenCode 官方 Go 文档将 `deepseek-v4-flash` 列为 `https://opencode.ai/zen/go/v1/chat/completions` 的 OpenAI-compatible 模型；响应含 `reasoning_content` 字段，`thinking` 参数可关闭思考且被网关接受。

## ADDED

- REQ-CHG-325：当配置命中受支持的 OpenCode Go deepseek-v4 profile（hostname 为 `opencode.ai` 且模型名以 `deepseek-v4-` 开头，不区分大小写）时，请求必须发送 `thinking={"type":"disabled"}`，避免翻译任务生成或等待推理内容。其他 OpenAI-compatible provider 不得无条件收到该扩展字段；profile 识别规则必须由单元测试冻结（与 REQ-CHG-284 的硅基流动 `enable_thinking=false` 特判同一模式）。
- REQ-CHG-327：**移除占位符保护**。标题/简介原文（`title_original`/`description_original`）作为 `source_text` 直接发送给 AI，不再做 `[[SP_XXXXXXXX_0000]]` 替换、严格校验与本地恢复；prompt version 前向升级为 `sakuraplayer-zh-v4` 并形成新业务键。REQ-CHG-314 的"请求不得携带番号、演员、厂商、系列或标签原值"条款、REQ-CHG-315 的占位符严格校验条款及 REQ-CHG-326 复合词保护全部作废。输出仍只允许 `{"schema_version":1,"translated_text":"..."}` 单字段 JSON；`finish_reason` 必须为 `stop`；截断、非 stop、空译文、多余字段仍按 guardrail 拒绝。

## Unchanged Behavior

- 配置仍以单个加密载荷和版本 CAS 保存，API Key 不进入日志、异常、快照或 Git。
- 请求仍为一次只翻译一个字段，`temperature=0`、`response_format={"type":"json_object"}`、按种类与输入估算的 `max_tokens` 保持不变。
- 同一 `(owner_type, owner_id, source_hash, model, prompt_version)` 最多自动派发一次；dispatched 后结果不确定时不得自动重试。
- 译文仍只写 `title_zh`/`description_zh`，不写番号、演员、厂商、系列、标签等任何元数据字段。
- 默认自动测试继续禁止访问付费 AI。

## Acceptance Criteria

- [x] OpenCode Go deepseek-v4 profile 请求包含 `thinking={"type":"disabled"}`；普通 OpenAI-compatible profile 与硅基流动 profile 的既有 body 不增加未知扩展字段。
- [x] `sakuraplayer-zh-v4` 请求体不含任何占位符字段；adapter 不再替换/恢复文本；旧 `sakuraplayer-zh-v3` 及更早的 translation records 保持不可变，新业务键使用 v4。
- [x] 真实 provider 门禁使用用户授权 Key 与合成简介，关闭思考后在配置超时内返回并通过后端校验；默认测试保持离线。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| OpenAI-compatible request adapter | MODIFIED | MEDIUM（移除保护/恢复逻辑） |
| translation prompt/output protocol | MODIFIED | HIGH（v3 → v4，新业务键） |
| translation service/guard | MODIFIED | LOW（移除 protected 构造与比较） |
| 默认离线测试 | MODIFIED | LOW |

## Testing Strategy

- 单元测试冻结 OpenCode deepseek-v4 profile 的 `thinking` 字段、其他 host/模型组合不加该字段、硅基流动 profile 不受影响。
- 单元测试断言 v4 prompt 不含占位符指令、adapter 直发原文、guardrail 仍拒绝空译文/非 stop/多余字段。
- service 与 PostgreSQL 集成测试证明 v4 使用新业务键，旧终态记录不变且不自动重派。
- 真实验证必须显式启用，使用用户授权 Key 与合成文本，不写业务翻译记录。

## Rollback Plan

实现提交前可整体回退。实现提交后不得把 v4 原地改回 v3 占位符语义，也不得删除旧 translation records；若 provider capability 变化，使用新的前向 prompt/profile 变更并保留历史付费派发事实。
