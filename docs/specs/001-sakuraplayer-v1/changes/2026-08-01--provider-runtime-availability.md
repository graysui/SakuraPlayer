# Change Specification: 外部元数据服务运行可用性

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-215 后的真实首次运行发现：生产 API 只注入 115 连接探测，JavDB、DMM、GFriends 和 AI 会在 0-2 ms 内固定返回 `service_unavailable`；同时 JavDB 核心仍抓取被上游拒绝的固定 HTML 站点，导致全部核心元数据失败。周中首次部署还要等待下一次定时任务才能建立 GFriends 和排行榜快照。本变更增加 TASK-216 与 TASK-217，先恢复真实 provider 访问与连接测试，再补齐首次快照启动；TASK-214 在两项完成前保持 pending。

## ADDED

- REQ-CHG-225: JavDB 核心搜索和详情使用参考项目固定 revision 已验证的签名 JSON API，默认 host 为 `jdforrepam.com`，并允许通过经过严格 hostname 校验的非秘密运行配置覆盖。搜索仍按规范化番号精确匹配，详情先映射为现有严格 `CoreMovieMetadata`，上游任意结构不得透传领域层。
- REQ-CHG-226: JavDB 连接测试在配置存在时执行只读登录并区分 `available`、`credentials_invalid` 和 `unavailable`；未配置继续返回 `not_configured`。核心影片和公开榜单仍允许匿名读取，账号只用于连接验证与需登录 TOP250。
- REQ-CHG-227: DMM 使用年龄确认 Cookie、浏览器请求头和路径式搜索入口。DMM 连接测试执行无写只读请求；地区限制、网络错误和结构变化保持 `unavailable/dmm_upstream_error`，不得伪报可用或阻断 JavDB 核心。
- REQ-CHG-228: GFriends 连接测试只验证固定 Filetree 源的安全 HTTPS 可达性，不下载 Content 图片；provider 的 configured 仍只表示本地 current snapshot 已建立。AI 连接测试只调用 OpenAI-compatible `/v1/models`，不得发送翻译请求或产生付费 reservation/dispatch。
- REQ-CHG-229: 五个连接测试均必须由生产 composition root 注入真实 probe；缺少已声明 probe 是启动/测试缺陷，不得在管理员请求时静默回退为 `service_unavailable`。所有结果只保存稳定状态、错误码、耗时和时间，不保存上游正文、token 或 secret。
- REQ-CHG-230: Windows 设置和诊断对 DMM、GFriends、AI 专属稳定错误码补齐中文映射，未知码仍显示“未知错误”；协议枚举和服务端稳定码保持英文。
- REQ-CHG-231: 默认自动测试继续只使用 MockTransport/fixture，不访问真实 JavDB、DMM、GFriends 或付费 AI；真实只读探测仅作为显式本机验收证据，且不得输出凭据、token、完整 URL 或上游正文。
- REQ-CHG-232: scheduler 首次启动时，如果从未存在 provider snapshot request 且 Actor Mapping/GFriends 任一 current snapshot 缺失，幂等排入一次首次快照请求；已有 queued/claimed/completed/failed request 时不得重复创建。
- REQ-CHG-233: scheduler 首次启动时，如果从未存在 ranking request/snapshot，则幂等排入当前日/周/月与当年 TOP250 目标；已有任何持久请求或快照事实时不得把首次启动当作自动重试。后续仍按每日 01:45 Asia/Shanghai 调度。

## MODIFIED

- REQ-CHG-234: AC-042、AC-044 至 AC-046、AC-049、AC-069、AC-119、AC-121 与 AC-128 增加真实 provider 运行链路、首次快照和无付费只读连接测试语义。
- REQ-CHG-235: TASK-214 新增 TASK-216 与 TASK-217 依赖；两项运行修复完成前不得开始 Windows 清理。

## Acceptance Criteria

- [ ] JavDB 签名 JSON API 的搜索、详情、公开榜单、登录和错误映射由固定 fixture 覆盖，真实只读验收可恢复 `core_ready`。
- [ ] 五个 target 在生产均有 probe；JavDB/AI 配置有效时可用，DMM 地区限制如实不可用，GFriends 源可达时可用。
- [ ] DMM/GFriends/AI 专属错误在 Windows 显示中文，响应和日志不泄露 secret 或上游正文。
- [ ] TASK-217 首次快照与排行榜请求各只创建一次，重启或既有失败事实不自动重试。

## Testing Strategy

- TASK-216 Focused 覆盖 provider adapter、生产 probe 注入、设置 API 与 Windows 中文映射。
- TASK-217 Focused 覆盖首次入队幂等、既有事实保护和 scheduler composition root。
- Fast/Final 按统一实施流程运行；默认门禁不访问真实外部 provider，部署后只执行显式无写探测。

## Rollback Plan

只能以前向变更替换 JavDB host/签名协议或连接探测方式；不得恢复缺 probe 的固定 unavailable，也不得删除既有连接测试、快照、任务或失败事实。
