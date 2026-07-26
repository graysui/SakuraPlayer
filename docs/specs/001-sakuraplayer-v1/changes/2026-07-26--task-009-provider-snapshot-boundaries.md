# Change Specification: TASK-009 提供方快照安全与重建边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-049 至 AC-053 要求每周刷新 Actor Mapping 与 GFriends、保留最近成功快照并只关联唯一演员，但原任务没有冻结下载上限、路径语法、调度时刻、快照激活、身份匹配和陈旧资产清理规则。本变更补齐 TASK-009 的可执行安全与一致性边界，不改变外部可见功能。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 0 |
| REMOVED | 0 |

## ADDED

### Actor Mapping 与 GFriends 安全快照

**Requirements**:

- REQ-CHG-062: 固定 Actor Mapping URL 为 `https://raw.githubusercontent.com/li-peifeng/Jav-Actors-Mapping/main/actor-mapping.xml`，GFriends Filetree URL 为 `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Filetree.json`，内容基址为 `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content`；不接受运行配置或上游载荷覆盖。
- REQ-CHG-063: Actor Mapping 正文最多 16 MiB，Filetree 正文最多 32 MiB；流式读取超限立即停止。下载最多跟随 3 次重定向，每一跳都必须保持 HTTPS、精确小写主机、默认端口、无 userinfo/query/fragment，并分别保持固定资产路径。
- REQ-CHG-064: Actor Mapping 使用 `defusedxml` 0.7.1，拒绝 DTD、实体和外部网络；只接受 `actor-mapping/actor/a` 结构以及已声明属性。Filetree 只读取 `Content/<目录>/<别名文件名>` 三层映射，最多 500,000 个叶子。
- REQ-CHG-065: GFriends 目录、键和值必须是非空相对单段名称，拒绝段值 `.`/`..`、斜杠、反斜杠、scheme、绝对路径和 NUL；值只允许 `.jpg/.png` 加可选的单个数字 `t` query。连续点号可作为普通文件名内容。最终 URL只能由固定 Content 基址和百分号编码后的受校验段生成。
- REQ-CHG-066: 下载文件写入同目录临时文件，完成大小、结构和 SHA-256 验证并 `flush/fsync` 后原子替换。数据库只激活完整有效文件；同摘要刷新幂等复用。单源失败保留该源最近成功快照，另一源可以独立成功。
- REQ-CHG-067: Actor Mapping 只能以当前 JavDB 名称和 `authority=javdb` 别名唯一命中既有 Actor；0 个或多个 Actor 均丢弃，禁止按姓名创建、合并或改写 `javdb_id`。命中后写 `name_zh`、可用中文简介和 `authority=actor_mapping` 别名；空字段不清除既有非空资料。
- REQ-CHG-068: 每次成功 Actor Mapping 重建只全量协调 `authority=actor_mapping` 别名，保留 JavDB 别名。同一规范名已由 JavDB 保存时不建立重复 mapping 行；用户搜索词永不进入别名表。
- REQ-CHG-069: GFriends 使用 Actor 当前中日文名和全部权威别名构建多值索引；名称只命中一个 Actor 且同一最终 URL 不跨 Actor 时才关联。每个 Actor 按 URL 排序后的首张图为 `profile`，其余为 `gallery`；一次重建原子替换全部派生资产，使唯一变歧义、删除和 URL 改动不会留下陈旧行。
- REQ-CHG-070: scheduler 在每周日 05:00 `Asia/Shanghai` 以固定 job ID `provider_snapshots_weekly` 持久入队一次全局请求；scheduler 不访问外部网络。worker 使用 PostgreSQL claim/lease 执行，重复 slot 幂等，崩溃可回收同一请求，不为明确失败自动创建新请求。
- REQ-CHG-071: `actor_map` 和 `gfriends` 影片可选 stage 只验证相应最近成功快照存在；没有快照时记录 `provider_snapshot_unavailable` warning，不重复解析全量上游文件，也不阻断已提交 JavDB 核心。
- REQ-CHG-072: 默认自动测试仅使用固定 XML/JSON fixture 与 fake HTTP，不访问真实 GitHub Raw 或 GFriends Content；容量测试使用生成数据但不得镜像真实图片。

**Acceptance Criteria**:

- [x] 精确 URL、三跳重定向、16/32 MiB、结构、XXE 和路径穿越测试通过。
- [x] 两个快照独立激活，失败和损坏输入继续使用对应最近成功文件。
- [x] Actor Mapping 只唯一关联既有 JavDB Actor，重建保留 JavDB 别名并清理陈旧 mapping 别名。
- [x] GFriends 对 0/1/多个 Actor、跨 Actor 重复 URL、删除和唯一变歧义执行原子全量重建。
- [x] 周日 05:00 只持久入队，worker claim/lease 执行且重复 slot 幂等。

**Impact**: TASK-009、元数据契约、运行配置、错误码、数据模型、scheduler、worker、迁移和测试；Breaking: NO，相关 provider 尚未实现。

## MODIFIED

无。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| Actor Mapping/GFriends 下载与解析 | ADDED | HIGH |
| 快照请求队列与 worker consumer | ADDED | MEDIUM |
| 演员别名和 GFriends 资产重建 | ADDED | HIGH |
| defusedxml 0.7.1 | ADDED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-009 的依赖或 AC 映射。契约、实现、测试、迁移和任务状态仍在 TASK-009 的一次中文提交中交付。

## Testing Strategy

- 单元测试覆盖固定 URL、重定向、上限、XXE、JSON 层级、合法连续点号和非法路径段。
- SQLite 自包含测试覆盖别名和资产重建的 0/1/多匹配、陈旧清理与幂等。
- PostgreSQL 集成测试覆盖 partial unique current、claim/lease、重复 slot、并发重建和迁移。
- Final 使用隔离 Compose，不访问真实 GitHub Raw 或图片内容。

## Rollback Plan

TASK-009 提交前可整体回退本变更和实现。提交后若需改变地址、放宽上限或匹配规则，必须新增 Delta 并补安全与陈旧数据回归测试。
