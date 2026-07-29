# 任务列表：115 缓存与播放后端

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**生成日期**: 2026-07-24

**语言**: Python / FastAPI / PostgreSQL

**实施与验证流程**: [统一实施与验证工作流](implementation-workflow.md)

## 代码库分析摘要

- 可按固定 revision 和符号允许清单适配参考项目的 Cloud115 扫码、Cookie snapshot、目录、离线、原画/HLS 和小文件下载原语；TASK-102 才拥有数据库 CAS。
- 必须删除旧 MediaLibrary 永久库语义，改为单绑定、单专属缓存根和每任务目录。
- 资源拒绝、事件发布通过后端基础工作流发布的应用端口调用，不直接跨上下文改表。

## 任务索引

| ID | 标题 | 主要焦点 | 依赖 | 跨边界 | 外部风险 |
|---|---|---|---|---|---|
| [TASK-101](tasks/TASK-101.md) | Cloud115Port、适配器与 Fake | 精确 Protocol/DTO、snapshot、错误、fixture、来源声明 | TASK-015 | 否 | 是 |
| [TASK-102](tasks/TASK-102.md) | 扫码绑定、Cookie CAS 与缓存根 | 单账号、加密回写、`SakuraPlayer-Cache` | TASK-101 | 否 | 是 |
| [TASK-103](tasks/TASK-103.md) | 缓存任务状态机与 2/10 容量 | Schema、幂等、事务 claim | TASK-102 | 否 | 否 |
| [TASK-104](tasks/TASK-104.md) | 离线提交、对账、取消与等待语义 | 用户触发、60 秒、后台继续 | TASK-103 | 否 | 是 |
| [TASK-105](tasks/TASK-105.md) | 视频/字幕解析与媒体选择 | 广告排除、分段、真实大小、选择器 | TASK-104 | 否 | 是 |
| [TASK-106](tasks/TASK-106.md) | 确定性失败与来源拒绝集成 | 失效/违规、清磁力、拒绝端口 | TASK-104 | 否 | 是 |
| [TASK-107](tasks/TASK-107.md) | TTL、LRU、租约与安全清理 | 24h/1-168h/20、归属证明 | TASK-103,TASK-105 | 否 | 是 |
| [TASK-108](tasks/TASK-108.md) | 签名播放会话与原画 302 | 12h、固定 UA、owner、no-store | TASK-102,TASK-105,TASK-107 | 否 | 是 |
| [TASK-109](tasks/TASK-109.md) | 最高码率 HLS 兼容播放 | fallback、VIP/转码错误、模式 | TASK-108 | 否 | 是 |
| [TASK-110](tasks/TASK-110.md) | 字幕下载、音轨契约与生命周期 | 四格式、客户端私有缓存、清理信号 | TASK-105,TASK-108 | 否 | 是 |
| [TASK-111](tasks/TASK-111.md) | 影片级进度与播放心跳 | 跨端、自动续播、95%/2min | TASK-108 | 否 | 否 |
| [TASK-112](tasks/TASK-112.md) | 缓存事件、通知、诊断与恢复 | WS/REST、启动对账、操作 API | TASK-103..111 | 否 | 否 |
| [TASK-113](tasks/TASK-113.md) | 115 缓存播放后端 E2E | 状态化 Fake、生产服务组合和后端可观察闭环 | TASK-101..112 | 是 | 是 |
| [TASK-114](tasks/TASK-114.md) | 115 缓存播放后端清理 | 固定 manifest、Phase 2 等价门禁、specs-code-cleanup | TASK-113 | 否 | 否 |

## 数量检查

- 实现任务：12，未超过 15。
- E2E：1。
- 清理：1。

## 文件冲突结论

Cloud115 协议适配器只由 TASK-101 拥有，TASK-102 只编排扫码、加密绑定和 snapshot CAS；缓存状态、执行器、解析、清理、播放、字幕、进度和事件分别拥有独立模块文件。TASK-106 只调用 `SourceRejectionPort`，不修改资源接入表实现。TASK-113 仅扩展测试 Fake/E2E 和验证契约，通过现有 composition 组合多个上下文，不修改生产状态机、Schema 或公开 API。

TASK-114 的清理输入和行为等价门禁由 [TASK-114 清理范围与等价门禁](changes/2026-07-29--task-114-cleanup-gates.md) 冻结；默认验证不访问真实 115。
