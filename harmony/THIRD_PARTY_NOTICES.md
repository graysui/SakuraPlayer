# Third-Party Notices

SakuraPlayer 以 GPL-3.0-only 分发。二进制分发必须包含适用的 GPL 文本、本声明，以及所有打包进 HAP 的第三方依赖声明。

## @ohos/hypium 1.0.25

@ohos/hypium 是 OpenHarmony 单元测试框架（arkxtest JsUnit），Copyright OpenHarmony 贡献者，以 Apache License 2.0 分发。许可文本见
<https://www.apache.org/licenses/LICENSE-2.0>，源码见 <https://ohpm.openharmony.cn/ohpm/@ohos/hypium>。

## @ohos/hamock 1.0.0

@ohos/hamock 是 OpenHarmony mock 测试库，Copyright OpenHarmony 贡献者，以 Apache License 2.0 分发。许可文本见
<https://www.apache.org/licenses/LICENSE-2.0>，源码见 <https://ohpm.openharmony.cn/ohpm/@ohos/hamock>。

## HarmonyOS SDK 与 DevEco Studio 工具链

工程使用 DevEco Studio 6.1.1.290、OpenHarmony SDK API 24（包标记 6.1.1.125）、Hvigor 6.24.3、ohpm 6.1.2.285 与 DevEco 内置 Node 18.20.1。SDK 与工具链是构建环境组件，不打包进 HAP 产物，其使用受华为开发者协议约束。本工程不包含第三方 C/C++ 原生库，播放使用系统 Media Kit 原生 AVPlayer 能力。

## 移植来源声明

鸿蒙客户端未移植 Windows/Flutter 客户端代码，仅复用后端 OpenAPI、事件、错误码契约与固定 User-Agent 约定；UI 源码为独立编写。后端、Windows 客户端与发布脚本的许可证与来源声明分别见仓库根 LICENSE、windows/THIRD_PARTY_NOTICES.md 与各模块 NOTICE。
