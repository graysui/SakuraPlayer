---
id: TASK-317
title: "新手发布文档与首次发布就绪"
spec: docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md
lang: general
status: completed
dependencies: [TASK-316]
ac-mapping: [AC-005, AC-009, AC-123, AC-134, AC-135, AC-138, AC-139, AC-140]
imp-requirements: [REQ-002, REQ-023, REQ-025, REQ-026]
cross-boundary: false
external-dependency-risk: true
provides: [beginner release guide, Linux Docker Compose deployment guide, v1.0.0 release readiness]
---

# TASK-317: 新手发布文档与首次发布就绪

**功能描述**: 重构项目首页的新手使用路径，提供可直接执行的 Linux Docker Compose 部署流程，明确 Windows 发布包与安装方式，并为首次 `v1.0.0` tag 做文档和外部仓库就绪检查。

## 验收条件

- [x] README 首屏清楚展示下载、Linux 部署、功能、架构和安全入口。
- [x] Linux 示例从克隆仓库、生成五个 secret、选择发布镜像、启动、健康检查到常用运维形成闭环。
- [x] Linux 跨设备访问区分 loopback、局域网私有地址和 HTTPS，明确禁止公网明文暴露 API。
- [x] Windows 新手可从 Releases 网页下载、校验、解压并运行当前用户安装脚本。
- [x] README 明确当前产物是包含应用 EXE 的 ZIP，不是单文件 EXE/MSI 安装器。
- [x] `v1.0.0` 与 `windows/pubspec.yaml`、Docker Hub 仓库、Actions Secret 和发布工作流的就绪条件已核对。

## Definition of Ready

- [x] TASK-316 completed，Verify 与 Release workflow 已在 GitHub 启用。
- [x] `windows/pubspec.yaml` 版本为 `1.0.0+1`。
- [x] Docker Hub `graysui/sakuraplayer-backend` 仓库已存在。
- [x] GitHub Actions Secret `DOCKERHUB_TOKEN` 已设置，且未读取其内容。
- [x] 用户明确授权完成文档后创建正式 tag。

## 实现文件（仅文件名）

**新增**:

- `docs/specs/001-sakuraplayer-v1/tasks/TASK-317.md`

**修改**:

- `README.md`
- 任务索引、追踪矩阵和会话交接

## 验证例外

用户明确批准本次文档与首发就绪修改不执行 Focused/Fast/Final 三层验证，也不运行完整 Compose。任务只执行 Markdown/命令事实检查、`git diff --check`、受控差异审计和提交后的 GitHub Verify；正式 tag 由任务完成提交另行触发。

## Definition of Done

- [x] README 示例与仓库 Compose、env、Windows 发布脚本和版本事实一致。
- [x] 定向文档检查、受控差异审计和 `git diff --check` 通过。
- [x] GitHub Verify 在任务提交上绿色。
- [x] 任务状态、索引、追踪和交接在同一中文提交中更新。

**依赖**: TASK-316
