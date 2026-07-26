# Change Specification: TASK-010 翻译协议与付费幂等边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-054 至 AC-057 要求可配置 OpenAI-compatible 翻译、保护不可改写字段并在来源未变化时避免重复付费，但原任务没有冻结输出 JSON、prompt version、文本上限、protected 规范化、未配置行为或并发/崩溃后的外部调用语义。演员简介翻译还依赖 TASK-009 已落地的 Actor Mapping 中文简介。本变更补齐可执行协议与付费安全边界，不增加新的用户功能。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### OpenAI-compatible 单字段翻译协议与持久 reservation

**Requirements**:

- REQ-CHG-073: TASK-010 正式依赖 TASK-009。完整 metadata attempt 只在 `actor_map` 之后运行 `translation`；`Actor.bio_zh_source` 标记 `actor_mapping/ai`，0010 将实施前既有非空 `bio_zh` 回填为 `actor_mapping`。演员仅在 `bio_original` 非空且当前 `bio_zh_source` 不是 `actor_mapping` 时进入 AI 翻译；Actor Mapping 后续写入始终覆盖 AI 并改回 `actor_mapping`。
- REQ-CHG-074: AI 配置以单个 `ai.configuration` AES-256-GCM JSON 载荷保存，并通过版本 CAS 原子更新 `base_url/api_key/model/timeout_seconds`。配置读取返回短生命周期 typed snapshot；日志、异常和 `repr` 不得包含 api_key 或完整载荷。TASK-013 后续只回显非敏感字段与 `api_key_configured`。
- REQ-CHG-075: `base_url` 是不含 `/v1` 尾段的 provider root，规范化时只移除尾部 `/`；必须是绝对 `http/https` URI，长度不超过 2048，无 userinfo、query 或 fragment。`model` 为去除首尾空白后的 1..255 字符，`api_key` 为 1..8192 UTF-8 字节，超时为 1..600 秒。任一字段缺失或非法时不访问网络，translation stage 记录 `translation_not_configured` warning。
- REQ-CHG-076: prompt version 固定为 `sakuraplayer-zh-v1`。system prompt 固定为：`Translate only source_text into Simplified Chinese. Return exactly one JSON object matching schema_version 1. Copy protected without changing, omitting, or adding values. Never translate identifiers, actor names, maker, series, or tags.`
- REQ-CHG-077: 每次请求只翻译一个 `movie_title/movie_description/actor_bio` 字段。user JSON 固定包含 `schema_version=1`、`kind`、`source_text` 和 `protected={number,actors,maker,series,tags}`；OpenAI-compatible HTTP body固定包含 model、system/user messages、`temperature=0` 和 `response_format={"type":"json_object"}`。端点为 `POST {base_url}/v1/chat/completions`，使用 Bearer api_key。
- REQ-CHG-078: 只接受 `choices[0].message.content` 中的 UTF-8 JSON object：`{"schema_version":1,"translated_text":"...","protected":{...}}`，禁止额外字段。空 source 不请求；source_text 和 translated_text 各最多 32,000 个 Unicode 字符，序列化后的完整请求最多 512 KiB，完整响应正文最多 256 KiB。超限输入记录 `translation_input_too_large`，超限或非法响应记录 `translation_guardrail_failed`。
- REQ-CHG-079: protected 字符串比较使用 Unicode NFKC、首尾去空白、连续空白折叠为单个 ASCII 空格和 casefold；null 保持 null；actors/tags 对每项同样规范化后排序比较并保留重复项。比较不得改写数据库展示原文。任一 protected 字段缺失、增加或规范化后不同都拒绝译文。
- REQ-CHG-080: `source_hash` 固定为未经规范化的 source_text UTF-8 字节 SHA-256。完成结果唯一键固定为 `(owner_type, owner_id, source_hash, model, prompt_version)`；命中 completed 时直接复用，不再次访问 provider。key 轮换和 base_url 改变不使相同业务键失效，source/model/prompt 改变才产生新键。
- REQ-CHG-081: 付费调用前必须先持久创建或 claim `reserved` 行，再以 claim token 和未过期 lease 为 CAS 条件提交 `dispatched`，提交成功后才允许发送 HTTP。只有未进入 dispatched 的过期 reservation 可被回收。`dispatched/completed/rejected/unknown` 同一业务键永不由自动任务再次派发。
- REQ-CHG-082: 合法响应原子写 completed 结果并只在 owner 当前原文仍与 source_text 完全一致时更新 `title_zh/description_zh/bio_zh`；新的 source/model/prompt 结果可替换同字段旧 AI 译文。AI 写演员简介同时保存 `bio_zh_source=ai`，不得覆盖 `actor_mapping`。非法结构或 protected 改写写 rejected；HTTP、超时、连接异常、子进程崩溃或响应后提交失败留下 unknown/dispatched。未知结果宁可等待来源、模型或 prompt 变化，也不得猜测未付费并自动重试。
- REQ-CHG-083: 同一影片 stage 内标题、简介和缺少中文简介的关联 Actor 独立处理；单项失败继续处理其他项，最后以首个稳定错误码形成 stage warning。默认自动测试只使用 MockTransport/fake clock，不访问真实或付费 AI。

