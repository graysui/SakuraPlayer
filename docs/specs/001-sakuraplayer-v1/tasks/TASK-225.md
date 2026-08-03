---
id: TASK-225
title: "硅基流动 Qwen 翻译兼容修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-010, TASK-223, TASK-224]
ac-mapping: [AC-054, AC-055, AC-056, AC-057, AC-058]
imp-requirements: [REQ-011]
cross-boundary: false
external-dependency-risk: true
provides: [SiliconFlow Qwen translation profile, prompt v2, safe translation diagnostics]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-225: 硅基流动 Qwen 翻译兼容修复

**功能描述**: 修复硅基流动 `Qwen/Qwen3.5-35B-A3B` 在现有翻译协议下长时间思考、频繁超时并返回错误输出字段的问题，使新翻译尝试可以快速返回并通过既有严格 schema 和 protected guard。

**实施边界**: [硅基流动 Qwen 翻译协议兼容](../changes/2026-08-02--siliconflow-qwen-translation-compatibility.md)

## 验收条件

- [x] 使用新的 prompt version 明确唯一输出 JSON 结构，模型不得返回 `kind/source_text`、Markdown、代码围栏或额外字段。
- [x] 硅基流动 Qwen3.5 profile 关闭思考模式，其他 OpenAI-compatible provider 的请求兼容性不回退。
- [x] 输出 token 边界覆盖标题、简介和演员简介，不把短句诊断使用的 512 token 固定值直接用于长简介。
- [x] 新 prompt version 产生新付费业务键；旧 v1 失败与不确定记录保持不可变且不自动批量重试。
- [x] 后端日志能够安全区分超时、HTTP、响应超限、JSON、schema 和 protected 失败，不记录秘密、元数据正文或思考内容。
- [x] 默认测试不访问付费 AI；显式真实硅基流动门禁只使用一条合成文本并通过现有后端校验。

## Definition of Ready

- [x] TASK-010 已 completed，翻译 schema、protected guard 和付费派发状态机可用。
- [x] TASK-223 已只读确认正式翻译 completed 为 0，主要失败码为 guardrail/upstream。
- [x] 硅基流动官方文档已确认 `/v1/chat/completions`、`response_format` 和该模型的 `enable_thinking` 能力。
- [x] 合成文本真实诊断已复现错误字段与长思考，并验证关闭思考和明确 schema 后通过后端校验。
- [x] TASK-224 已完成独立验证和中文 Git 提交，工作区不存在跨任务混合修改。

## 根因与实验证据

- 当前 `sakuraplayer-zh-v1` 只引用 `schema_version 1`，没有告诉模型 `translated_text` 的准确输出结构。
- 模型实际返回合法 JSON，但把译文写入 `source_text` 并保留 `kind`，被 `extra=forbid` 和缺失字段校验拒绝。
- 当前请求没有发送 `enable_thinking=false`；合成短句响应包含约 9965 字符思考内容并耗时约 43 秒，正式请求大量达到 60 秒超时。
- 明确输出结构并关闭思考的对照请求约 1.3 秒返回，思考内容为 0，现有输出 schema 和 protected guard 通过。

## 实施批次

1. 以失败 fixture 冻结当前 Qwen 错误输出、prompt v2 完整结构和严格 guard 不放宽。
2. 实现受限硅基流动 Qwen3.5 request profile、关闭思考和有界输出策略，并保持其他 provider body 兼容。
3. 增加脱敏失败子分类与 trace id 日志，验证不记录请求、响应、思考或秘密。
4. 验证 prompt version 前向业务键和旧记录不自动重派；运行 Focused/Fast 与只读审计。
5. 完成 Final；经显式开关执行一次合成文本真实门禁，更新任务、索引、追踪和交接后独立中文提交。

## 预计实现文件

**修改**:

- `backend/src/sakuraplayer/catalog/translation/adapter.py` - prompt version、provider profile、请求边界和安全诊断。
- `backend/src/sakuraplayer/catalog/translation/service.py` - 新 prompt version 业务键与失败诊断接线。
- `backend/tests/unit/catalog/translation/test_adapter.py` - Qwen 输出、profile、上限与错误分类。
- `backend/tests/unit/catalog/translation/test_service.py` - 新旧 prompt 记录和不自动重派。
- `backend/tests/integration/catalog/test_translation_service.py` - PostgreSQL 业务键与旧事实保护。
- `docs/specs/001-sakuraplayer-v1/contracts/metadata-providers.md` - provider capability 和诊断边界。
- `docs/specs/001-sakuraplayer-v1/contracts/error-codes.md` - 稳定错误与安全子分类边界。
- 任务索引、追踪矩阵与 `SESSION-HANDOFF.md` - TASK-225 生命周期状态。

## 测试说明

- MockTransport 覆盖当前错误输出、正确输出、思考开关、普通 provider、非 stop、截断、超时、非 200、非法 envelope/content/schema 和 protected mismatch。
- PostgreSQL 覆盖 prompt v1/v2 独立业务键、旧 rejected/unknown/dispatched 不变、completed 复用和并发最多一次 dispatch。
- 日志与快照扫描不得出现 Authorization、API Key、source/protected/translation、完整响应或 `reasoning_content`。
- 真实硅基流动测试默认 skip；显式执行时只使用合成文本，不创建 `translation_record` 或修改影片/演员。

## Definition of Done

- [x] 硅基流动 Qwen3.5 合成翻译在配置超时内返回并通过严格后端校验。
- [x] 正式新增翻译可以完成，旧失败记录未被自动批量重试或修改。
- [x] 通用 OpenAI-compatible provider、protected guard、付费幂等和 AI warning 隔离无回归。
- [x] Focused、Fast、完整差异审计、Final、秘密扫描和 `git diff --check` 全部通过。
- [x] 任务状态、变更规格、契约、索引、追踪矩阵和交接同步，并创建独立中文 Git 提交。

## 完成证据

- Focused：translation adapter/service 41 项通过；审计补强后的 adapter 31 项通过。
- Fast：Ruff format/check、857 项自包含测试、宿主 Docker 配置、差异与秘密扫描通过，9 项 infrastructure marker 按既有分层排除。
- Final：Compose 一次通过 857 项自包含、128 项 PostgreSQL integration/E2E、迁移、五服务健康、认证 canary、持久日志秘密扫描、重启、ready 降级恢复和资源清理。
- 真实门禁：使用现有加密配置和一条合成文本直接调用硅基流动 Qwen3.5，v2 adapter 于 744 ms 返回并通过严格 schema/protected guard；未创建业务翻译记录或修改影片、演员和队列。

**依赖**: TASK-010, TASK-223, TASK-224
