---
id: TASK-003
title: "秘密加密与脱敏基础设施"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: python
status: pending
dependencies: [TASK-001]
ac-mapping: [AC-014, AC-015, AC-017, AC-120, AC-128]
imp-requirements: [REQ-004, REQ-022, REQ-024]
cross-boundary: false
external-dependency-risk: false
provides: [AES-GCM secret repository, redaction, test secret provider]
---

# TASK-003: 秘密加密与脱敏基础设施

**功能描述**: 为 Cookie、JavDB 密码、AI key 等可恢复秘密提供 AES-256-GCM 加密、独立设置密钥读取、版本 CAS 和统一脱敏；该密钥不得用于 JWT 或播放签名。

**规格映射**: AC-014、AC-015、AC-017、AC-120、AC-128

## 验收条件

- [ ] 115 Cookie 等敏感配置以主密钥加密后写 PostgreSQL，主密钥只能来自 Docker Secret 或环境变量；对应 AC-014、AC-120。
- [ ] 加密记录包含版本并支持并发安全 CAS，旧请求不能覆盖新凭据；对应 AC-015。
- [ ] 普通日志和诊断响应不输出 Cookie、完整磁力、AI key 或完整签名 URL；对应 AC-017。
- [ ] 默认自动测试使用可替换的内存/fake secret provider，不访问真实外部服务；对应 AC-128。

## Definition of Ready

- [ ] TASK-001 数据模型骨架和 TASK-002 session epoch 可用。
- [ ] AES-256-GCM nonce、key_id、ciphertext 和 version 字段已确认。
- [ ] 生产缺少主密钥的启动失败行为已确定。

## 技术上下文

- 使用 cryptography 45.0.4，随机 96-bit nonce，每次写入重新加密。
- 密钥名、格式和 `_FILE` 优先级以 `contracts/runtime-configuration.md` 为准；检测到用途复用时启动失败。
- `encrypted_setting` 只由 identity 配置仓储管理，业务模块不直接访问数据库密文。
- 日志过滤器以字段名和 URL query 双重脱敏，错误详情只允许稳定 code。

## 实现文件（仅文件名）

**创建**:

- `backend/src/sakuraplayer/identity/crypto.py` - AES-GCM envelope 和主密钥 provider。
- `backend/src/sakuraplayer/identity/secrets.py` - encrypted_setting repository/CAS。
- `backend/src/sakuraplayer/shared/redaction.py` - 日志、诊断和错误脱敏器。
- `backend/tests/unit/identity/test_crypto.py` - 加解密、key version、nonce 单测。
- `backend/tests/unit/shared/test_redaction.py` - 秘密和 URL 脱敏单测。
- `backend/tests/integration/identity/test_secret_cas.py` - 并发 CAS 集成测试。

## 测试说明

**单元测试**:

- 验证密文篡改、错误 key、重复明文产生不同 nonce 时拒绝解密。
- 验证已知敏感字段、query 参数和异常对象在日志/响应中被替换。

**集成测试**:

- 两个并发写入同一设置时，只有持有最新 version 的写入成功；旧值不覆盖新值。
- 生产配置从 Docker Secret/环境变量读取，客户端设置 API 永远只返回脱敏状态。

**边界条件**:

- 缺少主密钥、空密文、key_id 不存在、日志中出现完整磁力或 URL。

## Definition of Done

- [ ] 所有可恢复秘密统一接入仓储和 CAS。
- [ ] 脱敏测试覆盖 API/日志/诊断路径。
- [ ] 自动测试无真实外部访问。

**依赖**: TASK-001

**实现命令**:

`/developer-kit-specs:specs.task-implementation --lang=python --task="docs/specs/001-sakuraplayer-v1/tasks/TASK-003.md"`
