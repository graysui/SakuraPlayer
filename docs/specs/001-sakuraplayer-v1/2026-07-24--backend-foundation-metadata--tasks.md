# 任务列表：后端基础与元数据

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**生成日期**: 2026-07-24

**语言**: Python / FastAPI / PostgreSQL

**实施与验证流程**: [统一实施与验证工作流](implementation-workflow.md)

## 代码库分析摘要

- 新建 `backend/`，遵循项目架构中的模块化单体和端口适配器结构。
- 参考 `avmedia` 的 JavDB/DMM/GFriends 实现，但不移植 Peewee、下载器、永久媒体库或视觉模块。
- 脚手架任务预先创建 composition root 和模块边界；后续任务只编辑自身目录，避免文件冲突。

## 任务索引

| ID | 标题 | 主要焦点 | 依赖 | 跨边界 | 外部风险 |
|---|---|---|---|---|---|
| [TASK-001](tasks/TASK-001.md) | 后端工程、Compose 与 Schema 门禁 | loopback、用途分离 secret、迁移、健康 | 无 | 否 | 否 |
| [TASK-002](tasks/TASK-002.md) | 唯一管理员认证与会话 | bootstrap token、Argon2id、JWT、refresh | TASK-001 | 否 | 否 |
| [TASK-003](tasks/TASK-003.md) | 秘密加密与脱敏基础设施 | AES-GCM、Docker Secret、日志错误 | TASK-001 | 否 | 否 |
| [TASK-004](tasks/TASK-004.md) | AVdb Release 下载、解密与同步 | 主备、SHA-256、PBKDF2/AES、调度 | TASK-001,TASK-003 | 否 | 是 |
| [TASK-005](tasks/TASK-005.md) | 六分类导入、番号与首次范围 | 29 万级导入、90 天/5000、待识别 | TASK-004 | 否 | 否 |
| [TASK-006](tasks/TASK-006.md) | 影片多来源、标签和拒绝标记 | 合并拆分、字幕/破解/4K/有码 | TASK-005 | 否 | 否 |
| [TASK-007](tasks/TASK-007.md) | 持久元数据队列与硬超时 | 3 子进程、600 秒、完整/富化重试 | TASK-001,TASK-005 | 否 | 否 |
| [TASK-008](tasks/TASK-008.md) | JavDB 核心、DMM 与永久图片 | core_ready、简介、图片 warning | TASK-003,TASK-007 | 否 | 是 |
| [TASK-009](tasks/TASK-009.md) | 演员映射与 GFriends | 周更、权威别名、唯一匹配 | TASK-008 | 否 | 是 |
| [TASK-010](tasks/TASK-010.md) | OpenAI 兼容翻译 | 保护字段、幂等、异步富化 | TASK-003,TASK-008 | 否 | 是 |
| [TASK-011](tasks/TASK-011.md) | 媒体库、搜索、详情与收藏 API | core_ready 查询、聚合详情 | TASK-006,TASK-008,TASK-009,TASK-010 | 否 | 否 |
| [TASK-012](tasks/TASK-012.md) | JavDB 排行榜快照 | 日/周/月/TOP250/年份 | TASK-007,TASK-008 | 否 | 是 |
| [TASK-013](tasks/TASK-013.md) | 管理设置、诊断与持久事件 | 设置、任务管理、REST snapshot/WS | TASK-002,TASK-003,TASK-007,TASK-011,TASK-012 | 否 | 否 |
| [TASK-014](tasks/TASK-014.md) | 后端基础与元数据 E2E | 全链路和 `[SEF]` 故障隔离 | TASK-001..013 | 否 | 是 |
| [TASK-015](tasks/TASK-015.md) | 后端基础与元数据清理 | specs-code-cleanup | TASK-014 | 否 | 否 |

## 数量检查

- 实现任务：13，未超过 15。
- E2E：1。
- 清理：1。

## 文件冲突结论

TASK-001 创建所有模块的空 composition skeleton；TASK-002 至 TASK-013 只填充各自模块和独立测试路径。TASK-013 负责事件网关和管理聚合，不修改其他任务的领域文件。TASK-014 只新增 E2E 文件。
