# Change Specification: TASK-101 Cloud115 协议就绪边界

**Type**: Delta
**Date**: 2026-07-27
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-101 预审发现冻结的参考接口清单遗漏扫码前三步和目录自查原语，内部端口没有
精确签名、稳定 DTO 与逐操作错误映射，Cookie snapshot 产生和数据库 CAS 的职责混在
适配器中，协议 fixture 又不在 Fast/Final 默认收集路径。按旧契约直接实施会依赖不存在
的接口或让真实 115 调用混入默认测试。本变更只修正实施就绪边界，不增加产品功能。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 3 |
| MODIFIED | 3 |
| REMOVED | 0 |

## ADDED

### 固定 revision 与符号级移植清单

**Requirements**:

- REQ-CHG-128: TASK-101 的参考基线固定为
  `https://github.com/tinypinglite/sakuramediabe.git` revision
  `670ca75b2d35b606ffc0caa6fd47fd04c4c95870`；只允许选择性适配 QR、Cookie
  探活、目录、离线、文件枚举、downurl RSA/XOR、HLS 元数据、小文件下载和删除符号。
- REQ-CHG-129: 禁止整文件复制参考 `client.py`、`types.py`、`exceptions.py` 或
  `cipher.py`；禁止带入 rapid upload、copy/move、MediaLibrary、原始响应、磁力/source
  URL 字段、上传 AES/LZ4 和外部播放器路径。
- REQ-CHG-130: 适配器目录 NOTICE 和根 THIRD_PARTY_NOTICES 必须记录上游 URL、固定
  revision、实际使用文件/符号和 GPLv3；稳定异常只能保存安全 code 与可选 retry-after。

**Acceptance Criteria**:

- [x] 架构批准清单包含实际 QR 四步和 `dir_info` 签名。
- [x] 提交差异只包含允许符号，许可证说明可追溯且没有上游秘密载荷模型。

### 类型化端口与安全协议边界

**Requirements**:

- REQ-CHG-131: Cloud115Port 使用精确 Protocol 签名和 frozen DTO；QR、凭据探活、目录、
  离线分页/任务、远端文件、原画和 HLS 不向领域层暴露 errno、任意 JSON 或响应正文。
- REQ-CHG-132: `OfflineTaskSnapshot` 不包含磁力、raw source URL 或任意上游载荷；取消
  固定调用 `delete_source_files=False`，提交超时使用 `cloud115_submit_uncertain` 且不得
  自动重提。
- REQ-CHG-133: Cookie 响应合并只产生 `CredentialProbe.cookie_snapshot` 或扫码结果的
  snapshot。TASK-101 不读取 credential_version、不访问数据库也不执行 CAS；TASK-102
  在应用/仓储事务中以版本 CAS 加密写回。
- REQ-CHG-134: QR、Cookie 和 HLS/原画相关请求只允许契约列出的精确 HTTPS 115 主机，
  重定向必须逐跳复核；未知 QR status、非法 JSON、未知 errno 和解密失败统一映射为
  `cloud115_protocol_error`，不得输出请求 URL、Cookie、磁力或响应正文。

**Acceptance Criteria**:

- [x] 端口、Fake 和适配器共同通过类型、状态、错误映射、主机限制和脱敏合约测试。
- [x] TASK-101 生产代码不 import SQLAlchemy，也没有 credential CAS 或 source URL DTO。

### 可执行的协议验证门禁

**Requirements**:

- REQ-CHG-135: 无网络协议 fixture 位于 `backend/tests/unit/cloud115/`，进入现有 Fast 和
  Final 自包含测试收集；`backend/tests/lib/cloud115/` 不得作为完成证据路径。
- REQ-CHG-136: pytest 注册 strict `real115` marker；真实协议测试必须位于显式目录，
  同时要求 marker、环境开关、外部凭据和应用专属测试根。Fast、无参数 Final 和普通
  pytest 默认不收集或不执行真实测试，发布级真实门禁仍由 TASK-213 负责。

**Acceptance Criteria**:

- [x] 治理测试固定 fixture 收集路径、strict marker 和默认无真实 115 的 runner 边界。
- [x] 默认 Fast/Final 在没有真实凭据时通过且不会请求 115。

## MODIFIED

### 实施前协议核验

**Previous Behavior**: 架构要求每个实现任务先执行真实协议测试验证签名。

**New Behavior**: TASK-101 先核对固定 revision、历史真实证据和无网络 fixture；当前真实
调用只在显式 `real115` 门禁中允许。发布前完整扫码、离线、播放和清理由 TASK-213 负责。

### Cookie 写回职责

**Previous Behavior**: Cloud115 适配器关闭时直接执行数据库 credential version CAS。

**New Behavior**: TASK-101 适配器只返回最新 Cookie snapshot；TASK-102 拥有加密仓储、
credential version 和 CAS，旧请求丢弃失败 snapshot，不覆盖重新扫码结果。

### 离线对账依赖

**Previous Behavior**: TASK-104 依赖未定义字段的 remote task ID 和宽泛失败类别。

**New Behavior**: TASK-104 只依赖 `info_hash`、任务目录 CID、类型化分页快照和已冻结的
invalid/quota/not-found/unavailable/rate-limit/submit-uncertain 错误。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| architecture / Cloud115Port / error codes | MODIFIED | MEDIUM |
| TASK-101 / TASK-102 / TASK-104 / task index | MODIFIED | LOW |
| pytest marker / readiness governance | ADDED | LOW |
| Cloud115 adapter / Fake / fixtures | ADDED | HIGH |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。功能规格、架构、契约、TASK-101/102/104、115 任务索引、
追踪矩阵、测试 README、实现和测试在 TASK-101 同一中文提交中同步。

## Testing Strategy

- start 治理测试检查批准接口、精确端口方法、错误码、fixture 路径和 real115 默认排除。
- unit fixture 覆盖 QR、Cookie、目录、离线、downurl、原画/HLS、小文件和删除解析。
- adapter/Fake 合约覆盖状态序列、提交不确定、目录移动、多媒体、限流和秘密扫描。
- 按统一工作流运行 Focused、Fast、完整差异审计和一次 Compose Final。

## Rollback Plan

TASK-101 提交前可整体回退本变更及实现。提交后若 115 协议发生变化，必须以前向变更
规格更新固定 revision、DTO/错误映射和 fixture；不得放宽秘密边界或让真实调用进入默认测试。
