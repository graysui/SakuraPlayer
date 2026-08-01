---
id: TASK-216
title: "外部元数据服务可用性修复"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-008, TASK-009, TASK-010, TASK-012, TASK-013, TASK-215]
ac-mapping: [AC-042, AC-044, AC-045, AC-046, AC-119, AC-121, AC-128]
imp-requirements: [REQ-008, REQ-009, REQ-022, REQ-024]
cross-boundary: true
external-dependency-risk: true
provides: [signed JavDB JSON provider, typed provider probes, DMM request compatibility, Chinese provider errors]
---

**实施与验证流程**: [统一实施与验证工作流](../implementation-workflow.md)

# TASK-216: 外部元数据服务可用性修复

**功能描述**: 修复生产环境缺少 provider probe 和 JavDB 固定 HTML 入口失效造成的全服务误报与核心元数据阻断。

**实施边界**: [外部元数据服务运行可用性](../changes/2026-08-01--provider-runtime-availability.md)

## 验收条件

- [x] JavDB 搜索、详情和排行榜使用严格签名 JSON API，现有账号可执行无泄密只读登录探测。
- [x] DMM 使用年龄确认与浏览器请求形态，地区限制如实映射为不可用且不阻断核心元数据。
- [x] cloud115/JavDB/DMM/GFriends/AI 五类生产连接测试均执行真实 typed probe，不再因缺少 probe 固定误报。
- [x] AI probe 只读取 models，GFriends probe 只验证固定 Filetree，不产生付费调用、不下载 Content 图片。
- [x] Windows 对新增 provider 错误码显示中文，未知值仍安全降级。

## Definition of Ready

- [x] TASK-008/009/010/012/013/215 已完成。
- [x] 正式数据库和容器证据确认四类固定误报、JavDB 403 与元数据失败分布。
- [x] 用户指定的 `avmedia` 固定 revision、JavDB 签名 API、DMM 请求形态和 GPLv3 来源边界已核对。
- [x] 真实 JavDB 凭据登录与 AI models 只读探测已在不输出 secret 的条件下验证成功。

## 实施批次

1. 以失败 fixture 测试冻结 JavDB JSON/签名、DMM 请求兼容和稳定错误。
2. 实现四类 provider probe 与生产 composition 注入，补齐运行配置和契约。
3. 补齐 Windows 中文映射与相关 widget/unit 测试。
4. Focused、Fast、只读审计、Final、正式环境无写验证、交接和中文提交。

## Definition of Done

- [x] 所有验收条件、契约测试与默认离线门禁通过。
- [x] 完整差异审计、`git diff --check`、秘密扫描和 Compose Final 通过。
- [x] 正式环境 JavDB/AI/GFriends 状态与实际探测一致，JavDB 核心开始产生 `core_ready`。
- [x] TASK-214 保持 pending，下一任务为 TASK-217。

## 完成证据

- 后端 Fast 807 passed、8 deselected；Ruff format/check 与宿主 Docker 配置断言通过。
- Windows `flutter analyze` 与完整 211 项测试通过。
- Compose Final 第 2 次尝试通过 807 项自包含和 125 项 PostgreSQL integration/E2E；临时资源完整清理。
- 正式无写 probe：JavDB、GFriends、AI available，DMM 如实为 `dmm_upstream_error`；观察窗口内 `core_ready` 从 10 增长到 26。

**依赖**: TASK-008, TASK-009, TASK-010, TASK-012, TASK-013, TASK-215
