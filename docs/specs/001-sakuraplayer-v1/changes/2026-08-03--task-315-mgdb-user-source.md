# Change Specification: TASK-315 MGDB 用户数据源

**Type**: Delta
**Date**: 2026-08-03
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

现有 AVdb Release 客户端在后端内置第三方主/备用仓库。本变更把资源数据源责任交给管理员：Windows 设置页输入 GitHub 仓库地址，后端以 `mgdb.source` 加密设置保存并在 worker 领取同步任务时读取。该地址只允许 HTTPS、GitHub 官方主机、无凭据/query/fragment 的仓库 URL；后端不再包含任何默认第三方仓库。现有 AVdb Release 资产、解密流程和磁力加密存储保持兼容，Windows 可见名称统一为 MGDB。

## MODIFIED

- AC-018：Release 仍使用既有资产名、manifest、PBKDF2/AES-GCM 边界，但仓库地址必须来自管理员已保存的 MGDB 数据源，未配置时不得发起网络请求。
- AC-019：由“后端固定主源+备用源”改为“单一管理员配置源”；用户切换源后，下载内容仍按 Release、文件集合、大小和 SHA-256 复用/校验，不再内置主备仓库或自动查询固定镜像。
- AC-031、AC-033 至 AC-036、AC-063 至 AC-071、AC-083：内部数据和数据库兼容命名保留 AVdb；Windows UI、筛选和同步展示称为 MGDB。磁力只作为后端加密资源载荷存在，不进入客户端设置响应、日志、事件或公开 DTO。
- TASK-208 设置契约增加 MGDB 数据源输入、版本 CAS、规范化回显和清除动作；不新增磁力输入框。

## ADDED

- REQ-CHG-257：`mgdb.source` 通过现有设置 AES-GCM envelope 保存，replace/clear 使用 `expected_version` 原子 CAS。
- REQ-CHG-258：数据源 URL 仅允许 `https://github.com/{owner}/{repo}` 或 `https://api.github.com/repos/{owner}/{repo}`，端口只能为空或 443，禁止 userinfo、query、fragment；服务端保存并回显规范化的 GitHub URL。
- REQ-CHG-259：worker 每次领取同步请求后读取最新 MGDB source；未配置返回 `mgdb_source_not_configured` 并完成安全失败收敛，来源变更不需要重启服务。
- REQ-CHG-260：Windows 所有 AVdb 可见文案改为 MGDB，内部 `avdb_*` 错误码、数据库表和 Release 资产名不变；磁力不增加任何前端显示或编辑能力。

## Task Synchronization

本变更新增独立 `TASK-315`，不修改已有鸿蒙 `TASK-301` 至 `TASK-314` 的依赖或所有权。同步更新功能规格、AVdb 数据源契约、运行配置契约、REST OpenAPI、Windows 设置契约、Windows 任务索引、任务文件和追踪矩阵。

## Testing Strategy

- 后端 Focused：来源 URL 校验、加密设置 CAS/解密、无来源不联网、动态 worker source、单来源 Release 发现和磁力/秘密脱敏。
- Windows Fast：Settings DTO/Gateway/Controller、MGDB 设置输入/清除、旧 AVdb 文案扫描、现有设置与库筛选回归。
- Final：后端相关测试、Flutter analyze/test 和 Windows debug build；默认不访问真实 GitHub、115、JavDB 写操作或付费 AI。

## Rollback Plan

实现提交前可整体回退本变更。实现后只能通过新的前向 Delta 调整来源协议，不能恢复后端内置第三方仓库。
