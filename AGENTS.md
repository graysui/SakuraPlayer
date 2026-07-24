# SakuraPlayer 协作规则

## 必须遵守

- 每完成一项任务，就提交一次中文 Git；只暂存该任务相关文件，不得顺带提交用户的未跟踪资料。
- 所有需要用户回答的问题都必须通俗易懂，并明确标出推荐答案。
- 一次只实现一个 `TASK-xxx`；开始前读取该任务的依赖、验收条件和 Definition of Ready。
- 不得静默修改冻结规格。发现冲突时先创建变更规格，同步功能规格、契约、任务和追踪矩阵。
- 不得回退或覆盖不属于当前任务的工作区修改。

## 新会话读取顺序

1. `docs/specs/001-sakuraplayer-v1/SESSION-HANDOFF.md`
2. `docs/specs/architecture.md`
3. `docs/specs/001-sakuraplayer-v1/2026-07-24--sakuraplayer-v1.md`
4. `docs/specs/001-sakuraplayer-v1/2026-07-24--technical-plan.md`
5. 当前任务文件及其直接引用的契约

## 实施边界

- Windows 与真实 115 门禁完成前，不实施 HarmonyOS 业务功能。
- 默认自动测试不得访问真实 115、JavDB 写操作或付费 AI。
- 保留三份根目录用户资料的未跟踪状态，除非用户明确要求纳入版本控制。
