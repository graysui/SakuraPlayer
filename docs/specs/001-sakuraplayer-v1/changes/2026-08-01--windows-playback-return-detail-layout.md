# Change Specification: Windows 播放返回与详情布局恢复

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

Windows Release 实际体验发现：播放器退出动作固定导航缓存页，丢失了详情页发起播放的上下文；影片详情的来源列表位于简介和剧照之后，常用来源选择需要滚动到底部。本变更新增 TASK-221，恢复详情播放的返回目标，并把详情区块固定为来源、简介、剧照。

## ADDED

- REQ-CHG-257: 从影片详情发起的立即 ready 或等待期 ready 播放，typed player route 可以携带可选 `return_movie_id` query；值必须是本次播放请求的已校验 MovieId UUID，不得携带标题、来源、能力 URL 或任意返回路径。
- REQ-CHG-258: 播放器退出时，有合法 `return_movie_id` 必须回到对应影片详情；缺失或非法时回到缓存页。缓存页直接播放不得添加影片返回目标，仍回缓存页。
- REQ-CHG-259: 影片详情资料头之后的连续滚动区块固定为“来源、简介、剧照”；宽窄布局顺序一致，不新增嵌套卡片或独立滚动区。

## MODIFIED

- REQ-CHG-260: TASK-214 增加 TASK-221 依赖；TASK-217 的 provider/ranking 首次快照边界不变。

## Acceptance Criteria

- [x] 详情立即 ready 和等待期 ready 进入播放器后，点击返回回到同一 MovieId 详情。
- [x] 缓存页 ready 播放返回缓存页；伪造或非法 `return_movie_id` 不形成任意内部跳转。
- [x] 播放 route 不包含能力 URL、Cookie、磁力、来源 ID、标题或自由格式返回路径。
- [x] 详情宽窄布局均按来源、简介、剧照显示，既有来源选择、简介空状态和剧照加载保持可用。

## Testing Strategy

- Route/Widget 覆盖详情返回目标、缓存返回目标、非法 query 回退和等待期 ready 交接。
- 详情 Widget 覆盖三个区块的垂直顺序以及既有来源选择。
- Fast/Final 运行 `dart format`、`flutter analyze`、完整 `flutter test`、Windows Fake integration 和 Release build。
- 默认测试不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

只能通过新的前向变更调整返回目标或详情顺序；不得恢复自由格式 return URL，也不得把播放能力或外部数据写入 route。
