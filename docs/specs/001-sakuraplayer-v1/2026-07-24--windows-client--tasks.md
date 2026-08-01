# 任务列表：Windows 客户端

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**生成日期**: 2026-07-24

**语言**: Dart / Flutter / media_kit

**实施与验证流程**: [统一实施与验证工作流](implementation-workflow.md)

## 代码库分析摘要

- 新建 `windows/` Flutter 3.29.2 工程，只启用 Windows 平台。
- 参考项目的 feature-first、聚合详情、桌面 Shell 和 `ThrottlingPlayer`，统一使用 Riverpod，不保留 Provider/ChangeNotifier 混用。
- 不移植外部播放器、时间轴缩略图、下载器、永久媒体库、Android/Web 等平台代码。

## 任务索引

| ID | 标题 | 主要焦点 | 依赖 | 外部风险 |
|---|---|---|---|---|
| [TASK-201](tasks/TASK-201.md) | Flutter Windows 脚手架、主题与认证壳 | 工具链、Riverpod、路由、GPLv3 | TASK-114 | 否 |
| [TASK-202](tasks/TASK-202.md) | API、令牌、事件与快照基础 | 后端地址、bootstrap、Dio、WS | TASK-201,TASK-013 | 否 |
| [TASK-203](tasks/TASK-203.md) | 桌面 Shell、全局搜索与缓存角标 | 左栏、顶部工具、路由 | TASK-202 | 否 |
| [TASK-204](tasks/TASK-204.md) | 媒体库网格、筛选与进度卡片 | 六分类、标签、大小、分页 | TASK-203 | 否 |
| [TASK-205](tasks/TASK-205.md) | 日/周/月/TOP250 排行榜 | 本地快照、年份筛选 | TASK-204 | 否 |
| [TASK-206](tasks/TASK-206.md) | 女优列表、详情与写真 | 名称/别名、收藏、图库缓存 | TASK-204 | 是 |
| [TASK-207](tasks/TASK-207.md) | 影片详情、多来源与收藏 | 聚合资料、typed route、来源选择与收藏 | TASK-204,TASK-206 | 否 |
| [TASK-208](tasks/TASK-208.md) | 115 扫码、缓存管理、设置与诊断 | QR、TTL、任务操作、脱敏设置；[客户端边界](contracts/windows-settings-cache-client.md) | TASK-202,TASK-112 | 是 |
| [TASK-209](tasks/TASK-209.md) | 播放请求、全屏等待与通知 | 60 秒锁定、排队、后台完成；[客户端契约](contracts/windows-play-request-client.md)、[ADR-004](../adr/ADR-004-windows-cache-notifications.md) | TASK-207,TASK-208 | 否 |
| [TASK-210](tasks/TASK-210.md) | media_kit 原画/HLS 播放器 | 候选选择、ready 播放、固定 UA、302、seek 合并、模式；[客户端契约](contracts/windows-playback-client.md) | TASK-209,TASK-109 | 是 |
| [TASK-211](tasks/TASK-211.md) | 字幕、音轨、倍速与影片进度 | libass、私有缓存、自动续播 | TASK-210,TASK-110,TASK-111 | 是 |
| [TASK-212](tasks/TASK-212.md) | Windows 私有安装包与真实验收工具 | release、许可证、显式 real-115 suite | TASK-201..211 | 是 |
| [TASK-213](tasks/TASK-213.md) | Windows E2E 与真实 115 门禁 | AVdb 现行资产名/manifest、Cloud115 能力域、外置字幕证据豁免、AC-130 流程 | TASK-201..212,TASK-113 | 是 |
| [TASK-214](tasks/TASK-214.md) | Windows 客户端清理 | specs-code-cleanup | TASK-213 | 否 |

## 数量检查

- 实现任务：12，未超过 15。
- E2E：1。
- 清理：1。

## 文件冲突结论

TASK-201 创建可构建的 Windows debug 工程、应用组合根和各 feature 空入口；允许提交 Flutter 生成的原生 runner、CMake、插件注册、工程元数据与锁文件。TASK-202 至 TASK-211 各自拥有 feature 目录，TASK-202 替换真实会话状态，TASK-203 统一拥有最终 Shell/route 聚合。TASK-212 独占 Windows release、私有安装包、产物许可证核验和显式验收配置。TASK-201 typed routes 使用手写强类型目标，不引入路由代码生成依赖。
