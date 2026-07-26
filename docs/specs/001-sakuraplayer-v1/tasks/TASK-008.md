---
id: TASK-008
title: "JavDB 核心、DMM 与永久图片"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
dependencies: [TASK-003, TASK-007]
ac-mapping: [AC-042, AC-044, AC-045, AC-046, AC-047, AC-048]
imp-requirements: [REQ-008, REQ-009]
cross-boundary: false
external-dependency-risk: true
provides: [JavDB core provider, DMM enrichment, permanent image store]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-008: JavDB 核心、DMM 与永久图片

**功能描述**: 接入 JavDB 核心影片/演员关系、DMM 简介富化、可选 JavDB 凭据和永久目录图片原子缓存。

**规格映射**: AC-042、AC-044 至 AC-048

## 外部依赖风险

- **依赖**: JavDB、DMM 和图片主机。
- **状态**: 参考 provider 可移植，但页面/API 可变化。
- **缓解**: 防腐 DTO、固定 HTML/JSON fixture、超时、图片白名单/大小限制；失败不删除最近成功数据。

## 验收条件

- [x] JavDB 是影片和演员关系主来源，核心事务成功后影片 `core_ready`；对应 AC-042、AC-044。
- [x] DMM 只补简介，失败保留核心；对应 AC-045。
- [x] JavDB 账号密码可选且加密，未配置只跳过需登录 TOP250；对应 AC-046。
- [x] 封面/剧照等写永久卷，不随 115 缓存删除；失败使用占位并可通过富化阶段重试补齐；对应 AC-047、AC-048。

## Definition of Ready

- [x] TASK-007 子进程 stage runner 和 TASK-003 secret provider 可用。
- [x] `CoreMovieMetadata`、DMM Description 与图片写入契约已确认。
- [x] 允许的图片主机、内容类型和大小边界已由 [TASK-008 永久图片安全边界](../changes/2026-07-26--task-008-image-security-boundaries.md) 固定。

## 技术上下文

- 单影片 JavDB search/detail 串行；核心短事务后再执行图片/DMM。
- 图片先写临时文件、校验摘要/像素后原子替换。
- provider 响应先映射内部 DTO，禁止领域层解析任意 JSON/HTML。

## 实施批次

| 批次 | 行为闭环 | 聚焦证据 |
|---|---|---|
| 1 | Movie/Actor/Tag/CatalogImage 模型、迁移与核心事务 | Schema 结构、幂等 upsert、关系替换和 `core_ready` 原子提交 |
| 2 | JavDB/DMM 防腐 DTO、HTML fixture 和可选加密凭据 | 精确番号、结构变化、未找到、限流、未配置/错误凭据 |
| 3 | 永久图片 fake HTTP、完整解码、原子缓存与占位 | SSRF、重定向、MIME、8 MiB、像素、半写入和重名 |
| 4 | stage executor 接线与可选失败隔离 | core 成功后 DMM/图片 warning、显式 enrichment retry、默认无真实网络 |
| 5 | Fast、只读审计、Final、任务与交接同步 | 完整门禁证据和一次中文提交 |

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/catalog/providers/javdb.py` - JavDB 防腐适配器。
- `backend/src/sakuraplayer/catalog/providers/dmm.py` - DMM 文本提取适配器。
- `backend/src/sakuraplayer/catalog/core_import.py` - Movie/Actor/Tag 核心事务。
- `backend/src/sakuraplayer/catalog/image_store.py` - 永久图片原子缓存和占位。
- `backend/tests/unit/catalog/providers/test_javdb.py` - JavDB fixture 合约。
- `backend/tests/unit/catalog/providers/test_dmm.py` - DMM fixture 合约。
- `backend/tests/integration/catalog/test_core_import.py` - core_ready 与富化隔离。

## 测试说明

**单元测试**:

- JavDB 编号精确匹配、详情字段、演员关系和未找到；DMM 文本/空描述/结构变化。
- 图片成功、类型错误、过大、半写入、占位状态和 `retry-enrichment(images)`。

**集成测试**:

- 核心提交后让 DMM/图片失败，验证影片仍可见且 warning/重试状态持久化。
- 未配置/错误 JavDB 凭据时验证公开功能继续、需登录 TOP250 明确跳过。

**边界条件**:

- 同一影片重复 core import、图片重名、provider 限流、核心已提交后子进程超时。

## Definition of Done

- [x] JavDB 核心、DMM、凭据和永久图片完成。
- [x] 可选失败不阻断或回滚 core_ready。
- [x] provider 和原子文件测试通过。

## 验证证据

- Focused/Fast：TASK-008 provider/core/image/runtime/child/migration 54 passed；自包含 293 passed、7 deselected；PostgreSQL/Schema 38 passed；只读 compileall 与宿主 Compose 配置断言通过。
- 只读审计：Schema/事务、Provider/安全、supervisor/代码质量三路复审发现的 fence、并发 upsert、图片补偿、cover position 和 DTO 去重问题均已修复，最终无剩余 P0/P1/P2。
- Final：`backend/tests/run-compose.ps1` 尝试 1 通过；自包含 293 passed、7 deselected，PostgreSQL/Compose 67 passed、12 deselected，并完成迁移、五服务健康、重启恢复和隔离资源清理；默认测试未访问真实 JavDB、DMM 或图片主机。

**依赖**: TASK-003, TASK-007

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-008.md"`
