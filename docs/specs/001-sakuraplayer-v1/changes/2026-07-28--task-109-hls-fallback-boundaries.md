# Change Specification: TASK-109 HLS 回退确定性边界

**Type**: Delta
**Date**: 2026-07-28
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

TASK-109 要求原画优先并在可回退错误或用户选择兼容模式时使用最高码率 HLS，但既有规格没有
冻结可自动回退的错误集合，并把已经由 Cloud115 适配器完成的 master m3u8 解析再次分配给
播放层。HLS variant/segment 又由 302 后的客户端直接请求，后端无法单独证明完整子请求链路的
User-Agent。本变更冻结三者的确定性边界，不新增任务或播放模式。

## ADDED

### 原画自动回退白名单

自动 HLS fallback 白名单固定且仅包含 `cloud115_original_unavailable`。只有 original mode 的
流入口收到该错误时才在同一次请求内解析 HLS；用户显式创建 `compatibility` 会话时直接解析
HLS，不先请求原画。

下列 original 错误不得自动回退，必须保持原 code 和 HTTP 语义：

- `cloud115_credentials_expired`
- `cloud115_file_not_found`
- `cloud115_rate_limited`
- `cloud115_unavailable`
- `cloud115_protocol_error`

HLS 自身错误也不得被包装为 `cloud115_original_unavailable`；会员、未就绪、无 variant、凭据、
文件、限流、上游和协议错误按稳定错误目录直接返回。

### HLS DTO 校验与稳定选择

Cloud115 适配器独占 video info/master 请求、master m3u8 解析、相对 URL 解析和 capability URL
校验，继续返回冻结的 `HlsInfo/HlsVariant`。播放层不得重复解析 m3u8，只执行以下规则：

1. `HlsInfo.pickcode` 必须与会话媒体 pickcode 完全一致。
2. variants 必须非空，且每个 variant 的 `user_agent` 必须与会话固定 UA 完全一致。
3. 选择 `bandwidth` 最大的 variant；并列时保持 master 原顺序，选择首个。
4. pickcode 或 UA 不一致映射 `cloud115_protocol_error`；空 variants 映射
   `cloud115_hls_unavailable`。

### User-Agent 责任

- TASK-109 后端验证 Cloud115 master 请求使用会话固定 UA，并且选中 variant 携带相同 UA。
- TASK-210/TASK-310 客户端必须让播放器的 variant/segment 子请求继续使用 manifest 中的
  `required_user_agent`。
- TASK-213/TASK-312 分别使用真实 115 和真实设备验证完整 master/variant/segment 链路。

## MODIFIED

- 会话创建和 PlaybackManifest 的公开 mode 从阶段性的 `original` 扩展为
  `original/compatibility`；切换模式创建新会话，不修改已签名 mode。
- stream `302` 可指向 original 或选中的最高码率 HLS variant，仍固定
  `Cache-Control: no-store`，不代理视频字节，不返回完整档位列表。
- TASK-109 的 `playback/hls.py` 只消费类型化 HLS DTO 并稳定选择，不拥有协议 parser。

## Acceptance Criteria

- [x] 自动 fallback 只允许 `cloud115_original_unavailable`，其他 original 错误保持不变。
- [x] compatibility 会话直接解析 HLS，original 成功时不调用 HLS。
- [x] 最高 bandwidth 稳定选择和同码率首项规则可由 fixture 测试。
- [x] Cloud115 适配器与播放层的 parser/策略职责不重复。
- [x] 后端、客户端和真实链路的 HLS UA 责任有明确任务归属。
- [x] 公开契约只暴露 original/compatibility，不返回全部 HLS 档位。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| REQ-019、技术计划 AD-007 | MODIFIED | HIGH |
| Cloud115/REST/错误码契约 | MODIFIED | HIGH |
| Playback session/stream resolver | MODIFIED | HIGH |
| TASK-109/210/213/310/312 责任 | MODIFIED | MEDIUM |

## Testing Strategy

- 单元覆盖 fallback 白名单、最高码率、同码率首项、空 variants、pickcode/UA 不一致和所有 HLS
  稳定错误。
- 集成覆盖 original 成功不调用 HLS、唯一白名单错误自动回退、非白名单错误不回退、显式
  compatibility 直接 HLS、302/no-store、无档位列表和短链接不持久化。
- 默认测试只使用 FakeCloud115；真实 master/variant/segment UA 保持在指定外部门禁。

## Rollback Plan

若实现未通过门禁，回退 TASK-109 的代码、测试与本变更同步内容，保持 TASK-108 的 original-only
接口；不得扩大 fallback 白名单或在回退时改动已完成的 TASK-108 数据 Schema。

## Task Impact

不新增或拆分任务。TASK-109 实施后端 HLS resolver 与 fallback；TASK-210/310 消费两种 mode，
TASK-213/312 保持真实链路验收责任。
