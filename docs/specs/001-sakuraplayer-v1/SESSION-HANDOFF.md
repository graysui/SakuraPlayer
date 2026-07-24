# SakuraPlayer v1 新会话交接

**更新时间**: 2026-07-24

**当前阶段**: Phase 1 后端基础设施实施中；TASK-001、TASK-002 已完成，下一任务为 TASK-003。

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

## 2. Git 状态基线

已完成的文档提交：

```text
2cf0b2c 文档：冻结 SakuraPlayer v1 需求规格
7480775 文档：确定 SakuraPlayer v1 技术架构与接口契约
fcf8bdf 文档：拆分 SakuraPlayer v1 实施任务与追踪矩阵
```

本交接文件、运行契约和接口补强属于其后的实施准备提交。新会话先运行 `git status --short` 和 `git log -5 --oneline`，不得假设工作区干净。

## 3. 恢复状态

- **已完成任务**: TASK-001、TASK-002。
- **下一任务**: TASK-003 秘密加密与脱敏基础设施。
- **当前阻塞项**: 无；按任务依赖继续后端数据真相，不得跳到客户端或 115 实现。
- **未完成外部门禁**: TASK-213 Windows/真实 115 与 TASK-312 HarmonyOS API 24 真机门禁，仍保持未完成。

下一会话从 TASK-003 开始：

```text
/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-003.md"
```

完成 TASK-003 的实现、测试和评审后，按根目录 `AGENTS.md` 创建下一次中文 Git 提交。工作流级清理由 TASK-015 在后端基础 E2E 后统一执行。

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
