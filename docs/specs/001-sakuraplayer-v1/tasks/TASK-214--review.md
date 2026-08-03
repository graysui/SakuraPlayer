# TASK-214 Windows 客户端代码清理 Review Report

**日期**: 2026-08-03
**状态**: Approved
**Git 范围**: `508643ec4332aa3563f301d41164d1637abbce6a..7d377d1`
**审查范围**: TASK-201..213 及其后置 TASK-215/218/219/220/221/222/223/226/227 的 Windows 变更，共 131 个历史文件。

## 批准清理文件

| 文件 | 发现 | 批准动作 |
|---|---|---|
| `windows/lib/app/composition_root.dart` | 两处 best-effort 字幕缓存清理失败使用 `debugPrint` 输出固定调试文本 | 删除调试输出；保留异常吞吐、异步时序和运行恢复行为，并用必要注释说明 best-effort 边界 |

除上表外，不批准修改其他产品、测试、工具、配置、生成文件、依赖锁或资源文件。若实现中发现行为缺陷，退出 TASK-214 并创建独立任务，不得借清理修改逻辑。

## 保留项

- `windows/integration_test/real115_probe_test.dart` 的结构化 `print` 是 TASK-213 脱敏验收证据协议，必须保留。
- `temporary` 命中是原子临时文件或测试名称；Android/iOS/Linux/macOS/Web 字符串用于验证发布包只包含 Windows 平台，必须保留。
- Flutter 生成插件注册、Windows runner/CMake、图标、许可证、NOTICE、`pubspec.lock` 和发布脚本没有确认债务，不手工修改。
- 固定 Windows UA、播放器签名、seek 合并、路由、DTO 与状态机不在清理范围。

## 清理前基线

- `dart format --output=none --set-exit-if-changed lib test integration_test`: 97 文件，0 变更。
- `flutter analyze`: 零问题。
- `dart fix --dry-run`: 无建议修复。
- `flutter test`: 233 项通过。
- `flutter test -d windows integration_test/windows_user_journey_test.dart`: 4 项通过。
- `flutter build windows --release`: 通过。

## 结论

Review approved。TASK-214 只能执行上表两处调试输出卫生清理，并在修改后重跑格式、分析、完整测试、Windows integration 和 Release；必须通过差异审计证明无逻辑或签名变化。
