---
id: TASK-114
title: "115 缓存播放后端代码清理"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: completed
reviewed_date: 2026-07-29
completed_date: 2026-07-29
cleanup_date: 2026-07-29
dependencies: [TASK-113]
ac-mapping: []
imp-requirements: []
cross-boundary: false
external-dependency-risk: false
provides: [phase2 cleanup manifest and equivalent cloud cache playback files]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-114: 115 缓存播放后端代码清理

**功能描述**: 在 115 后端完成且审计收敛后执行纯卫生清理，保留所有协议、状态机、安全删除和公共签名行为。

**清理门禁**: [TASK-114 清理范围与等价门禁](../changes/2026-07-29--task-114-cleanup-gates.md)

## 验收条件

- [x] 只清理固定 Git 区间重建并由静态 manifest 冻结的 126 个 Python 文件。
- [x] 删除 debug 日志/注释、临时 fixture、无用 import 和明显不可达代码，不改变状态转换。
- [x] 运行 ruff format/check、类型检查、后端全量测试和 TASK-113 E2E。
- [x] Cloud115 NOTICE、协议 fixture、错误码和真实测试 marker 保留。

## Definition of Ready

- [x] TASK-113 为 `completed`，正式只读审计无剩余 P0/P1/P2 且 Compose Final 通过。
- [x] `eb280ab^..baf218b` 可重建 126 个当前仍存在的 Python 路径，静态清单完整。
- [x] TASK-113 Final 基线通过且当前扫描未发现需要在 cleanup 修复的逻辑缺陷。

## 技术上下文

- 使用 `specs-code-cleanup`；测试失败立即停止。
- 不升级 115 协议、不改重试/超时、不合并状态。
- 保留必要协议注释，尤其 UA、RSA/KDF 和删除证明。
- Python 3.10.16 测试镜像锁定 Ruff 0.16.0 与 mypy 2.3.0。
- Ruff 检查 `src tests alembic/env.py`；mypy 精确检查质量目录清单中的 57 个生产文件。
- 清理前后比较 OpenAPI、迁移、数据库约束、Cloud115Port、状态机、错误码、事件、
  UA、签名/HLS/字幕/进度常量和保护文件摘要。
- 默认基线为 Fake 115 + 真实隔离 PostgreSQL + Compose Final，不访问真实 115；
  发布级真实 115 门禁仍归 TASK-213。

## 实现文件（仅文件名）

**修改**:

- `backend/src/`、`backend/tests/`、`backend/alembic/env.py` - 仅限静态 manifest 中的 Python 文件。
- `backend/tests/README.md` - 记录 TASK-114 质量入口。
- `backend/tests/quality/test_task015_cleanup_gate.py` - 使 Phase 1 迁移集合门禁允许后续前向迁移。
- `docs/specs/001-sakuraplayer-v1/tasks/TASK-114.md` - Cleanup Summary。

**创建**:

- `backend/tests/quality/task114_cleanup_manifest.txt` - 固定清理 manifest。
- `backend/tests/quality/task114_mypy_files.txt` - 精确 mypy 文件清单。
- `backend/tests/quality/task114_cleanup_gate.py` - Phase 2 等价基线入口。
- `backend/tests/quality/test_task114_cleanup_gate.py` - 清单与基线回归测试。
- `docs/specs/001-sakuraplayer-v1/changes/2026-07-29--task-114-cleanup-gates.md` - 可执行清理边界。

## 测试说明

- 扫描 `print(`、DEBUG/TEMP、未使用 import、短链/Cookie 误日志。
- 运行格式化、静态检查、全部单元/集成/E2E。
- 比较 OpenAPI 和状态转换表，确认无签名/功能变化。
- 比较清理前后 TASK-114 基线，并确认 NOTICE、协议 fixture 和 `real115` marker 摘要不变。

## Definition of Done

- [x] 仅卫生改动且所有测试重新通过。
- [x] 无秘密或短链调试输出。
- [x] 追加 Cleanup Summary 并完成任务。

## Cleanup Summary

- 固定 Git 区间 `eb280ab^..baf218b` 与静态 manifest 逐项一致，共 126 个路径：
  61 个生产文件、64 个测试文件和 `backend/alembic/env.py`。批准文件已全仓格式化，
  Ruff lint 和调试/TEMP/TODO/FIXME 扫描均无可清理债务，因此未制造生产逻辑差异。
- 新增 TASK-114 质量入口，清理前后 OpenAPI、20 份迁移摘要、数据库约束、
  Cloud115Port/DTO、CacheJob 状态机、错误码、事件和 UA/签名/HLS/字幕/进度/删除常量
  逐项相等；NOTICE、协议 fixture、`real115` 和 pytest marker 摘要保持不变。
- 修复 TASK-015 历史质量测试把 Phase 1 的 13 份迁移误作永久全仓总数的问题；现在
  显式验证 0001 至 0013 仍完整存在，并由 TASK-114 精确保护当前 0001 至 0020。
- Fast 最终为 783 passed、8 deselected；Phase 2 PostgreSQL integration/E2E 为
  41 passed、1 deselected；Ruff format/lint、57 文件 mypy、宿主 Docker 断言、完整
  差异与审计通过，无剩余 P0/P1/P2。
- Compose Final 首次尝试通过：自包含 776 passed、8 deselected，PostgreSQL
  integration/E2E 125 passed、16 deselected；迁移、五服务健康、认证 canary、秘密
  扫描、重启、ready 降级恢复和隔离资源清理全部完成，默认测试未访问真实 115。

**完成日期**: 2026-07-29

**依赖**: TASK-113

**实现命令**:

`/developer-kit-specs:specs-code-cleanup --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-114.md"`
