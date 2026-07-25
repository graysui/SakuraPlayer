---
id: TASK-102
title: "扫码绑定、Cookie CAS 与缓存根"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-101]
ac-mapping: [AC-013, AC-014, AC-015, AC-016, AC-079, AC-080, AC-081, AC-082]
imp-requirements: [REQ-004, REQ-016]
cross-boundary: false
external-dependency-risk: true
provides: [single 115 binding, QR API, cookie CAS, SakuraPlayer-Cache root]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-102: 扫码绑定、Cookie CAS 与缓存根

**功能描述**: 实现 Windows/HarmonyOS 可用的扫码会话、唯一加密绑定、Cookie snapshot CAS、凭据状态和 `SakuraPlayer-Cache` find-or-create。

**规格映射**: AC-013 至 AC-016、AC-079 至 AC-082

## 外部依赖风险

- **依赖**: 115 扫码与目录 API。
- **状态**: 参考实现已验证；上游登录槽和 Cookie 刷新可能变化。
- **缓解**: Fake 状态序列、CAS 版本、active/expired/unavailable 三态和显式真实扫码测试。

## 验收条件

- [ ] 客户端可发起 QR、轮询状态和完成绑定；对应 AC-013。
- [ ] Cookie 仅后端持有并加密，snapshot 通过版本 CAS 回写，旧请求不覆盖重扫；对应 AC-014、AC-015。
- [ ] expired 返回稳定重扫错误，unavailable 不误标过期；对应 AC-016。
- [ ] 首次绑定确保唯一缓存根并记录账号/root CID；系统不扫描其他目录，手动移动/删除只标失效；对应 AC-079 至 AC-082。

## Definition of Ready

- [ ] TASK-101 QR/目录/credential port 和 TASK-003 secret repository 可用。
- [ ] active 绑定单例与 credential_version 迁移已确认。
- [ ] 根目录同名并发 find-or-create 由事务互斥。

## 技术上下文

- 重新绑定前检查活动缓存任务；旧账号任务不能用新 Cookie 清理。
- Cookie client context 退出时 snapshot CAS；CAS 丢失直接丢弃旧快照。
- 根目录只通过持久 CID 使用，不按名称全盘扫描。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/cloud_cache/binding_service.py` - 单绑定和 Cookie CAS。
- `backend/src/sakuraplayer/cloud_cache/qr_service.py` - QR session 状态机。
- `backend/src/sakuraplayer/cloud_cache/root_directory.py` - 专属根 find-or-create/验证。
- `backend/src/sakuraplayer/cloud_cache/binding_api.py` - binding/qr REST 路由。
- `backend/tests/integration/cloud_cache/test_binding_cas.py` - 重扫并发和 secret。
- `backend/tests/integration/cloud_cache/test_cache_root.py` - 根目录和移动/删除。

## 测试说明

**单元测试**:

- waiting/scanned/confirmed/expired/canceled 状态和错误码。
- active/expired/unavailable 转换，unavailable 不触发重扫提示。

**集成测试**:

- 两个请求刷新 Cookie 同时管理员重扫，验证旧 CAS 不覆盖新 Cookie。
- 根已存在/不存在/同名多个/被删除/被移动时，验证数据库和 115 操作范围。

**边界条件**:

- QR 过期、绑定已存在、有活动任务重绑、根目录 API 限流。

## Definition of Done

- [ ] QR、绑定、CAS、状态和根目录完成。
- [ ] 客户端响应不包含 Cookie/root 以外的敏感定位。
- [ ] 并发重扫和目录故障测试通过。

**依赖**: TASK-101

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-102.md"`
