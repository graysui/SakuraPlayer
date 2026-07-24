---
id: TASK-004
title: "AVdb Release 下载、解密与同步"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-001, TASK-003]
ac-mapping: [AC-018, AC-019, AC-020, AC-021, AC-022, AC-024]
imp-requirements: [REQ-005]
cross-boundary: false
external-dependency-risk: true
provides: [AVdb release adapter, decrypt pipeline, sync run persistence]
---

# TASK-004: AVdb Release 下载、解密与同步

**功能描述**: 实现 AVdb GitHub Release 主/备发现、SHA-256 校验、PBKDF2-HMAC-SHA256/AES-256-GCM 解密、30D/全量调度和同步批次持久化。

**规格映射**: AC-018、AC-019、AC-020、AC-021、AC-022、AC-024

## 外部依赖风险

- **依赖**: `li-peifeng/AVdb-Only` 与 `jzdxjk/AVdb-Only` GitHub Release API。
- **状态**: 协议和加密格式已由本地指南核验，但上游可变。
- **缓解**: 固定样本、manifest 白名单、资产 SHA-256、最近成功游标和主备失败可观测；默认测试使用 fixture。

## 验收条件

- [ ] 按文档的 200,000 次 PBKDF2-HMAC-SHA256 与 AES-256-GCM 解密内层 CSV；对应 AC-018。
- [ ] 主源失败时使用备用源，切换前校验资产 SHA-256；对应 AC-019。
- [ ] 每日 03:00 导入 30D、每周日 04:00 全量对账；同一 Release 幂等且全量缺失旧行不删除；对应 AC-020 至 AC-022。
- [ ] 同步游标、Release、资产摘要、时间和失败原因持久化；对应 AC-024。

## Definition of Ready

- [ ] TASK-001 迁移和 scheduler 入口可运行。
- [ ] 已读取 `contracts/avdb-source.md`；上游固定密钥材料作为公开格式常量，不与 SakuraPlayer 启动级 secret 混用。
- [ ] 主备仓库、资产名和 Release ID 规则冻结。

## 技术上下文

- `resources` 上下文拥有 `avdb_sync_run`、asset manifest 和 provider cache。
- 主备仓库、资产白名单、解密限制和 13 字段边界只使用 `contracts/avdb-source.md`，不依赖未跟踪原始指南。
- 解密采用流式/分批 CSV 读取，单批失败不回滚其他已提交批次。
- 使用 `Asia/Shanghai` 调度，scheduler 只入队，worker 执行导入。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/resources/avdb_release.py` - Release 主备发现和下载。
- `backend/src/sakuraplayer/resources/avdb_crypto.py` - manifest 校验和 AES-GCM 解密。
- `backend/src/sakuraplayer/resources/sync_service.py` - 批次导入协调和游标。
- `backend/src/sakuraplayer/scheduler/jobs.py` - 03:00/周日 04:00 入队注册。
- `backend/tests/fixtures/avdb/` - 固定加密样本和损坏资产样本。
- `backend/tests/unit/resources/test_avdb_crypto.py` - 解密/摘要单测。
- `backend/tests/integration/resources/test_avdb_sync.py` - 主备、调度和持久化测试。

## 测试说明

**单元测试**:

- 用固定样本验证 PBKDF2 参数、GCM tag、CSV UTF-8 BOM 和 manifest 字段校验。
- 验证错误摘要、未知算法、超大 manifest 和错误 Release 被拒绝。

**集成测试**:

- Fake GitHub 返回主源失败、备用成功、相同摘要和不同摘要，验证切换与停止策略。
- 重复执行同一 30D/全量 Release，验证同步游标和既有缺失记录不被删除。

**边界条件**:

- 下载中断、单批 CSV 损坏、空资产、时区切换、scheduler 重复触发。

## Definition of Done

- [ ] 解密、摘要、主备、调度和持久化完成。
- [ ] 未把固定密钥、磁力或上游响应写入日志。
- [ ] fixture/integration 测试通过。

**依赖**: TASK-001, TASK-003

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-004.md"`
