# SakuraPlayer 协作规则

## 必须遵守

- 每完成一个 `TASK-xxx`，就使用中文提交信息创建一次 Git 提交；任务实现、测试、任务状态及相关契约放在同一提交中，不得合并多个任务。
- 只暂存当前任务相关文件，不得顺带提交用户的未跟踪资料。
- 所有需要用户回答的问题都必须通俗易懂，并明确标出推荐答案。
- 一次只实现一个 `TASK-xxx`；开始前读取该任务的依赖、验收条件和 Definition of Ready。
- 不得静默修改冻结规格。发现冲突时先创建变更规格，同步功能规格、契约、任务和追踪矩阵。
- 不得回退或覆盖不属于当前任务的工作区修改。

## 新会话读取顺序

1. `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`
2. `docs/specs/architecture.md`
3. `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
4. `docs/specs/001-sakuraplayer-v1/2026-07-24--technical-plan.md`
5. `docs/specs/001-sakuraplayer-v1/implementation-workflow.md`
6. 当前任务文件及其直接引用的契约
7. 涉及 HarmonyOS 任务时，先读 `docs/specs/001-sakuraplayer-v1/2026-07-24--harmonyos-client--tasks.md` 和 `changes/2026-08-04--harmony-baseline-and-device-gate.md`，并加载项目自带 `harmonyos-development` 技能（`run_skill`），再读当前任务文件

## 会话与进度管理

- 新会话读取交接文档后，必须检查 `git status --short`、最近提交和当前任务文件，不得只依赖交接文档判断实际状态。
- 每完成一个 `TASK-xxx`，必须在同一提交中更新 `SESSION-HANDOFF.md` 的当前阶段、已完成任务、下一任务、阻塞项和未完成外部门禁。
- `SESSION-HANDOFF.md` 只记录恢复工作所需的当前状态，不复制完整规格、研究资料或提交历史；提交记录以 Git 为准。
- 正式实施任务以 `docs/specs/001-sakuraplayer-v1/tasks/TASK-xxx.md` 为唯一依据，不得用本地规划文件替代。
- 本仓库不使用 Superpowers 插件，也不得调用或依赖任何 `superpowers:*` 技能；规划、TDD、调试、评审、验证和 Git 收尾均以仓库文档与现有工具为准。
- 预计超过 5 次工具调用、包含多个实施阶段或可能跨会话的任务，使用 `planning-with-files-zh` 的文件规划方式。
- 使用文件规划方式时，临时执行记录放在 `.planning/TASK-xxx/`；`task_plan.md` 只记录执行阶段，外部资料写入 `findings.md`，操作、错误和测试结果写入 `progress.md`。
- `.planning/` 是本地工作记忆，不是冻结规格；如其内容与正式任务文件冲突，以正式任务文件为准。该目录不得包含凭据，也不得纳入任务提交。

## 分层验证与并行协作

- 所有未完成任务按 `implementation-workflow.md` 使用 Focused、Fast、Final 三层验证；Fast 只用于实现反馈，不能替代任务 Definition of Done 或 Final。
- 完整 Compose 只在实现、Fast、完整差异自审和只读审计收敛后进入。每次 Final 尝试最多运行一次完整 Compose；失败后退出 Final，修复并重过受影响的 Fast 与审计，再开始新的 Final 尝试。
- 共享工作区实行单写者。主实施路径负责文件修改、数据库迁移、容器生命周期、暂存和提交；子智能体只并行执行互不依赖的只读审计，主实施路径复核后统一修复。
- 快速测试可以复用无秘密的依赖镜像和专用测试 PostgreSQL 进程，但每次测试必须创建并清理隔离数据库，不得复用开发或生产数据。
- 任务开始前先拆出可独立验证的任务内批次；若要改变正式任务边界，必须先创建变更规格并同步任务索引、依赖、AC 映射和追踪矩阵。

## 实施边界

- Windows 与真实 115 门禁（TASK-213/AC-130）已完成，HarmonyOS 业务功能可以实施；HarmonyOS 不要求连接、授权或侧载 API 24 物理真机，未运行真实设备验证不得宣称真实设备证据已通过（AC-131）。
- 默认自动测试不得访问真实 115、JavDB 写操作或付费 AI。
- 保留根目录用户资料（含三份原始分析文档和 `HarmonyOS/` 试验工程）的未跟踪状态，除非用户明确要求纳入版本控制。

## HarmonyOS 客户端实施规则

- 冻结工具链：DevEco Studio `6.1.1.290`、OpenHarmony SDK API `24`（包标记 `6.1.1.125`）、Hvigor `6.24.3`、ohpm `6.1.2.285`、DevEco 内置 Node `18.20.1`；系统 PATH 中的其他 Node 版本不属于鸿蒙基线，升级需先创建变更规格。
- 只用 Stage 模型 + ArkTS/ArkUI + 原生 `AVPlayer`；不使用 FA 模型、ArkUI-X 或跨平台 UI 运行时。
- 正式工程目录固定为 `harmony/`，`compileSdkVersion/targetSdkVersion=6.1.1(24)`；根目录未跟踪的 `HarmonyOS/`（ArkUI-X 试验产物）不纳入提交、不改造。
- 各功能任务只编辑独立 feature 目录；Navigation 组合根由 TASK-303 统一拥有；所有事件监听使用可注销的命名回调。
- 严格 ArkTS：不得用 `any/unknown` 逃避 OpenAPI DTO 校验，ArkTS strict check 零动态类型逃逸。
- 验证基线：Hvigor sync、ArkTS strict check、debug/release HAP 构建、HAP 内容与开发者签名配置检查；固定 UA、302、Range、HLS、MKV、ASS 协议语义用 ohosTest/fixture 验证；默认测试不访问真实 115、JavDB 写操作或付费 AI。
- `harmonyos-development` 是项目自带技能（`.agents/skills/harmonyos-development/`，不属于 `superpowers:*`，不受禁止条款约束）。涉及鸿蒙的规划、实施、评审、调试和迁移必须先 `run_skill` 加载，并按意图读取其参考文件（如 `build-sign-release`、`navigation`、`state-management`、`permissions`）；其中 ArkTS 规则、Stage 模型、ArkUI 组件与性能规则是鸿蒙任务的实施依据。
- 技能使用边界：生产实现只使用 API 24 Release 能力，不得把 API 26 Beta1 预览 API、版本或行为写入生产代码；API 26 内容仅在用户明确要求预览适配时参考，并明确标注为预览。

## 完成门禁

- 只有当前任务的 Definition of Done、对应验收条件和要求的测试全部满足后，才能标记完成并提交。
- 提交前必须检查完整差异、运行当前任务相关测试，并执行 `git diff --check`；无法运行的测试必须说明原因，不得标记为已通过。
- 完成任务时同步更新任务状态和勾选项；涉及接口、错误码、事件或数据结构时，同步更新对应契约和追踪矩阵。
- 不得通过删除测试、降低断言、扩大跳过范围，或捕获并忽略异常来使测试通过。
- 不得用 Fast 结果、历史 Compose 结果或失败前的局部结果冒充当前 Final 通过。

## 安全边界

- 密钥、115 Cookie、磁力链接、完整签名 URL 和用户密码不得进入 Git、普通日志、测试快照或回复内容。
- 鸿蒙开发者签名材料（`.p12`/`.cer`/`.p7b` 及密码）与 Asset Store 令牌不得进入 Git、普通日志或测试快照；签名配置只引用本地路径。
- 真实 115 测试必须使用显式测试开关和专属测试目录；清理目录前必须验证目标位于应用管理根目录内。
- 不得擅自升级冻结的语言、框架、数据库或客户端版本；确需升级时先创建变更规格。
