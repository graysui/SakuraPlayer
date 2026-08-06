# Change Specification: 媒体库排序改用影片发行日期

**Type**: Delta
**Date**: 2026-08-06
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-064 冻结媒体库"发布日期"排序与展示键为"满足筛选的 AVdb 来源最新发布日期"，即 `MAX(ResourceSource.publish_date)`（资源帖发帖日期）。实测 4120 部 core_ready 影片只有 199 个不同的发帖日期键，且老片新帖现象严重：SILK-052（2014 年发行）因 2026-08-01 新资源帖排在 2026 新片中间，SSNI-217 来源日期跨度 2018~2026。媒体库列表显示的"发布日期"与详情页"发布日期"（`Movie.release_date`，详情页 `releaseDate ?? publishDate` 优先发行日期）不一致，用户感知为排序错误。`Movie.release_date` 完整度 4119/4120。修改为：媒体库列表"发布日期"排序与展示键改用影片发行日期 `Movie.release_date`。

## 变更

- REQ-CHG-329：修订 AC-064。媒体库列表"发布日期"排序（`publish_date_desc`/`publish_date_asc`）与列表卡片展示的 `publish_date` 改用影片发行日期 `Movie.release_date`，NULL 排最后，同键以 `movie_id` 稳定排序；排序值、游标格式（date 或空字符串）、分页与筛选语义保持不变。AVDB 来源发帖日期（`ResourceSource.publish_date`）不再作为媒体库列表排序或展示键；详情页 `release_date` 行为不变。`MovieSummaryOutput.publish_date` 字段名不变，语义从"来源最新发帖日期"改为"影片发行日期"。
- 媒体库默认排序仍为 `publish_date_desc`，前端"发布日期：新到旧/旧到新"选项与标签不变。
- 游标 key 语义从来源发帖日期变为发行日期，格式兼容（ISO date 或空）；部署后客户端重启重新拉取列表即使用新键，旧游标自然失效（按既有游标失效规则返回第一页或 validation_failed）。

## 范围与安全

- 只改 catalog 查询的排序/展示键与游标键；数据库无迁移；`ResourceSource.publish_date` 保留（来源排序、搜索候选 `sort_date` 等既有用途不变）。
- 不访问真实网络；默认测试继续离线。

## 回滚

发布前可整体回退本变更规格，恢复"来源最新发帖日期"排序语义；已下发的带新键游标在回滚后按旧键解析可能失效，客户端重启即可。

## 验证边界

- catalog 单元/集成测试断言 `publish_date_desc`/`publish_date_asc` 按 `Movie.release_date` 排序、NULL 排最后、同键按 `movie_id` 稳定、游标跨 NULL 继续。
- 列表摘要 `publish_date` 等于影片 `release_date`（不再等于来源发帖日期）。
- 详情页 `release_date` 行为不变。
