# Change Specification: HarmonyOS 工具链基线与 API 24 真机门禁撤销

**Type**: Delta
**Date**: 2026-08-04
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

根据开发机已安装环境更新 HarmonyOS 冻结工具链版本，并撤销 API 24 物理真机连接、侧载和真机播放探针作为鸿蒙开发前置条件。API 24 仍是编译 SDK、ArkTS/ArkUI API 和 AVPlayer 签名基线；Windows 真实 115 门禁、开发者签名侧载和 HarmonyOS 播放产品方向不变。

## MODIFIED

- **AC-007**：HarmonyOS 继续使用 API 24、ArkTS/ArkUI、Stage 模型和原生 `AVPlayer`。冻结工具链改为 DevEco Studio `6.1.1.290`、OpenHarmony SDK API `24`（本机包标记 `6.1.1.125`）、Hvigor `6.24.3`、ohpm `6.1.2.285` 和 DevEco 内置 Node `18.20.1`。系统 PATH 中的其他 Node 版本不属于该基线。
- **AC-131**：由“真实 API 24 设备探针”改为“安装 SDK API 24 签名核验、ArkTS/ArkUI/能力构建检查、自动化单元/契约 fixture 验证”。验证固定 User-Agent、302、Range、HLS、MKV 和 ASS 的协议及状态语义，但不得要求连接、授权或侧载 API 24 物理真机；未运行真实设备验证不得宣称真实设备证据已通过。
- HarmonyOS 进入条件改为 Windows AC-130 已完成、TASK-301 工具链和 Stage 工程检查通过；不再等待 AC-131 真机门禁。

## RETIRED TASK

- `TASK-312` 的主动实施和外部门禁职责撤销。原任务文件保留并标记为已撤销，作为历史变更记录，不再进入后续任务依赖、DoR、DoD 或发布门禁。

## Task Synchronization

- 更新 TASK-301、TASK-302、TASK-310、TASK-311、TASK-313、TASK-314 的工具链、验证和依赖描述。
- 更新 HarmonyOS 任务索引、总任务索引、追踪矩阵、运行配置契约、架构、技术计划、README、用户需求和会话交接。
- 保留 `TASK-312.md` 文件但将状态改为 `cancelled`；不创建 probe 工程、真机证据表或真实设备 marker。

## Testing Strategy

- 工具链：记录 DevEco、SDK API 24、Hvigor、ohpm 和 DevEco 内置 Node 的已安装版本。
- 工程：执行 Hvigor sync、ArkTS strict check、debug/release HAP 构建、HAP 内容检查和开发者签名配置检查。
- 自动化：执行 ohosTest/fixture 覆盖固定 UA、302、Range、HLS、MKV、ASS、生命周期和错误隔离；测试不访问真实 115，不连接物理真机。
- 真实设备运行证据属于未执行项，不得以 SDK、构建或 fixture 结果代替真实设备证据。

## Rollback Plan

若后续发现必须支持某个物理设备特有行为，应先创建新的变更规格，重新定义设备范围、证据和外部门禁，再单独同步任务与追踪矩阵；不得在实现任务中静默恢复 TASK-312。
