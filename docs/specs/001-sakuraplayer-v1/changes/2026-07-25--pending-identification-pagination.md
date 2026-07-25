# Change Specification: 待识别查询与关联确定性

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-028/029 和 OpenAPI 已要求待识别资源支持搜索、游标分页和手动关联，但尚未冻结搜索字段、稳定排序、cursor 绑定和关联并发语义。本变更补齐实现所需确定性，不增加公开字段或管理员能力。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### 安全游标分页与原子关联

**Requirements**:

- REQ-CHG-043: 待识别列表必须按 `imported_at DESC, id DESC` 稳定排序，cursor 必须是不透明、版本化并绑定 `identification_status` 和规范化查询词的键集游标；格式错误或跨查询复用返回 `validation_failed`。
- REQ-CHG-044: `q` 必须在去除首尾空白后，对 `title/raw_number` 做字面量、不区分大小写的包含搜索；当 `q` 是十进制整数时还可精确匹配 `external_post_id`。`%` 和 `_` 必须作为普通字符，不得直接成为 SQL 通配符。
- REQ-CHG-045: 手动关联必须在数据库行锁事务内只接受 `pending` 来源和已存在影片；成功后原子设置 `movie_id`、目标影片的 `normalized_number` 与 `identification_status=manual`。已关联来源返回 `source_already_identified`，来源缺失/拒绝返回 `source_not_found`，影片缺失返回 `resource_not_found`。
- REQ-CHG-046: 列表和关联响应不得包含磁力 envelope、详情/预览 URL、上游正文、字段错误或其他提交载荷。

**Acceptance Criteria**:

- [ ] 两页之间新增更晚来源不会造成旧 cursor 重复返回已见行；cursor 不能跨状态或查询词使用。
- [ ] 标题、原始番号、精确帖子 ID 搜索生效，`%/_` 按字面量处理。
- [ ] 匿名请求拒绝；关联成功、来源/影片不存在和重复关联返回稳定状态码。
- [ ] 响应字段严格匹配 `PendingResourceSource` 和 `MovieSource` 安全 schema。

**Impact**: TASK-005 待识别 service/API 和 OpenAPI 错误响应。

## MODIFIED

### OpenAPI 待识别端点

**Previous Behavior**: 已声明参数和成功响应，但没有搜索/排序描述，也没有列全认证、not-found 和 validation 响应。

**New Behavior**: 参数描述和标准失败响应与上述冻结行为一致。

**Requirements**:

- REQ-CHG-047: OpenAPI 必须完整表达待识别端点的认证、校验、not-found 与冲突响应。

**Acceptance Criteria**:

- [ ] OpenAPI 解析和路由测试覆盖新增响应。

**Impact**: `contracts/rest-api.openapi.yaml`；Breaking: NO。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 待识别 service/API | ADDED | MEDIUM |
| OpenAPI | MODIFIED | LOW |

## Task Synchronization

本变更直接由 TASK-005 交付，不创建独立 `TASK-CHG`。

## Testing Strategy

- PostgreSQL API 集成测试覆盖认证、搜索、游标绑定、分页和关联并发状态。
- 响应敏感字段黑名单测试覆盖磁力、URL 和上游载荷。

## Rollback Plan

客户端尚未实施，可与 TASK-005 API 整体回退；不得只回退 OpenAPI 而保留不同分页行为。
