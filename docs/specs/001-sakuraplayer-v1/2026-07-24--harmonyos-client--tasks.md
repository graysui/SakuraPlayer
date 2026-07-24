# 任务列表：HarmonyOS 客户端

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**生成日期**: 2026-07-24

**语言**: ArkTS / ArkUI / HarmonyOS API 24

## 代码库与平台分析摘要

- 使用 DevEco Studio 6.1.1 Release 6.1.1.280、SDK 6.1.1(24)、Hvigor 6.24.2、ohpm 6.1.2.268、Node 18.20.1。
- 新建 Stage 模型 entry HAP，`compileSdkVersion/targetSdkVersion=6.1.1(24)`；使用 Navigation/NavPathStack 和 ArkTS V2 状态。
- 网络使用 Network Kit，令牌使用 Asset Store Kit，播放使用 Media Kit `AVPlayer`，测试使用 Hypium/UiTest。
- AC-006 和 AC-131 是进入门禁，不生成业务实现任务。TASK-301 只建立最小 Stage/签名探针工程，TASK-312 必须在 TASK-302 及后续功能开发前完成真实设备验收。

## 任务索引

| ID | 标题 | 主要焦点 | 依赖 | 外部风险 |
|---|---|---|---|---|
| [TASK-301](tasks/TASK-301.md) | API 24 Stage 工程与签名侧载基线 | DevEco/Hvigor/ohpm、GPLv3 | TASK-213,TASK-214 | 是 |
| [TASK-312](tasks/TASK-312.md) | HarmonyOS API 24 真机前置门禁 | 固定 UA、302、Range、HLS、MKV、ASS | TASK-301,TASK-213,TASK-214 | 是 |
| [TASK-302](tasks/TASK-302.md) | Asset Store 认证、HTTP、WebSocket 与快照 | 后端地址、bootstrap、ArkTS typed DTO | TASK-301,TASK-312,TASK-013 | 否 |
| [TASK-303](tasks/TASK-303.md) | Navigation、底部 Tab、主题与搜索 | ArkUI V2、三入口、角标 | TASK-302 | 否 |
| [TASK-304](tasks/TASK-304.md) | 媒体库网格、筛选与进度 | LazyForEach/Grid、六分类 | TASK-303 | 否 |
| [TASK-305](tasks/TASK-305.md) | 日/周/月/TOP250 排行榜 | 年份、快照、分页 | TASK-303 | 否 |
| [TASK-306](tasks/TASK-306.md) | 女优列表、详情与写真 | 名称/别名、收藏、LRU 图片 | TASK-303 | 是 |
| [TASK-307](tasks/TASK-307.md) | 影片详情、多来源与收藏 | 聚合详情、来源标签、进度 | TASK-304,TASK-306 | 否 |
| [TASK-308](tasks/TASK-308.md) | 115 扫码、缓存、设置与诊断 | QR、TTL、任务操作、通知 | TASK-302,TASK-112 | 是 |
| [TASK-309](tasks/TASK-309.md) | 播放请求与 60 秒全屏等待 | bindContentCover、取消、后台继续 | TASK-307,TASK-308 | 否 |
| [TASK-310](tasks/TASK-310.md) | AVPlayer 原画/HLS、固定 UA 与 seek | XComponent、302、Range、模式 | TASK-309,TASK-109 | 是 |
| [TASK-311](tasks/TASK-311.md) | 字幕、音轨、倍速、进度与生命周期 | 私有缓存、ASS、自动续播 | TASK-310,TASK-110,TASK-111 | 是 |
| [TASK-313](tasks/TASK-313.md) | HarmonyOS 端到端验收 | AC-003/132、完整用户旅程 | TASK-302..312 | 是 |
| [TASK-314](tasks/TASK-314.md) | HarmonyOS 客户端清理 | specs-code-cleanup | TASK-313 | 否 |

## 数量检查

- 实现任务：11，未超过 15。
- E2E：2（前置真机门禁与最终全旅程）。
- 清理：1。

## 文件冲突结论

TASK-301 创建 Stage/Hvigor/ability/route skeleton 和最小签名探针；TASK-312 只拥有前置真机探针与证据。各功能任务只编辑独立 feature 目录，TASK-303 统一拥有 Navigation 组合根。所有事件监听使用可注销的命名回调。
