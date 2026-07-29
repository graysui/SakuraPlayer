# Change Specification: TASK-201 Windows 脚手架实施边界

**日期**: 2026-07-29
**状态**: Accepted
**影响任务**: TASK-201、TASK-202、TASK-203、TASK-212
**影响 AC**: AC-005、AC-008、AC-009、AC-059、AC-062、AC-104

## 1. 背景

TASK-201 原任务仍只声明 TASK-014 依赖，但总任务关键路径要求 TASK-113、TASK-114 完成后再进入 Windows 工作流。任务还同时要求私有安装产物、桌面 Shell 和真实会话路由，而这些行为分别由 TASK-212、TASK-203 和 TASK-202 拥有。

原文件清单也未覆盖 `flutter create --platforms=windows` 生成的原生 runner、CMake、插件注册、`.metadata`、分析配置和锁文件；架构只冻结 `go_router`，没有冻结路由代码生成工具。

## 2. 变更要求

- REQ-CHG-152: TASK-201 的直接依赖改为已完成的 TASK-114；TASK-114 的前置链路已包含 TASK-014、TASK-113，不再重复声明历史依赖。
- REQ-CHG-153: TASK-201 只验收 Windows debug 工程、主题、认证壳和应用内全屏播放器占位路由。Windows release、私有安装包、产物许可证核验和真实验收配置全部归 TASK-212。
- REQ-CHG-154: TASK-201 可以提交 Flutter Windows 可构建工程所需的生成文件，包括 `.metadata`、`analysis_options.yaml`、`pubspec.lock`、原生 runner、CMake 和插件注册文件；不得生成 Android、iOS、macOS、Linux 或 Web 平台目录。
- REQ-CHG-155: TASK-201 使用 `go_router 16.3.0` 与手写强类型路由目标，不引入未冻结的 `go_router_builder`、`build_runner` 或生成路由文件。
- REQ-CHG-156: TASK-201 只提供可注入的 `AuthSessionState` 最小接口和登录、Shell 占位页面。TASK-202 以真实 token/session controller 提供该状态，TASK-203 替换 Shell 占位内容并拥有最终左侧导航；后续任务不得要求 TASK-201 提前实现 API、令牌、安全存储或搜索 Shell。
- REQ-CHG-157: TASK-201 工具链固定 Flutter 3.29.2、Dart 3.7.2、Visual Studio 2022 NativeDesktop 工作负载；无法运行的验证必须如实标记，不得以静态检查冒充 Windows build。

## 3. 行为边界

### TASK-201 AC 所有权

**Previous Behavior**: TASK-201 映射 AC-005、AC-008、AC-009、AC-059、AC-062、AC-104，并要求私有安装产物和左侧导航预留。

**New Behavior**: TASK-201 映射 AC-005、AC-009、AC-062、AC-104。AC-008 的 Windows 私有安装包由 TASK-212 实现；AC-059 的最终左侧导航由 TASK-203 实现。TASK-201 只保留可替换的 Shell 路由占位。

### 认证与 Shell 接口

`AuthSessionState` 只有 `unauthenticated` 和 `authenticated` 两种脚手架可观察状态。路由守卫规则固定为：

- 未认证访问 Shell 或全屏播放器时重定向到登录页；
- 已认证访问登录页时重定向到 Shell 占位页；
- TASK-201 不保存 token、不调用后端、不持久化假会话；测试通过 provider override 注入状态；
- 不存在年龄确认、外部播放器或公开商店路由。

TASK-202 可以替换状态提供者，但保持上述路由状态语义；TASK-203 可以替换 Shell 占位页面，但不改变认证守卫和全屏播放器独立路由边界。

## 4. 追踪与任务同步

| 工件 | 变更 | 风险 |
|---|---|---|
| TASK-201 | 依赖、AC、DoR、文件范围、测试和 DoD | MEDIUM |
| Windows 任务索引 | 依赖与文件所有权 | LOW |
| 总任务索引 | Windows 完成进入条件 | LOW |
| 追踪矩阵 | AC-008、AC-059 实现所有权 | LOW |
| TASK-202/203/212 | 行为不变，仅由本变更澄清既有所有权 | LOW |

本变更与 TASK-201 实现、测试、任务状态和交接在同一中文提交中交付，不创建独立 TASK-CHG。

## 5. 回滚

TASK-201 提交前可以整体回退本变更和 Windows 新工程。提交后若需引入路由生成、改变任务依赖或把 release 安装包提前到 TASK-201，必须创建新的前向变更规格并同步任务和追踪矩阵。
