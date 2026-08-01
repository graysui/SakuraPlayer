# Change Specification: 实际体验内容恢复

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-217 建立真实 provider/ranking 快照后的 Release 体验发现：播放器只携带影片 ID 而未保留实际导航栈；DMM 在搜索页直接查找简介，没有进入精确番号详情页；JavDB 修复前的瞬时失败事实使日/周/月榜快照虽存在但不可见；诊断 DTO 已有失败计数而页面未显示。GFriends 当前快照和 Windows 直连图片均已验证可用，旧页面数据需显式刷新。本变更新增 TASK-222 收敛这些问题，TASK-214 继续保持 pending。

## ADDED

- REQ-CHG-264: Windows 从详情、等待页或缓存页进入播放器时必须使用应用内导航栈保存实际来源页面；播放器返回优先 pop 到该页面。直接深链或无可返回页面时只允许回到缓存页，不接受自由格式 return URL，也不得把播放能力、来源、Cookie、磁力或标题写入 route。
- REQ-CHG-265: DMM 简介必须先请求固定 `www.dmm.co.jp` 搜索页，从固定主机详情链接提取 CID，按规范化番号精确匹配后再请求详情页。rental 详情只读取 Product JSON-LD description，mono 详情只读取固定简介块；搜索未命中返回无简介，网络、状态、越界响应或结构变化返回 `dmm_upstream_error`。
- REQ-CHG-266: TASK-222 部署验证可使用既有管理员 `manual_retry` 语义，显式恢复当前 ranking snapshots 中最新 attempt 为 `javdb_upstream_error` 的唯一番号；`javdb_movie_not_found`、已有 active attempt 和已 `core_ready` 影片不得重试。该操作是一次显式运行恢复，不改变失败不自动重试规则。
- REQ-CHG-267: DMM 修复后的既有 `completed_with_warnings` 只允许通过既有 `retry-enrichment` 语义显式重试 `dmm`，不得自动重跑 JavDB 核心、其他富化或付费 AI；新任务正常使用修复后的 provider。
- REQ-CHG-268: Windows 元数据聚合进度在“已处理/总数”和当前最多 3 个番号之外增加“失败数量”；继续不得铺开逐任务番号列表。
- REQ-CHG-269: GFriends 验收以 current snapshot、API `profile_url` 投影和 Windows 图片下载三层证据为准。快照建立前已打开的女优页由现有刷新动作重载；不得为刷新旧页面而放宽唯一姓名/别名映射或 URL 白名单。

## MODIFIED

- REQ-CHG-270: TASK-214 增加 TASK-222 依赖；TASK-222 完成前不得开始 Windows 清理。

## Acceptance Criteria

- [ ] 详情立即 ready、等待期 ready 和缓存页播放均返回各自进入播放器前的页面；直接深链安全回缓存页。
- [ ] DMM 固定 fixture 覆盖搜索匹配、detail URL 解码、CID 精确匹配、rental/mono 简介、未找到和上游失败；真实只读 probe 返回 available。
- [ ] 正式当前榜单瞬时失败番号被显式恢复，日/周/月至少产生可见影片；永久未找到和已有 active attempt 不被重试。
- [ ] 既有 DMM warning 可显式进入仅 `dmm` 富化重试，新完成影片可保存原始简介。
- [ ] 诊断页显示失败数量和当前番号，不显示逐任务列表。
- [ ] 正式女优首屏刷新后，对有 `profile_url` 的条目创建私有缓存并显示头像；未匹配条目仍显示占位。

## Testing Strategy

- Flutter route/widget 覆盖详情、等待、缓存、直接深链返回，以及失败计数展示。
- DMM 使用 MockTransport/固定 fixture 覆盖两阶段请求、严格详情 URL/CID、响应上限和错误映射；默认测试不访问真实外部服务。
- PostgreSQL 聚焦验证显式恢复候选集合只包含当前榜单 transient failed，并通过现有队列方法创建新 attempt。
- Fast/Final 按统一流程运行；Final 后只执行无泄密 DMM/GFriends 只读 probe 和显式正式恢复核对。

## Rollback Plan

只能用新的前向变更调整播放返回或 provider 解析；不得恢复自由格式 return URL、搜索页直接取简介、失败自动重试或放宽 GFriends 匹配/URL 边界。
