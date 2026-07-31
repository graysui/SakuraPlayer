# Change Specification: TASK-210 Windows 播放器确定性边界

**Type**: Delta
**Date**: 2026-07-31
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-209 已能获得完整 ready `CacheJob`，但现有无参数 `/player` 占位 route 会在 controller reset
后丢失 `cache_job_id` 与首个 `media_id`，无法调用已冻结的 playback session 接口。另一方面，
TASK-105 已交付 `awaiting_selection` 与有序媒体选择 API，但 Windows 任务没有拥有候选选择 UI，
导致歧义资源无法进入 ready。本变更冻结 TASK-210 的播放器交接、候选选择、media_kit、固定 UA、
错误恢复和 seek 合并边界，不修改后端 OpenAPI、状态机或真实 115 门禁。

## ADDED

### 播放器交接与候选选择

- REQ-CHG-196: `ready` 或 `reused + ready` 的 `CacheJob` 必须包含非空有序
  `selected_media_ids`。Windows 在 reset 播放请求 controller 前复制 `cache_job_id` 与首个
  `media_id`，进入只含这两个 UUID 的受认证 typed player route；不得把 manifest、stream URL、
  User-Agent、Cookie 或磁力放入 route。
- REQ-CHG-197: 缓存页对 `awaiting_selection` 按 `candidate_id` 展示候选组；每组只包含
  `is_valid=true` 的媒体，并按 `sequence_no` 升序提交完整 media ID 列表。用户必须显式选择组并
  点击播放；成功转为 ready 后才进入播放器。后台 ready、通知点击或列表刷新不得自动播放。
- REQ-CHG-198: 缓存页对具有非空 `selected_media_ids` 的 ready job 提供显式播放动作，使用首个
  ID 创建会话。无效 UUID、ready 空选择、候选组空洞或陈旧 route 返回缓存页并显示稳定的客户端
  协议/服务端错误，不从本地字段猜测媒体归属。

### 会话、UA 与模式

- REQ-CHG-199: 每次进入播放器、显式重试或切换模式都重新向
  `POST /api/v1/cache-jobs/{cache_job_id}/playback-sessions` 提交首媒体 ID、`platform=windows` 和
  安装级 `client_instance_id`。默认 mode 为 `original`；`compatibility` 必须创建全新 session，
  不修改或复用旧签名 URL。
- REQ-CHG-200: Windows 固定 UA 为 `SakuraPlayer/1.0 (Windows; x64)`。manifest 的
  `platform/mode/cache_job_id/required_user_agent`、queue UUID/顺序与 URL 必须严格校验；每个
  `Media` 都使用同一 `User-Agent` header。media_kit 1.1.11 在 libmpv `on_load` 写入
  `http-header-fields`，由 TASK-213 真实验证 302、Range 和 HLS 子请求。
- REQ-CHG-201: capability URL 按当前认证服务端 origin 解析，只允许同 origin 的绝对或
  root-relative HTTP(S) URL；URL 只保存在当前 controller/media_kit 内存，不持久化、不记录日志、
  不发送 Bearer。播放器模式菜单只显示“原画”和“兼容播放”，不展示 HLS variant。

### 播放引擎、错误与 seek

- REQ-CHG-202: TASK-210 使用应用内 media_kit `Player + VideoController + Playlist` 播放 manifest
  的完整有序队列，并注入可测试的 engine 端口。页面销毁、认证变化或服务端切换时释放 Player、
  manifest 与 capability URL；不调用外部播放器，不建立缩略图 API、状态或 UI。
- REQ-CHG-203: controller 订阅 `Player.stream.error`。已达到 manifest `expires_at` 的播放错误只在
  当前 controller generation 内重新签发同 mode 会话一次；未到期错误保留当前模式并显示重试/
  兼容动作，不循环重签。API 401/403/404/409/422 和协议错误保留稳定 code，不包装为 HLS fallback。
- REQ-CHG-204: 所有 slider、键盘、按钮和自动恢复 seek 都只能调用 `ThrottlingPlayer`。无在途 seek
  时立即执行；在途期间只覆盖保存最后目标；成功后最多执行该最后目标。任一次 seek 失败都清空
  pending 并向 controller 报错，不并发重放或吞掉异常。
- REQ-CHG-205: TASK-210 提供播放/暂停、标准进度、固定倍速菜单和全屏控制；窄窗口控制可换行或
  收入菜单但不得溢出画面。字幕、音轨、外置字幕缓存、15 秒心跳和完成阈值继续由 TASK-211 所有。

## MODIFIED

- TASK-210 的 AC 映射增加 AC-093，并接管 Windows `awaiting_selection` 候选组 UI 与 ready 缓存
  播放入口；TASK-105 继续独占后端解析、评分、持久选择与状态转换。
- TASK-209 的 `/player` 占位交接由 UUID typed route 取代；TASK-209 状态机、60 秒 deadline、通知
  和后台不自动播放语义不变。
- TASK-210 Definition of Ready 引用 [Windows 播放器客户端契约](../contracts/windows-playback-client.md)，
  以本地固定版本源码核验 media_kit UA header、error stream、playlist 和 seek API。

## Acceptance Criteria

- [ ] ready/等待 ready/缓存页 ready 三入口都携带 job 与首媒体 UUID，并为每次打开创建新 session。
- [ ] awaiting-selection 按候选组提交完整有序媒体，后台事件和通知不自动播放。
- [ ] manifest 严格 DTO、同 origin URL、固定 Windows UA、original/compatibility 新会话均有测试。
- [ ] 30 至 60 次连续 seek 只执行首个和最后目标；失败清空 pending，所有 UI 入口使用同一 wrapper。
- [ ] 页面包含应用内画面、播放/暂停、进度、倍速和全屏，在窄窗口无溢出且不存在缩略图能力。

## Task Synchronization

本变更不新增 `TASK-CHG`。变更规格、客户端契约、功能规格、技术计划、Windows 任务索引、
TASK-210 和追踪矩阵先独立中文提交；TASK-210 实现、测试、状态和交接在后续中文提交中完成。

## Testing Strategy

- Dart 单元测试覆盖严格 manifest、session payload、URL/UA、模式 generation、过期重签和 seek 合并。
- Flutter Widget/route 测试覆盖三类播放入口、候选组、播放器控制、窄布局、错误恢复和无缩略图。
- Fast 运行格式、`flutter analyze`、完整 `flutter test` 和差异/秘密检查；Final 运行 Windows debug
  build。真实 302/Range/HLS 仍只由 TASK-213 显式运行。

## Rollback Plan

TASK-210 实现提交前可整体回退本变更。实现后只能通过新的前向变更调整 Windows 播放器边界，
不得回退固定 UA、同 origin capability、显式用户播放、后台不自动播放或 seek 串行约束。
