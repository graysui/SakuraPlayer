---
id: TASK-010
title: "OpenAI 兼容翻译"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-003, TASK-008]
ac-mapping: [AC-054, AC-055, AC-056, AC-057]
imp-requirements: [REQ-011]
cross-boundary: false
external-dependency-risk: true
provides: [translation adapter, protected-field guard, translation record]
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

- [ ] 支持配置 base_url、加密 api_key、model 和超时；对应 AC-054。
- [ ] 异步翻译影片标题/简介，演员简介仅缺中文内容时翻译；对应 AC-055。
- [ ] 番号、演员姓名、厂商、系列和标签不能被 AI 改写；对应 AC-056。
- [ ] 原文、译文、source_hash、模型和 prompt_version 持久化，来源未变复用结果；对应 AC-057。

## Definition of Ready

- [ ] TASK-003 secret provider 和 TASK-008 core_ready 影片存在。
- [ ] 翻译输入/输出 JSON schema 和 prompt version 已冻结。
- [ ] protected 字段比较采用规范化但不改变展示原文。

## 技术上下文

- 翻译是元数据任务可选 stage，失败只能产生 warning。
- 唯一键为 owner/source_hash/model/prompt_version。
- 适配器不记录完整 prompt、key 或上游响应正文。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/translation/adapter.py` - OpenAI 兼容 HTTP 适配。
- `backend/src/sakuraplayer/catalog/translation/guard.py` - protected 字段验证。
- `backend/src/sakuraplayer/catalog/translation/service.py` - 幂等记录和 stage 集成。
- `backend/tests/unit/catalog/translation/test_guard.py` - 改写拒绝测试。
- `backend/tests/integration/catalog/test_translation_service.py` - 配置、复用和失败隔离。

## 测试说明

**单元测试**:

- 输出改写番号、演员、厂商、系列或标签时拒绝；只翻译允许字段时接受。
- 相同 source_hash/model/prompt 命中，相同文本不同 prompt/model 分开保存。

**集成测试**:

- Fake AI 成功/超时/非法 JSON/401，验证 secret 脱敏和 core_ready 影片持续可浏览。
- 演员已有中文简介时验证不发起翻译请求。

**边界条件**:

- 空简介、超长文本、来源更新、key 轮换、AI 不可用。

## Definition of Done

- [ ] 配置、翻译、保护、持久化和复用完成。
- [ ] AI 失败不改变影片可见性。
- [ ] 默认测试无付费请求。

**依赖**: TASK-003, TASK-008

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-010.md"`
