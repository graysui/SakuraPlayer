# ADR-004: Windows 缓存通知使用 flutter_local_notifications

**日期**: 2026-07-31
**状态**: Accepted

## 背景

TASK-202 已交付跨平台的 `AppNotificationSink`、生命周期协调和展示成功后幂等已读，但 Windows 仍使用 `NoopAppNotificationSink`。TASK-209 需要在应用运行或系统后台显示缓存开始、就绪、失败和 115 凭据失效通知；完全退出不常驻，下一次启动由 REST 快照补拉。Windows 客户端固定 Flutter 3.29.2、Dart 3.7.2，不能直接使用要求 Flutter 3.38.1 的最新版通知插件。

## 决策

Windows 固定使用 `flutter_local_notifications` 19.5.0，并接受其 Windows FFI 实现 1.0.3。该系列最低要求 Flutter 3.22.0 / Dart 3.4.0，兼容项目基线；主包和 Windows 实现均使用 BSD 3-Clause 许可，第三方声明由 Windows 工程维护并由 TASK-212 做最终产物审计。

适配器只实现以下能力：

- 启动一次插件并展示即时 Windows toast；
- 用稳定的应用名、AppUserModelId 和 GUID 初始化；
- 将后端通知 UUID 作为不透明 payload，点击后只导航到缓存页，不创建播放会话或自动播放；
- `show` 成功完成才返回 `true`，由既有 `NotificationCoordinator` 调用后端幂等已读；异常返回 `false` 并保留未读事实；
- 不使用定时通知、活动通知查询、取消或依赖 MSIX 包身份的 API。

Windows 未打 MSIX 时，插件不能可靠查询或取消历史通知，但这不影响本任务的即时展示；TASK-212 负责私有安装包和最终系统通知验收。完全退出不运行后台进程，通知只由已运行的客户端连接触发。

## 后果

- `pubspec.yaml` 和锁文件增加一个固定直接依赖及其 Windows FFI/平台接口传递依赖。
- 适配器可以在 Flutter 测试中用注入的插件端口替换，不要求测试机显示真实 toast。
- 通知展示成功表示客户端已交给 Windows 通知 API，不等同于用户已经点击或阅读；后端 `read_at` 只表示展示成功。

## 替代方案

- `flutter_local_notifications` 22.x：要求 Flutter 3.38.1 / Dart 3.10，越过冻结工具链，拒绝。
- `local_notifier` 0.1.6：兼容工具链且为 MIT，但版本较旧、额外要求 Windows shortcut 策略，且不复用项目选择的通知 DTO/平台接口，拒绝。
- 自写 C++/WinRT FFI：避免 Dart 依赖但重复实现 toast 生命周期、打包身份和 ABI，超出 TASK-209，拒绝。
