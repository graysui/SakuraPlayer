# Change Specification: TASK-326 GFriends 女优资料恢复

## 背景

真实 `actor-mapping.xml` 已出现 `verified="0"` 条目。现有解析器只接受 `verified="1"`，因此会把整个有效 XML 判为 `provider_snapshot_invalid`，Actor Mapping 无法形成 current 快照。与此同时，首次 GFriends 快照可能在尚无已刮削 Actor 时完成，得到空的派生资产；旧请求失败后，首次启动逻辑又会因为历史请求存在而不再补发，导致连接探活可用但女优映射长期为 unknown，既有女优也没有中文简介、头像和写真。

## 变更

- REQ-CHG-318：新增 TASK-326，依赖 TASK-009、TASK-217、TASK-306 和 TASK-325，统一修复真实 Actor Mapping 兼容、既有女优资料重建和 Docker 原地升级恢复。
- REQ-CHG-319 / AC-049/050：Actor Mapping 的可选 `verified` 属性只接受上游已观察到的枚举字符串 `0` 或 `1`；两者都不改变唯一身份匹配规则，也不作为创建、合并或信任 Actor 身份的依据。其他值、未知属性、DTD、实体或非法结构继续拒绝整个候选快照。
- REQ-CHG-320 / AC-049：新增一次性前向数据迁移。升级时若 Actor Mapping 或 GFriends 任一 current 快照缺失，且没有 queued/claimed 快照请求，则只补入一个确定性 repair 请求；已有活动请求或两个 current 快照齐全时不重复入队。
- REQ-CHG-321 / AC-050/051：repair 请求仍通过既有 worker、固定 HTTPS 来源、完整解析和原子激活执行。Actor Mapping 成功后先重建既有 Actor 的中文名、简介和权威别名，随后 GFriends 使用重建后的全部权威名称重新生成头像/写真 URL 派生行；相同摘要也必须重新应用，而不是仅复用快照头。
- REQ-CHG-322 / AC-052/053：迁移和重建不得删除或重建 PostgreSQL，不得覆盖加密设置、影片、演员、收藏、已刮削关系、`data/`、`secrets/` 或永久目录图片。GFriends 仍只保存安全 URL，不下载或镜像 Content 图片。

## 范围与安全

- 不放宽 Actor Mapping 的元素、属性名、字段长度、`tmdb_id`、XXE 或唯一匹配边界；只把 `verified` 值域从单值 `1` 修正为上游实际布尔枚举 `0|1`。
- 一次性迁移只创建 provider snapshot queue 事实，不直接访问网络；外部下载仍由 worker 执行，并保持单源失败时最近成功快照可用。
- 默认测试使用固定 XML/JSON 与 PostgreSQL 隔离数据库，不访问真实 GFriends、JavDB 写操作、115 或付费 AI。
- 每周日 05:00 的常规刷新和影片可选 stage 语义保持不变；本变更不在每个影片子进程重复解析 20 MiB 级全量索引。

## 回滚

发布前可整体回退 TASK-326。发布后回滚代码或迁移不得删除已激活快照、已重建的 Actor 资料、GFriends URL、影片数据、设置或持久目录；repair 请求本身可按确定性 ID 从队列审计中移除。

## 验证边界

- 单元测试覆盖 `verified="0"` 接受、`verified="1"` 兼容和其他值继续拒绝。
- provider 测试覆盖相同 GFriends 摘要在既有 Actor 出现后仍重新应用并生成 profile/gallery。
- PostgreSQL 迁移测试覆盖旧 failed 请求 + 缺失 Actor Mapping current 的升级恢复、活动请求去重、双 current 跳过和业务数据保持不变。
- API 投影回归覆盖 Actor Mapping 简介、GFriends profile 与 gallery 仍通过既有安全 DTO 返回。
