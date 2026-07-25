# SakuraPlayer v1 需求追踪矩阵

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**任务总索引**: [2026-07-24--sakuraplayer-v1--tasks.md](2026-07-24--sakuraplayer-v1--tasks.md)

## 映射规则

- `[I]` 对应规格中的 `[IMP]`，只列实际产出该行为的实现任务；自动验证细节保留在各实现任务和工作流 E2E 中。
- `[S]` 对应 `[SEF]`，只由可观察结果所属的 E2E 检查点验证，不创建实现任务。
- `[E]` 对应 `[EXT]`，只由需要真实外部系统的显式 E2E 门禁验证，不进入默认自动测试。
- 普通实现任务的 `provides` 和 Definition of Done 定义其产出角色；客户端任务消费公开契约，E2E 任务的 `ac-mapping` 表示验证范围而非实现所有权。一个 AC 映射多个任务时，不代表每个任务重复实现完整行为。
- 清理任务不承担新需求，因此不映射 AC。
- AC-133 的 bootstrap secret 启动依赖与管理员创建后失去权限的生命周期由 [Bootstrap Secret 生命周期澄清](changes/2026-07-24--bootstrap-secret-lifecycle.md) 冻结；TASK-001 负责启动校验，TASK-002 负责永久关闭初始化行为。
- AC-133 的 `X-Bootstrap-Token` 只在尚未初始化时必填；管理员存在检查必须先于 header/secret 校验，详见 [Bootstrap Header 条件校验](changes/2026-07-24--conditional-bootstrap-header.md)。
- AC-011/AC-012 的 JWT claim、refresh 轮换/重放、client instance、logout 与 session epoch 语义由 [认证会话生命周期补强](changes/2026-07-24--authentication-session-lifecycle.md) 冻结，并由 TASK-002 实现。
- AC-133 的 bootstrap token 熵、规范 Base64URL 编码和固定长度摘要比较由 [Bootstrap Token 熵与比较规范](changes/2026-07-24--bootstrap-token-entropy.md) 冻结。
- AC-127 的内部探针、容器健康检查与 Schema 门禁由 [运维健康与 Schema 门禁契约](contracts/operational-health.md) 冻结；TASK-001 负责基础门禁，TASK-013/TASK-112 负责后续任务恢复与诊断。
- 实施验证顺序由 [统一实施与验证工作流](implementation-workflow.md) 统一管理；该流程只约束执行与证据，不新增或删除 AC 映射。
- AC-028/AC-030 的标准番号、FC2、保守拒绝和固定样本由 [影片番号规范化输入边界](changes/2026-07-25--movie-number-normalization.md) 冻结，并由 TASK-005 实现。
- AC-026/AC-027 的 90 日历日边界、5000 截断、稳定排序和无上限历史候选由 [首批元数据范围边界与排序](changes/2026-07-25--initial-metadata-scope-ordering.md) 冻结，并由 TASK-005 输出、TASK-007 消费。
- AC-028/AC-029 的搜索字段、键集游标、安全响应和原子手动关联由 [待识别查询与关联确定性](changes/2026-07-25--pending-identification-pagination.md) 冻结，并由 TASK-005 实现。

## 逐条追踪

