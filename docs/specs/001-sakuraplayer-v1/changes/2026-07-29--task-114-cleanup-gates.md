# Change Specification: TASK-114 清理范围与等价门禁

**Type**: Delta
**Date**: 2026-07-29
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-114 原任务把输入范围交给不存在的 TASK-101 至 TASK-113 逐任务评审文件，并要求
TASK-113 处于 `reviewed/implemented`，与统一流程要求清理前置任务必须 `completed` 冲突。
“真实基线测试”、类型文件和 Phase 2 等价接口也未固定。本变更只补齐可执行清理门禁，
不改变产品、协议、Schema、迁移或外部门禁范围。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 3 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### 可重建的 Phase 2 清理清单

**Requirements**:

- REQ-CHG-144: 清理输入以 TASK-101 首提交父节点至 TASK-113 完成提交的固定 Git
  区间 `eb280ab^..baf218b` 审批；静态 manifest 保存该区间内当前仍存在的 Python
  路径，结果必须排序、去重且可在无 Git 的测试容器中读取。
- REQ-CHG-145: manifest 固定为 126 个路径，包括 61 个生产文件、64 个测试文件和
  `backend/alembic/env.py`。允许卫生修改的范围仅为 manifest；Alembic 历史迁移、
  产品契约、依赖版本、NOTICE 和真实测试配置均不可因清理改变。

**Acceptance Criteria**:

- [x] 质量测试确认 manifest 路径全部存在、排序去重且分类计数准确。
- [x] 完整差异不包含 manifest 外的生产或测试卫生修改。

### 锁定的 Python 质量入口

**Requirements**:

- REQ-CHG-146: Python 3.10.16 测试镜像继续固定 Ruff 0.16.0 和 mypy 2.3.0；
  Ruff 门禁为 `ruff format --no-cache --check src tests alembic/env.py` 与
  `ruff check --no-cache src tests alembic/env.py`，不升级工具或改变 lint 规则。
- REQ-CHG-147: mypy 清单由 `task114_mypy_files.txt` 固定为 57 个生产文件。
  `api/app.py`、`api/__main__.py`、`scheduler/__main__.py` 和 `worker/__main__.py`
  的 5 个既有错误不属于纯卫生修复；这 4 个文件仍受 Ruff、等价基线和完整测试约束。
- REQ-CHG-148: 如清理引入任何新 mypy 错误必须停止；不得借 TASK-114 修复上述既有
  跨上下文类型债务，也不得以忽略配置掩盖错误。

**Acceptance Criteria**:

- [x] 测试镜像报告锁定版本，Ruff 和 57 文件 mypy 全部通过。
- [x] mypy 清单是生产 manifest 的严格子集，且不包含 4 个已记录债务文件。

### Phase 2 行为等价基线

**Requirements**:

- REQ-CHG-149: 质量脚本在清理前后规范化捕获完整 FastAPI OpenAPI、全部迁移摘要、
  SQLAlchemy `CheckConstraint`、CacheJob 状态/容量/合法转换、Cloud115Port 与 DTO
  签名、Phase 2 模块常量和稳定错误码。
- REQ-CHG-150: 同一基线必须覆盖缓存事件、通知、固定 User-Agent、签名时长、HLS
  回退、字幕/进度阈值、安全删除相关常量，以及 Cloud115 NOTICE、协议 fixture、
  `real115` 目录、pytest marker 和 `.dockerignore` 的摘要。
- REQ-CHG-151: 基线写入 `.planning/TASK-114/`，清理后由同一脚本比较；任一差异
  必须停止 Final。完整测试仍是行为证据，摘要比较不能替代测试。
- REQ-CHG-152: “真实基线”固定指状态化 Fake 115、真实隔离 PostgreSQL 和无参数
  Compose Final；默认 Focused/Fast/Final 不访问真实 115。TASK-213 继续独占发布级
  `real115` 门禁。

**Acceptance Criteria**:

- [x] 清理前后所有基线分区逐项相等。
- [x] TASK-113 E2E、完整 backend 测试和 Compose Final 通过且未收集 `tests/real115`。

## MODIFIED

### TASK-114 Definition of Ready

**Previous Behavior**: TASK-113 为 `reviewed/implemented` 且存在批准 review；范围依赖
TASK-101 至 TASK-113 的评审文件。

**New Behavior**: TASK-113 必须为 `completed`，其完成证据必须包含收敛的正式只读审计
和 Compose Final；TASK-114 以固定 Git 区间、静态 manifest 和清理前基线作为输入。

### 通用清理流程适配

**Previous Behavior**: TASK-114 直接继承通用技能要求目标任务自身已有 review 文件的
假设，但独立 cleanup task 在清理结束前没有自身 review。

**New Behavior**: TASK-114 以 TASK-113 的完成审计和本变更的可执行门禁作为前置行为
基线；自身按 Fast、完整差异自审、只读审计和 Final 顺序完成。

### TASK-015 历史迁移门禁的前向兼容

**Previous Behavior**: TASK-015 质量测试永久断言仓库迁移总数精确等于 13，导致 Phase 2
依法追加 0014 至 0020 后完整 backend 回归失败。

**New Behavior**: TASK-015 继续显式验证 0001 至 0013 的 13 份 Phase 1 迁移全部存在，
但允许后续任务以前向迁移扩展仓库；TASK-114 基线独立精确捕获当前 20 份迁移及摘要。

**Requirements**:

- REQ-CHG-153: 历史阶段质量门禁必须验证自身迁移集合仍为当前集合的子集，不得把
  阶段结束时的全仓数量变成阻止后续前向迁移的永久上限。

**Acceptance Criteria**:

- [x] TASK-015 与 TASK-114 质量测试同时通过，且 0001 至 0020 的摘要受 TASK-114
  清理前后基线保护。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| TASK-114 / Phase 2 任务索引 | MODIFIED | LOW |
| Python 清理 manifest 与质量脚本 | ADDED | LOW |
| TASK-015 历史质量测试 | MODIFIED | LOW |
| 测试 README / 追踪说明 | MODIFIED | LOW |
| 产品 API / Schema / migrations / Cloud115 协议 | UNCHANGED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。TASK-114、Phase 2 任务索引、追踪说明、质量脚本和
测试 README 在 TASK-114 同一中文提交中同步。

## Testing Strategy

- 在卫生修改前捕获 `.planning/TASK-114/cleanup-baseline-before.json`。
- 运行 TASK-015/TASK-114 质量测试、锁定 Ruff、57 文件 mypy、完整 Fast 和 TASK-113 E2E。
- 审计收敛后捕获 after 基线并比较，最后运行一次无参数 Compose Final。
- 检查 NOTICE、协议 fixture、`real115` marker 和默认不访问真实 115 的边界。

## Rollback Plan

TASK-114 提交前可整体回退本变更、质量入口和卫生差异。提交后若范围或工具门禁需要
调整，必须以前向变更规格更新；不得删除等价分区或缩小测试来绕过失败。
