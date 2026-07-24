# SakuraPlayer v1 新会话交接

**更新时间**: 2026-07-24

**当前阶段**: 规格、架构、契约和实施任务已冻结并完成实施前补强；产品代码尚未开始。

## 1. 当前成果

- 功能规格包含 135 条验收条件，需求到任务的映射见 `traceability-matrix.md`。
- 技术计划采用 FastAPI、PostgreSQL、Docker、Flutter Windows 和 HarmonyOS API 24 原生客户端。
- 57 个任务已拆为后端元数据、115 缓存播放、Windows 和 HarmonyOS 四个工作流。
- OpenAPI、WebSocket、错误码、115 端口、元数据提供方、运行配置和 AVdb 数据源契约均在 `contracts/`。
- Windows 真实 115 门禁通过后，才建立 HarmonyOS 最小探针；API 24 真机探针通过后才实施鸿蒙业务功能。

## 2. Git 状态基线

已完成的文档提交：

```text
2cf0b2c 文档：冻结 SakuraPlayer v1 需求规格
7480775 文档：确定 SakuraPlayer v1 技术架构与接口契约
fcf8bdf 文档：拆分 SakuraPlayer v1 实施任务与追踪矩阵
```

本交接文件、运行契约和接口补强属于其后的实施准备提交。新会话先运行 `git status --short` 和 `git log -5 --oneline`，不得假设工作区干净。

## 3. 下一步

从 `TASK-001` 开始，不得跳到客户端或 115 实现：

```text
/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-001.md"
```

完成 TASK-001 的实现、测试和评审后，按根目录 `AGENTS.md` 提交一次中文 Git，再进入 TASK-002。工作流级清理由 TASK-015 在后端基础 E2E 后统一执行。

## 4. 必读契约

| 开始内容 | 必读文件 |
|---|---|
| 工程与 Compose | `contracts/runtime-configuration.md`、`architecture.md`、`TASK-001.md` |
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
