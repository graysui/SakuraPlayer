---
id: TASK-010
title: "OpenAI 兼容翻译"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-003, TASK-008, TASK-009]
ac-mapping: [AC-054, AC-055, AC-056, AC-057]
imp-requirements: [REQ-011]
cross-boundary: true
external-dependency-risk: true
provides: [encrypted AI configuration, translation adapter, protected-field guard, paid-dispatch reservation, translation record]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-010: OpenAI 兼容翻译

**功能描述**: 实现可配置 OpenAI 兼容翻译适配器、异步标题/简介翻译、保护字段校验和来源摘要幂等复用。

**规格映射**: AC-054 至 AC-057

## 外部依赖风险

- **依赖**: 管理员配置的 OpenAI-compatible base_url/model。
- **状态**: 具体提供方未知，必须只依赖公开兼容 JSON 边界。
- **缓解**: httpx transport fixture、严格输出 schema、超时、保护字段验证、失败 warning 和 secret redaction。

## 验收条件

- [x] 支持配置 base_url、加密 api_key、model 和超时；对应 AC-054。
- [x] 异步翻译影片标题/简介，演员简介仅缺中文内容时翻译；对应 AC-055。
- [x] 番号、演员姓名、厂商、系列和标签不能被 AI 改写；对应 AC-056。
- [x] 原文、译文、source_hash、模型和 prompt_version 持久化，来源未变复用结果；对应 AC-057。

## Definition of Ready

- [x] TASK-003 secret provider、TASK-008 core_ready 影片和 TASK-009 Actor Mapping 可用。
- [x] 翻译输入/输出 JSON schema、`sakuraplayer-zh-v1` prompt、文本/响应上限已由 [TASK-010 翻译协议与付费幂等边界](../changes/2026-07-26--task-010-translation-safety-boundaries.md) 冻结。
- [x] protected 字段采用 NFKC/casefold/空白折叠比较但不改变展示原文；并发与崩溃后的付费派发事实已冻结。

## 跨边界说明

- 身份与配置上下文拥有 `ai.configuration` 加密载荷和 CAS；目录与元数据上下文只消费短生命周期 typed snapshot。
- TASK-010 交付 typed 配置端口供后续 TASK-013 设置 API 复用，不在翻译领域层直接解析 `encrypted_setting`。

## 技术上下文

- 翻译是元数据任务可选 stage，失败只能产生 warning。
- 唯一键为 owner/source_hash/model/prompt_version。
- HTTP 调用前先持久提交 dispatched；同一业务键的 dispatched/completed/rejected/unknown 不自动再次派发。
- 适配器不记录完整 prompt、key 或上游响应正文。

## 实施批次

| 批次 | 行为闭环 | 聚焦证据 |
|---|---|---|
| 1 | 0010 translation reservation/record Schema 与加密 AI 配置 typed wrapper | 迁移约束、CAS、缺失/非法配置、秘密不出库 |
| 2 | 固定 prompt、单字段 JSON、protected guard 与 OpenAI adapter | 请求/响应 schema、32K/256 KiB、改写拒绝、HTTP 故障 |
| 3 | reservation claim/dispatch/finalize 与完成结果复用 | PostgreSQL 并发最多一次 dispatch、过期 reserved 回收、终态不重派 |
| 4 | movie/actor 翻译服务与 metadata runtime 接线 | 原文变化 fence、已有 actor 中文简介跳过、单项失败隔离 |
| 5 | Fast、只读审计、Final、任务与交接同步 | 完整门禁证据和一次中文提交 |

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/translation/__init__.py` - 翻译包入口。
- `backend/src/sakuraplayer/catalog/translation/adapter.py` - OpenAI 兼容 HTTP 适配。
- `backend/src/sakuraplayer/catalog/translation/guard.py` - protected 字段验证。
- `backend/src/sakuraplayer/catalog/translation/service.py` - 幂等记录和 stage 集成。
- `backend/src/sakuraplayer/catalog/translation/config.py` - typed AI 配置与加密 setting adapter。
- `backend/alembic/versions/0010_translation.py` - 付费派发与翻译记录 Schema。
- `backend/tests/start/test_translation_migration.py` - Schema 与约束。
- `backend/tests/unit/catalog/translation/test_config.py` - 加密配置与 CAS。
- `backend/tests/unit/catalog/translation/test_guard.py` - 改写拒绝测试。
- `backend/tests/unit/catalog/translation/test_adapter.py` - 固定协议和 HTTP 边界。
- `backend/tests/unit/catalog/translation/test_service.py` - reservation、复用与失败隔离。
- `backend/tests/integration/catalog/test_translation_service.py` - 配置、复用和失败隔离。

**修改**:

- `backend/src/sakuraplayer/catalog/models.py` - translation record 与演员简介来源模型。
- `backend/src/sakuraplayer/catalog/actor_mapping.py` - Actor Mapping 权威简介来源。
- `backend/src/sakuraplayer/catalog/providers/runtime.py` - typed AI 配置与 translation stage 接线。
- `backend/tests/integration/start/test_schema_guard_postgres.py` - 0010 head 表清单。
- `backend/tests/unit/catalog/providers/test_runtime.py` - translation stage 运行时证据。
- `backend/tests/unit/catalog/test_actor_mapping.py` - 权威简介来源证据。

## 测试说明

**单元测试**:

- 输出改写番号、演员、厂商、系列或标签时拒绝；只翻译允许字段时接受。
- 相同 source_hash/model/prompt 命中，相同文本不同 prompt/model 分开保存。
- 32,000 字符、256 KiB、额外字段、空 choices、非 JSON content 和 protected 缺失/增加均拒绝。

**集成测试**:

- Fake AI 成功/超时/非法 JSON/401，验证 secret 脱敏和 core_ready 影片持续可浏览。
- 演员已有中文简介时验证不发起翻译请求。
- PostgreSQL 并发同一 actor/source 只允许一次进入 dispatched；dispatched 后崩溃事实不自动重派。

**边界条件**:

- 空简介、超长文本、来源更新、key 轮换、AI 不可用。

## Definition of Done

- [x] 配置、翻译、保护、持久化和复用完成。
- [x] AI 失败不改变影片可见性。
- [x] 默认测试无付费请求。

## 验证证据

- Focused/Fast：TASK-010 配置、协议、guard、service、runtime 与迁移聚焦组合 60 passed；Fast 自包含 389 passed、7 deselected；PostgreSQL Actor/Core/Translation 回归 9 passed，Final 修复后的 Schema 聚焦 1 passed；compileall、宿主 Docker 配置、秘密扫描和 `git diff --check` 通过。
- 只读审计：完整差异复审补齐演员简介来源、在途状态不可变、空白译文拒绝、512 KiB 请求和 256 KiB 流式响应边界，最终无剩余 P0/P1/P2；默认测试只使用 fake/MockTransport，不访问真实或付费 AI。
- Final：`backend/tests/run-compose.ps1` 尝试 2 通过；自包含 389 passed、7 deselected，PostgreSQL/Compose 72 passed、12 deselected，并完成 0010 迁移、五服务健康、认证 canary、敏感日志扫描、重启持久性、ready 降级恢复和隔离资源清理。尝试 1 仅发现并修复完整 Schema 期望表清单缺少 `translation_record`。

**依赖**: TASK-003, TASK-008, TASK-009

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-010.md"`
