# Change Specification: TASK-008 永久图片安全边界

**Type**: Delta
**Date**: 2026-07-26
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

AC-047、AC-048 和 TASK-008 要求下载永久目录图片并限制主机、类型、大小、重定向和像素，但原契约只声明存在这些限制，没有给出可执行数值，导致 TASK-008 Definition of Ready 无法满足。本变更冻结 v1 图片下载边界和解析依赖，不改变图片永久保留、占位或可重试语义。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 0 |
| REMOVED | 0 |

## ADDED

### 永久目录图片下载与验证

**Requirements**:

- REQ-CHG-053: TASK-008 永久目录图片只接受 `https://c0.jdbstatic.com`；必须使用规范化后的精确小写主机比较，禁止 userinfo、非 HTTPS、非默认端口、IP 字面量和子域后缀匹配。
- REQ-CHG-054: 只接受声明且实际解码一致的 `image/jpeg`、`image/png`、`image/webp`。单个响应正文最多 8 MiB，流式读取在超过上限后立即停止。
- REQ-CHG-055: 最多跟随 3 次 HTTP 重定向；每一跳都必须重新执行完整 URL 白名单检查，拒绝缺失或非法 `Location`、重定向循环和第四次重定向。
- REQ-CHG-056: 图片宽高必须分别为 1..12,000，总像素不得超过 40,000,000。使用 Pillow 11.2.1 完整解码验证真实格式和像素边界；截断、损坏和解压炸弹图片均拒绝。
- REQ-CHG-057: 文件名和相对路径只能由服务端根据 owner、kind、序号和内容摘要生成；临时文件必须位于目标目录内，完成校验、flush 和 fsync 后使用原子替换。异常或取消必须删除本次临时文件，不得覆盖既有 ready 文件。
- REQ-CHG-058: 下载或验证失败写入 `retry_pending` 图片事实并使用本地占位，不回滚 JavDB 核心事务；管理员只能通过已有 `retry-enrichment(images)` 创建新 attempt。
- REQ-CHG-059: 自动测试只使用脱敏固定图片 fixture 和 `httpx.MockTransport`，不得访问真实 JavDB、DMM 或图片主机。

**Acceptance Criteria**:

- [x] HTTPS 精确白名单、每跳重定向校验和 SSRF 拒绝测试通过。
- [x] MIME/真实格式不一致、8 MiB 边界、宽高边界、总像素、截断和损坏图片测试通过。
- [x] 成功写入使用同目录临时文件和原子替换；失败不留半文件且不覆盖既有 ready 文件。
- [x] 图片 warning 保留 `core_ready`，并可由显式 `retry-enrichment(images)` 补齐。

**Impact**: TASK-008、元数据提供方契约、错误码、架构依赖和永久图片测试；Breaking: NO，相关 provider 尚未实现。

## MODIFIED

无。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 永久图片下载适配器 | ADDED | HIGH |
| `catalog_image` 写入 | ADDED | MEDIUM |
| Pillow 11.2.1 | ADDED | LOW |
| TASK-008 Definition of Ready | SATISFIED | LOW |

## Task Synchronization

本变更不创建独立 `TASK-CHG`，不改变 TASK-008 的依赖或 AC 映射。契约、实现、测试和迁移仍在 TASK-008 的一次中文提交中交付。

## Testing Strategy

- 单元测试以固定的最小 JPEG/PNG/WebP 和恶意/损坏样本覆盖所有下载边界。
- fake HTTP 测试覆盖重定向每一跳、循环、超限流和响应头欺骗。
- PostgreSQL 集成测试覆盖 `core_ready` 与图片 warning/retry 事实隔离。
- Final 使用隔离 Compose，但不访问真实外部服务。

## Rollback Plan

TASK-008 提交前可整体回退本变更和实现。提交后若需增加主机或放宽限制，必须新增 Delta 并补安全回归；不得用通配主机或关闭解码检查临时绕过。
