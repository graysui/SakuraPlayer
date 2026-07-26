# SakuraPlayer v1 新会话交接

**更新时间**: 2026-07-26

**当前阶段**: Phase 1 后端基础设施实施中；TASK-001 至 TASK-008 已完成，下一任务为 TASK-009。

## 1. 当前成果

- 功能规格包含 135 条验收条件，需求到任务的映射见 `traceability-matrix.md`。
- 技术计划采用 FastAPI、PostgreSQL、Docker、Flutter Windows 和 HarmonyOS API 24 原生客户端。
- 57 个任务已拆为后端元数据、115 缓存播放、Windows 和 HarmonyOS 四个工作流。
- OpenAPI、WebSocket、错误码、115 端口、元数据提供方、运行配置和 AVdb 数据源契约均在 `contracts/`。
- Windows 真实 115 门禁通过后，才建立 HarmonyOS 最小探针；API 24 真机探针通过后才实施鸿蒙业务功能。
- TASK-001 已交付 Python/FastAPI 后端骨架、显式 Alembic 迁移、Schema 启动门禁、五服务 Compose、四个持久卷和内部健康检查。
- 启动配置固定四用途 secret，生产三类进程缺失、格式错误、来源冲突或用途复用时拒绝启动；bootstrap secret 生命周期由已接受变更规格冻结。
- TASK-001 自动验证覆盖 44 项启动测试、14 项 PostgreSQL 集成测试、四组件健康、持久日志、重启恢复、ready 故障降级和项目级 Docker 资源清理。
- TASK-002 已交付唯一管理员、Argon2id 密码、类型化 JWT、可撤销 refresh 会话、统一 HTTP/WebSocket 授权依赖和 logout epoch 清理语义。
- 认证契约冻结 15 分钟 access、登录起 30 天 refresh 绝对期限、同客户端单活、重放撤销、条件 bootstrap header 与 43..512 字符规范 Base64URL 初始化口令。
- TASK-002 自动验证覆盖 95 项自包含测试、18 项 PostgreSQL 集成测试、真实认证 canary、敏感日志扫描、重启恢复、ready 故障降级和项目级 Docker 资源清理。
- TASK-003 已交付 AES-256-GCM 加密 envelope、内存测试 key provider、`encrypted_setting` PostgreSQL 仓储和版本 CAS，以及统一日志/API 错误脱敏。
- 加密记录使用独立设置密钥、随机 96-bit nonce、key ID、密文和版本；并发新建/更新均以数据库原子条件写入避免旧凭据覆盖新值。
- 脱敏覆盖多段 Cookie、磁力、Bearer/JWT、AI key、client secret、DSN、绝对/相对 URL query、异常 traceback 与结构化日志字段；异常 code 仅允许稳定小写蛇形码。
- TASK-003 自动验证覆盖 125 项自包含测试、21 项 PostgreSQL 集成测试、Compose 真实认证 canary、秘密日志扫描、服务重启、ready 故障降级恢复和资源清理。
- TASK-004 已交付 AVdb Release 主备发现、逐跳下载校验、PBKDF2/AES-GCM 文件式解密、类型化 13 字段行流、同步事实、租约恢复、调度生产者和 worker consumer 端口。
- AVdb request/run 使用 token、未过期租约和 PostgreSQL 行锁隔离旧 worker；同 Release 已提交目录按文件集合、大小和 SHA-256 安全复用，解密明文使用受管目录并支持崩溃后扫尾。
- TASK-004 自动验证覆盖 175 项自包含测试、28 项 PostgreSQL 集成测试、迁移、五服务健康、认证 canary、敏感日志扫描、重启、ready 降级恢复和资源清理。
- TASK-005 已交付六分类流式来源导入、标准/FC2 番号规范化、去重影片骨架、90 日历日/5000 唯一番号首批范围、无上限历史候选和待识别管理员关联。
- `resource_source` 以 `(website, external_post_id)` 唯一，磁力以 AES-GCM envelope 保存；全量同步仅 upsert 当前行，缺失的既有来源不删除、不禁用。待识别 API 使用字面搜索、绑定状态与查询的键集游标，响应不暴露磁力或上游载荷。
- TASK-005 自动验证覆盖 199 项自包含测试、35 项 PostgreSQL Fast 测试、289,858 行流式容量证据，以及 Compose Final 的 41 项完整测试、服务健康、迁移、重启和清理。
- TASK-006 已交付来源证据化叠加标签、事务性影片合并/拆分、安全管理员响应，以及 Resources 所有的 `SourceRejectionPort`。
- 来源拒绝会原子清空磁力 envelope 并保存不含敏感载荷的唯一事实；导入与拒绝使用同一来源事务锁，增量/全量同步不能复活已拒绝来源。
- TASK-006 自动验证覆盖 204 项自包含测试、45 项 PostgreSQL 集成测试、17,202 条破解分类基线、并发拒绝/导入、迁移、五服务健康、重启、ready 降级恢复、秘密扫描和资源清理。
- TASK-007 已交付 PostgreSQL 持久元数据 job/stage、固定三槽 supervisor、600 秒 Linux 进程组硬终止、五级优先级、initial/history 持久 seeder，以及完整/可选富化管理员 retry。
- 元数据 child 独立创建 Engine/Session/httpx Client；provider 未交付时任务保持 queued。失败不会自动重试，initial 配额在多 worker 下严格不超过 5000，失败前缀通过候选 anti-join 不阻塞 history。
- TASK-007 自动验证覆盖 246 项自包含测试、33 项 PostgreSQL Fast 测试、三路无 P0/P1/P2 只读审计，以及 Compose Final 的 63 项 PostgreSQL/运行测试、迁移、五服务健康、重启、ready 降级恢复、秘密扫描和资源清理。
- TASK-008 已交付 JavDB 精确番号核心导入、Actor/Tag 关系、DMM 纯文本简介富化、可选 AES-GCM 凭据和永久目录图片原子缓存。
- JavDB 核心短事务与 DMM/图片可选阶段隔离；图片仅允许精确 HTTPS 主机和三种格式，并限制 8 MiB、3 跳、12,000 单边和 40M 总像素，失败保留最近 ready 图片并进入显式富化重试。
- TASK-008 自动验证覆盖 293 项自包含测试、38 项 PostgreSQL Fast 测试、三路无剩余 P0/P1/P2 只读审计，以及 Compose Final 的 67 项 PostgreSQL/运行测试、迁移、五服务健康、重启恢复和资源清理。

