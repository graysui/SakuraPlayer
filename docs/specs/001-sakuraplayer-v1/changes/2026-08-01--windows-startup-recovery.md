# Change Specification: Windows 启动初始化恢复

**Type**: Delta
**Date**: 2026-08-01
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-219 热更新实际启动发现：Windows 在读取本机安全存储时可能无限停留在初始化状态，且服务端地址输入也被同一个 busy 状态禁用，用户无法手工恢复。本变更新增 TASK-220，为启动初始化增加有界失败恢复，并在初始化期间保留地址编辑能力；地址保存仍必须等待初始化结束并通过既有安全策略和连接测试。

## ADDED

- REQ-CHG-250: Windows 认证初始化必须包含生产默认 5 秒的总超时，覆盖客户端实例 ID、本机服务端地址、默认地址探测、已保存地址探测和会话恢复链路；测试可注入更短超时。
- REQ-CHG-251: 初始化超时必须进入 `serverRequired` 且清除 busy，并显示中文可恢复提示；非网络的本机初始化异常也必须进入同一可编辑状态，使用稳定本地错误码且不得暴露异常、路径或安全存储内容。
- REQ-CHG-252: 初始化期间服务端地址文本框保持可编辑，但私网 HTTP 确认、提交地址和认证操作保持禁用；初始化成功、超时或失败后再按既有状态启用。
- REQ-CHG-253: 超时或本机异常恢复不得删除已保存地址、刷新令牌、客户端实例 ID、字幕或其他私有缓存；手工保存仍必须经过 AC-135 地址策略、连接测试和地址切换清理语义。
- REQ-CHG-255: 初始化超时后必须使原初始化代次失效；底层 Future 迟到完成不得覆盖恢复状态或随后成功保存的手工地址。恢复后的手工配置若再次遇到本机存储超时或异常，也必须清除 busy 并显示中文本地错误。
- REQ-CHG-256: Windows 真实安全存储的文件读取和 DPAPI 加解密必须在可终止的后台 isolate 执行；UI isolate 只等待有界结果。后台失败或超时不得删除、重命名、覆盖或记录现有安全存储文件及其内容。

## MODIFIED

- REQ-CHG-254: TASK-214 增加 TASK-220 依赖；TASK-217 的首次 provider/ranking 快照边界和优先级不变。

## Acceptance Criteria

- [x] 安全存储 Future 永不完成时，Windows 最迟在初始化超时后停止转圈并显示中文恢复提示。
- [x] 安全存储抛出非网络异常时，Windows 不会永久停留在 initializing/busy。
- [x] 初始化进行中可以输入服务端地址，但不能提交或绕过私网 HTTP 确认。
- [x] 初始化失败不清除现有本机状态，恢复后的手工配置仍执行既有安全校验和连接测试。
- [x] 初始化底层 Future 迟到完成不能覆盖恢复状态或新的手工配置，本机配置失败不能再次永久 busy。
- [x] 真实 Windows 安全存储不会同步阻塞 UI isolate，后台超时可终止且不修改现有安全存储文件。

## Testing Strategy

- Windows Focused 覆盖永不完成的安全存储 Future、同步/异步本机异常、初始化期间地址输入和提交禁用。
- Fast/Final 按统一实施流程运行 `dart format`、`flutter analyze`、完整 `flutter test`、Windows release build，并直接启动 Release 产物确认页面恢复。
- 默认测试不访问真实 115、JavDB 写操作或付费 AI。

## Rollback Plan

只能通过新的前向变更调整初始化时限或恢复文案；不得移除有界恢复、放宽地址安全策略或以清除用户本机状态作为启动手段。
