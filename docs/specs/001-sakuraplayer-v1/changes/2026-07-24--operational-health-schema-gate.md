# Change Specification: 运维健康与 Schema 门禁契约

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-001 要求 API、worker、scheduler 和 PostgreSQL 提供健康检查，并在未知 Schema 下拒绝启动，但现有 OpenAPI、错误码和任务文件没有冻结探针路径、ready 语义或启动失败分类。本变更只补齐部署运维契约，不新增业务 API。

## ADDED

### 内部运维健康探针

- API 匿名提供 `/health/live` 与 `/health/ready`，两者不属于 `/api/v1` 业务契约且不进入 OpenAPI。
- live 只证明 API 进程可响应；ready 还要求 PostgreSQL 可达且数据库 revision 集合与代码 Alembic head 集合完全一致。
- worker 和 scheduler 通过容器内 CLI 执行相同的配置、数据库和 Schema ready 检查，不新增 HTTP 端口。
- PostgreSQL 使用 `pg_isready`；所有探针响应和日志不得包含 DSN、secret 或 revision 值。

### Schema 启动错误分类

- `database_unavailable`: PostgreSQL 不可达。
- `schema_migration_required`: 空库未迁移或当前 revision 是代码迁移图中的已知旧版本。
- `schema_revision_unknown`: 非空无版本、revision 不在迁移图、领先、分叉或版本表异常。

## MODIFIED

### 初始迁移边界

`0001_initial_skeleton` 是空业务基线，只由 Alembic 维护版本表。TASK-001 不创建管理员、配置、目录、任务、缓存或播放业务表。迁移前置检查必须拒绝把非空无版本数据库直接 `stamp` 或升级为 SakuraPlayer 数据库。

## Impact

- 功能规格 AC-127
- `contracts/operational-health.md`
- 稳定错误码
- 架构 API 约定
- TASK-001 与追踪矩阵

Breaking: NO，产品代码尚未实施。

## Testing Strategy

- 单元测试覆盖 head、未迁移、已知旧版本、未知版本和数据库不可达。
- PostgreSQL 集成测试覆盖空库显式升级、重复升级和非空无版本拒绝。
- Compose 测试覆盖四组件健康、API loopback、PostgreSQL 不发布宿主端口和重启恢复。

## Rollback Plan

产品代码尚未实施，可整体回退本变更及其同步文件；不得只删除健康契约而保留实现或测试。