## 1.1 当前任务门禁状态

- **当前任务门禁阶段**: TASK-008 已完成；下一任务为 TASK-009。
- **最近绿色快速门禁**: TASK-008 Fast 为 293 passed、7 deselected；TASK-008 PostgreSQL/Schema 为 38 passed；只读 compileall 与宿主 Docker 配置断言通过。
- **最终门禁状态**: TASK-008 Compose Final 尝试 1 通过；自包含 293 passed、7 deselected，PostgreSQL/Compose 67 passed、12 deselected；迁移、五服务健康、重启恢复和隔离资源清理全部完成。
- **执行流程**: 采用 [统一实施与验证工作流](implementation-workflow.md)，先 Focused/Fast，再只读审计，最后 Final；不使用 Superpowers 插件或 `superpowers:*` 技能，复杂任务继续使用 `planning-with-files-zh`。

## 2. Git 状态基线

已完成的文档提交：

```text
2cf0b2c 文档：冻结 SakuraPlayer v1 需求规格
7480775 文档：确定 SakuraPlayer v1 技术架构与接口契约
fcf8bdf 文档：拆分 SakuraPlayer v1 实施任务与追踪矩阵
```

本交接文件、运行契约和接口补强属于其后的实施准备提交。新会话先运行 `git status --short` 和 `git log -5 --oneline`，不得假设工作区干净。

## 3. 恢复状态

- **已完成任务**: TASK-001、TASK-002、TASK-003、TASK-004、TASK-005、TASK-006、TASK-007、TASK-008。
- **下一任务**: TASK-009 演员映射与 GFriends。
- **当前阻塞项**: 无。
- **未完成外部门禁**: TASK-213 Windows/真实 115 与 TASK-312 HarmonyOS API 24 真机门禁，仍保持未完成。

下一会话从 TASK-009 开始：

```text
/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-009.md"
```

完成 TASK-008 的实现、测试和评审后，按根目录 `AGENTS.md` 创建本次中文 Git 提交。工作流级清理由 TASK-015 在后端基础 E2E 后统一执行。

## 4. 必读契约

| 开始内容 | 必读文件 |
|---|---|
| 工程与 Compose | `contracts/runtime-configuration.md`、`contracts/operational-health.md`、`architecture.md`、`TASK-001.md` |
| AVdb 导入 | `contracts/avdb-source.md`、`TASK-004.md` |
| REST/客户端 | `contracts/rest-api.openapi.yaml`、`contracts/error-codes.md` |
| 实时状态 | `contracts/realtime-events.md` |
| 元数据 | `contracts/metadata-providers.md` |
| 115 与播放 | `contracts/cloud115-port.md` |
| 数据库 | `data-model.md` |

## 5. 本地原始资料

仓库根目录目前保留三份用户提供的未跟踪资料：

- `AVDB-DATABASE-GUIDE.md`
- `SakuraMedia-Windows-Android-播放与架构分析.md`
- `SakuraMedia-排行榜-女优-详情页分析.md`

它们是核验来源，不是实现契约。实现必须以 `docs/specs/` 中已提交的文档为准；不得在没有用户授权时把三份原始资料加入 Git。

## 6. 外部门禁

- TASK-213 需要真实 Windows、真实 115 账号和专属测试目录。
- TASK-312 需要 DevEco Studio 6.1.1.280、HarmonyOS SDK 6.1.1(24)、API 24 真机和 MKV/HLS/ASS 样本。
- 外部凭据不进入仓库、普通日志、测试快照或聊天输出。
