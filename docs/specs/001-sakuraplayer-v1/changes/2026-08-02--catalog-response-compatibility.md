# Change Specification: 真实目录响应兼容与可选元数据状态

**Type**: Delta
**Date**: 2026-08-02
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-222 后的 Release 体验发现：GFriends `Filetree.json` 合法保留数字 `t` query，但 Windows GFriends 下载契约只接受无 query 的固定 Content URL，导致成功的女优列表和包含相关演员的影片详情在客户端整体解析失败；图片源当前又对正式下载请求返回 Cloudflare 403，`retry_pending` 封面记录继续指向 1x1 灰色占位文件并被目录 API 当作真实封面返回。AI 翻译则没有任何成功结果，现有失败事实以 guardrail 和 upstream 两类为主。本变更新增 TASK-223，修复客户端可消费投影和占位语义，不放宽 URL 白名单、不伪造图片或翻译成功。

## ADDED

- REQ-CHG-271: 新增 TASK-223，负责真实目录 API 响应与 Windows 严格 DTO 的兼容修复；TASK-214 在 TASK-223 完成前保持 pending。
- REQ-CHG-272: GFriends 持久快照继续保留由固定 Filetree 生成的完整证据 URL；目录 API 在 `profile_url` 和 `gallery_urls` 投影时只允许固定 `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/` 路径，并去掉已冻结的单个数字 `t` query。其他 query、fragment、userinfo、非默认端口、非固定主机或越界路径不得投影。
- REQ-CHG-273: 单个非法或不兼容的可选 GFriends 资产不得使女优列表、女优详情或影片详情整体不可消费。非法头像按缺头像投影，非法写真从图库中丢弃；演员身份、别名、收藏和影片关系不变。
- REQ-CHG-274: 只有已经通过完整图片校验并保存 `sha256` 的 cover 才能投影为 `cover_url`。`retry_pending` 记录若仍指向带摘要的最近成功文件可以继续投影；新下载失败、无图片摘要且指向 1x1 安全占位的记录只作为后端恢复事实，不得冒充客户端真实封面。没有已验证 cover 时 API 返回 `cover_url=null`，Windows 使用既有固定占位布局。
- REQ-CHG-275: TASK-223 的正式运行核验必须只读聚合 AI 配置状态、翻译 stage/record 状态和 `title_zh/description_zh` 数量，不调用付费翻译、不自动重试未知或拒绝记录。未产生 completed 事实时不得显示或报告中文翻译成功。

## MODIFIED

- REQ-CHG-276: AC-042/047/048 的可选图片失败语义增加客户端投影边界；永久记录和安全占位仍保留，目录卡片只把已有完整校验摘要的本地图片视为真实封面。
- REQ-CHG-277: AC-051/052 的 GFriends 精确 URL 在持久快照与客户端投影之间增加确定性规范化；Windows 无 query 白名单、匿名下载、安全缓存和逐图失败隔离保持不变。
- REQ-CHG-278: TASK-214 增加 TASK-223 依赖；本任务不开始 TASK-214，不升级框架或改变公开认证、分页、收藏和播放协议。

## Acceptance Criteria

- [ ] 正式首屏女优响应和包含 GFriends 演员的正式影片详情均通过 Windows 严格 DTO；返回 URL 无 query/fragment，客户端白名单不放宽。
- [ ] 非法可选 GFriends 资产按单图缺失隔离，不清空成功的女优页或影片详情。
- [ ] 已验证 cover 正常读取；无摘要 retry_pending 的安全占位记录在目录 API 中投影为 `cover_url=null`，带摘要的最近成功封面继续显示，影片详情仍可打开。
- [ ] 排行榜、媒体库和搜索结果进入同一 MovieId 详情，不因可选演员头像字段产生 `client_protocol_error`。
- [ ] 正式翻译状态只读核验报告配置、成功数量和稳定失败码，不访问付费 AI、不把原文回退称为中文译文。

## Testing Strategy

- 后端 Focused 使用固定 GFriends URL、非法 URL、有无校验摘要的 retry_pending cover fixture 覆盖列表、演员详情和影片详情投影。
- Windows Focused 使用后端规范化响应 fixture 验证 Actor/Movie 严格 DTO，继续断言带 query 的 GFriends URL 被客户端拒绝。
- Fast/Final 按统一流程运行；Final 后验证普通 Compose、Windows Release、正式 API DTO、图片状态和翻译聚合。外部图片源只允许无凭据只读 probe，不把 403 当作自动测试失败。

## Rollback Plan

只能通过新的前向变更调整 GFriends 投影或封面状态语义；不得放宽 Windows URL 白名单、删除永久图片恢复事实、自动重派付费翻译或把安全占位伪造成真实封面。