**Acceptance Criteria**:

- [x] 输入/输出 schema、固定 prompt、protected 规范化、32,000 字符和 256 KiB 边界测试通过。
- [x] 配置以一个加密载荷 CAS 保存，缺失/非法配置不访问网络且形成可显式补翻的 warning。
- [x] PostgreSQL 并发证明同一业务键最多一次从 reserved 进入 dispatched，完成结果复用不再次请求。
- [x] dispatched 后崩溃、超时、非法 JSON 和 protected 改写均不会自动重复派发或覆盖原文。
- [x] Actor Mapping 已有中文简介时不请求 AI；AI 单项失败不改变影片 `core_ready`。

**Impact**: AC-054 至 AC-057、TASK-010、元数据契约、运行配置、错误码、数据模型、迁移、provider runtime 和测试；Breaking: NO，翻译 provider 尚未实现。

## MODIFIED

### TASK-010 跨上下文与依赖

**Previous Behavior**: TASK-010 只依赖 TASK-003/TASK-008，标记为不跨边界，未说明 AI 配置所有权和 Actor Mapping 完成顺序。

**New Behavior**: TASK-010 增加 TASK-009 依赖并标记为跨边界。身份与配置上下文继续拥有加密 AI 配置，目录与元数据上下文只消费 typed snapshot并拥有 translation reservation/record；TASK-013 复用配置端口发布设置 API。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| OpenAI-compatible JSON adapter | ADDED | HIGH |
| encrypted AI configuration wrapper | ADDED | MEDIUM |
| translation reservation/record | ADDED | HIGH |
| metadata translation stage | MODIFIED | HIGH |
| TASK-010 dependency/context metadata | MODIFIED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。功能规格、元数据契约、运行配置、错误码、数据模型、任务索引、TASK-010 和追踪矩阵在 TASK-010 同一中文提交中同步；AC 映射仍为 AC-054 至 AC-057。

## Testing Strategy

- 单元测试覆盖配置、请求/响应 schema、prompt、protected 规范化、输入/响应上限和全部 provider 错误。
- SQLite 自包含测试覆盖 reservation 状态、完成复用、原文变化、Actor 条件和 stage failure isolation。
- PostgreSQL 集成测试覆盖唯一键、claim/lease CAS、并发最多一次 dispatch、终态不可重新派发和迁移约束。
- Final 使用隔离 Compose 和 MockTransport，不访问真实或付费 AI。

## Rollback Plan

TASK-010 提交前可整体回退本变更和实现。提交后若需改变 prompt、协议或付费重试语义，必须使用新 prompt version 和前向迁移，不得原地复用 `sakuraplayer-zh-v1` 或删除未知调用事实。
