---
id: TASK-208
title: "115 扫码缓存管理设置与诊断"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: pending
dependencies: [TASK-202, TASK-112]
ac-mapping: [AC-013, AC-016, AC-094, AC-118, AC-119, AC-120, AC-121, AC-122]
imp-requirements: [REQ-004, REQ-018, REQ-021, REQ-022]
cross-boundary: false
external-dependency-risk: true
provides: [Windows QR binding UI, cache page, settings diagnostics]
---

# TASK-208: 115 扫码缓存管理设置与诊断

**功能描述**: 实现 115 QR 绑定状态、缓存任务页、TTL 设置、连接测试、脱敏诊断和管理员重试/取消/清理操作。

**规格映射**: AC-013、AC-016、AC-094、AC-118 至 AC-122

## 外部依赖风险

- **依赖**: 115 QR 状态和连接测试结果。
- **状态**: QR 可过期，上游 unavailable 与 credentials expired 需区分。
- **缓解**: 稳定错误码、本地 QR 状态机、无 Cookie 展示和 Fake UI 测试。

## 验收条件

- [ ] 客户端显示 QR waiting/scanned/confirmed/expired/canceled 和绑定状态；expired 明确提示重扫；对应 AC-013、AC-016。
- [ ] 缓存页显示 queued/running/ready 数量/任务并可取消、清理；对应 AC-118、AC-122。
- [ ] TTL 可设 1 至 168 小时、默认 24；对应 AC-094。
- [ ] 设置回显非敏感 JavDB/AI 现值、增量/全量同步状态和连接测试；诊断只显示严格 DTO 中的脱敏 stage/error/time/attempt，主密钥不可编辑；对应 AC-119 至 AC-121。
- [ ] 管理员可对 warning 元数据任务选择失败/缺失富化阶段重试，不能选择 JavDB 核心或隐式重跑 AI；对应 AC-122。

## Definition of Ready

- [ ] TASK-202 secure/API/event，TASK-112 settings/cache/admin 契约可用。
- [ ] 二次确认取消、active lease 清理拒绝和 error code 文案已定义。
- [ ] API key/password 输入只发送，不回显。

## 技术上下文

- 任务页不是通用下载中心，不显示磁力、速度调参或并发配置。
- 固定 2/10/3/600 只读显示，不提供调整控件。
- QR 图片在内存显示，会话结束释放。

## 实现文件（仅文件名）

**创建**:

- `windows/lib/features/settings/presentation/settings_page.dart` - 115/JavDB/AI/TTL。
- `windows/lib/features/settings/presentation/qr_binding_controller.dart` - QR 状态。
- `windows/lib/features/cache/presentation/cache_page.dart` - 任务/容量/操作。
- `windows/lib/features/settings/presentation/diagnostics_page.dart` - 脱敏诊断。
- `windows/test/features/settings/qr_settings_test.dart` - QR/secret/TTL。
- `windows/test/features/cache/cache_page_test.dart` - 状态/取消/清理。

## 测试说明

- QR 全状态、expired/unavailable 文案区别、重绑有活动任务错误。
- TTL 0/1/24/168/169 边界；固定并发/超时无可编辑控件。
- 取消二次确认、active lease 清理拒绝、元数据失败完整重试、warning 富化阶段重试；Widget tree 无 secret 文本。

## Definition of Done

- [ ] QR、缓存页、设置、诊断和任务操作完成。
- [ ] 所有秘密只显示 configured/status。
- [ ] Widget/controller 测试通过。

**依赖**: TASK-202, TASK-112

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=general --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-208.md"`