| 验收条件 | 类型 | 需求组 | 实现或 E2E 检查点 |
|---|---|---|---|
| `AC-001` | `[I]` | `REQ-001` | `TASK-002` |
| `AC-002` | `[I]` | `REQ-001` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-003` | `[S]` | `REQ-001` | `TASK-313` |
| `AC-004` | `[I]` | `REQ-001` | `TASK-002` |
| `AC-005` | `[I]` | `REQ-002` | `TASK-001`, `TASK-201`, `TASK-212` |
| `AC-006` | `[E]` | `REQ-002` | `TASK-312` |
| `AC-007` | `[I]` | `REQ-002` | `TASK-301` |
| `AC-008` | `[I]` | `REQ-002` | `TASK-001`, `TASK-201`, `TASK-212`, `TASK-301` |
| `AC-009` | `[I]` | `REQ-002` | `TASK-001`, `TASK-201`, `TASK-212`, `TASK-301` |
| `AC-010` | `[I]` | `REQ-003` | `TASK-002` |
| `AC-011` | `[I]` | `REQ-003` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-012` | `[I]` | `REQ-003` | `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-013` | `[I]` | `REQ-004` | `TASK-101`, `TASK-102`, `TASK-208`, `TASK-308` |
| `AC-014` | `[I]` | `REQ-004` | `TASK-003`, `TASK-102` |
| `AC-015` | `[I]` | `REQ-004` | `TASK-003`, `TASK-102` |
| `AC-016` | `[I]` | `REQ-004` | `TASK-101`, `TASK-102`, `TASK-208`, `TASK-308` |
| `AC-017` | `[I]` | `REQ-004` | `TASK-003`, `TASK-101` |
| `AC-018` | `[I]` | `REQ-005` | `TASK-004` |
| `AC-019` | `[I]` | `REQ-005` | `TASK-004` |
| `AC-020` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005` |
| `AC-021` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005` |
| `AC-022` | `[I]` | `REQ-005` | `TASK-004`, `TASK-005` |
| `AC-023` | `[S]` | `REQ-005` | `TASK-014` |
| `AC-024` | `[I]` | `REQ-005` | `TASK-004` |
| `AC-025` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-026` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-027` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-028` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-029` | `[I]` | `REQ-006` | `TASK-005` |
| `AC-030` | `[I]` | `REQ-007` | `TASK-005` |
| `AC-031` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307` |
| `AC-032` | `[I]` | `REQ-007` | `TASK-006` |
| `AC-033` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307` |
| `AC-034` | `[I]` | `REQ-007` | `TASK-006`, `TASK-207`, `TASK-307` |
| `AC-035` | `[I]` | `REQ-007` | `TASK-006`, `TASK-105`, `TASK-207`, `TASK-307` |
| `AC-036` | `[I]` | `REQ-007` | `TASK-006`, `TASK-106` |
| `AC-037` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-038` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-039` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-040` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-041` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-042` | `[I]` | `REQ-008` | `TASK-007`, `TASK-008` |
| `AC-043` | `[I]` | `REQ-008` | `TASK-007` |
| `AC-044` | `[I]` | `REQ-009` | `TASK-008` |
| `AC-045` | `[I]` | `REQ-009` | `TASK-008` |
| `AC-046` | `[I]` | `REQ-009` | `TASK-008`, `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-047` | `[I]` | `REQ-009` | `TASK-008` |
| `AC-048` | `[I]` | `REQ-009` | `TASK-008` |
| `AC-049` | `[I]` | `REQ-010` | `TASK-009` |
| `AC-050` | `[I]` | `REQ-010` | `TASK-009` |
| `AC-051` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-306` |
| `AC-052` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-306` |
| `AC-053` | `[I]` | `REQ-010` | `TASK-009`, `TASK-206`, `TASK-306` |
| `AC-054` | `[I]` | `REQ-011` | `TASK-010` |
| `AC-055` | `[I]` | `REQ-011` | `TASK-010` |
| `AC-056` | `[I]` | `REQ-011` | `TASK-010` |
| `AC-057` | `[I]` | `REQ-011` | `TASK-010` |
| `AC-058` | `[S]` | `REQ-011` | `TASK-014` |
| `AC-059` | `[I]` | `REQ-012` | `TASK-201`, `TASK-203`, `TASK-303` |
| `AC-060` | `[I]` | `REQ-012` | `TASK-203`, `TASK-303` |
| `AC-061` | `[I]` | `REQ-012` | `TASK-203`, `TASK-303` |
| `AC-062` | `[I]` | `REQ-012` | `TASK-201`, `TASK-303` |
| `AC-063` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-304` |
| `AC-064` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-304` |
| `AC-065` | `[I]` | `REQ-013` | `TASK-011`, `TASK-203`, `TASK-303` |
| `AC-066` | `[I]` | `REQ-013` | `TASK-011`, `TASK-203`, `TASK-303` |
| `AC-067` | `[I]` | `REQ-013` | `TASK-011`, `TASK-204`, `TASK-304` |
| `AC-068` | `[I]` | `REQ-013` | `TASK-011`, `TASK-111`, `TASK-204`, `TASK-207`, `TASK-211`, `TASK-304`, `TASK-307`, `TASK-311` |
| `AC-069` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-070` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-071` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-072` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-073` | `[I]` | `REQ-014` | `TASK-012`, `TASK-205`, `TASK-305` |
| `AC-074` | `[I]` | `REQ-015` | `TASK-011`, `TASK-207`, `TASK-307` |
| `AC-075` | `[I]` | `REQ-015` | `TASK-011`, `TASK-206`, `TASK-306` |
| `AC-076` | `[I]` | `REQ-015` | `TASK-011`, `TASK-206`, `TASK-306` |
| `AC-077` | `[I]` | `REQ-015` | `TASK-011`, `TASK-204`, `TASK-206`, `TASK-207`, `TASK-304`, `TASK-306`, `TASK-307` |
| `AC-078` | `[I]` | `REQ-015` | `TASK-011`, `TASK-207`, `TASK-307` |
| `AC-079` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-080` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-081` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-082` | `[I]` | `REQ-016` | `TASK-102` |
| `AC-083` | `[I]` | `REQ-017` | `TASK-103` |
| `AC-084` | `[I]` | `REQ-017` | `TASK-103`, `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-085` | `[I]` | `REQ-017` | `TASK-103`, `TASK-209`, `TASK-309` |
| `AC-086` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-087` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-088` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-089` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-090` | `[I]` | `REQ-017` | `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-091` | `[I]` | `REQ-017` | `TASK-103`, `TASK-104`, `TASK-209`, `TASK-309` |
| `AC-092` | `[I]` | `REQ-018` | `TASK-105` |
| `AC-093` | `[I]` | `REQ-018` | `TASK-105` |
| `AC-094` | `[I]` | `REQ-018` | `TASK-107`, `TASK-208`, `TASK-308` |
| `AC-095` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-096` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-097` | `[I]` | `REQ-018` | `TASK-104`, `TASK-107` |
| `AC-098` | `[I]` | `REQ-018` | `TASK-107` |
| `AC-099` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-100` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-101` | `[I]` | `REQ-019` | `TASK-109`, `TASK-210`, `TASK-310` |
| `AC-102` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-103` | `[I]` | `REQ-019` | `TASK-109`, `TASK-210`, `TASK-310` |
| `AC-104` | `[I]` | `REQ-019` | `TASK-108`, `TASK-201`, `TASK-210`, `TASK-310` |
| `AC-105` | `[I]` | `REQ-019` | `TASK-108`, `TASK-210`, `TASK-310` |
| `AC-106` | `[I]` | `REQ-019` | `TASK-210`, `TASK-310` |
| `AC-107` | `[I]` | `REQ-020` | `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-108` | `[I]` | `REQ-020` | `TASK-105`, `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-109` | `[I]` | `REQ-020` | `TASK-105`, `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-110` | `[I]` | `REQ-020` | `TASK-110`, `TASK-211`, `TASK-311` |
| `AC-111` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-112` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-113` | `[I]` | `REQ-020` | `TASK-111`, `TASK-211`, `TASK-311` |
| `AC-114` | `[I]` | `REQ-020` | `TASK-110`, `TASK-111`, `TASK-210`, `TASK-211`, `TASK-310`, `TASK-311` |
| `AC-115` | `[I]` | `REQ-021` | `TASK-013`, `TASK-112`, `TASK-202`, `TASK-302` |
| `AC-116` | `[I]` | `REQ-021` | `TASK-013`, `TASK-112`, `TASK-202`, `TASK-302` |
| `AC-117` | `[I]` | `REQ-021` | `TASK-112`, `TASK-202`, `TASK-209`, `TASK-302`, `TASK-309` |
| `AC-118` | `[I]` | `REQ-021` | `TASK-112`, `TASK-203`, `TASK-208`, `TASK-303`, `TASK-308` |
| `AC-119` | `[I]` | `REQ-022` | `TASK-013`, `TASK-112`, `TASK-208`, `TASK-308` |
| `AC-120` | `[I]` | `REQ-022` | `TASK-003`, `TASK-013`, `TASK-208`, `TASK-308` |
| `AC-121` | `[I]` | `REQ-022` | `TASK-013`, `TASK-112`, `TASK-208`, `TASK-308` |
| `AC-122` | `[I]` | `REQ-022` | `TASK-007`, `TASK-013`, `TASK-112`, `TASK-208`, `TASK-308` |
| `AC-123` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-124` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-125` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-126` | `[I]` | `REQ-023` | `TASK-001` |
| `AC-127` | `[I]` | `REQ-023` | `TASK-001`, `TASK-013`, `TASK-112` |
| `AC-128` | `[I]` | `REQ-024` | `TASK-003`, `TASK-013`, `TASK-101`, `TASK-212` |
| `AC-129` | `[I]` | `REQ-024` | `TASK-013`, `TASK-101`, `TASK-212` |
| `AC-130` | `[E]` | `REQ-024` | `TASK-213` |
| `AC-131` | `[E]` | `REQ-024` | `TASK-312` |
| `AC-132` | `[S]` | `REQ-024` | `TASK-014`, `TASK-113`, `TASK-213`, `TASK-313` |
| `AC-133` | `[I]` | `REQ-025` | `TASK-001`, `TASK-002`, `TASK-202`, `TASK-302` |
| `AC-134` | `[I]` | `REQ-025` | `TASK-001` |
| `AC-135` | `[I]` | `REQ-025` | `TASK-202`, `TASK-302` |
