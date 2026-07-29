# Change Specification: TASK-202 客户端基础确定性边界

**日期**: 2026-07-29
**状态**: Accepted
**影响任务**: TASK-202、TASK-209、TASK-302
**影响 AC**: AC-002、AC-011、AC-012、AC-115、AC-116、AC-117、AC-133、AC-135

## 1. 背景

TASK-202 实施预审发现四处未闭合边界：Dio、安全存储和 `client_instance_id` 同时被写成
任务前置与本任务产出；刷新令牌轮换没有定义并发 401；REST 快照只有全局水位而不携带各
聚合版本；TASK-202 与 TASK-209 都声称拥有 Windows 系统通知，但只有 TASK-209 拥有平台
通知文件。OpenAPI DTO 也未冻结生成工具，而架构禁止静默增加代码生成依赖。

后端实际接口确认，无 `after_event_id` 的 WebSocket 会从保留窗口内最早事件开始按全局
`sequence` 重放。客户端应用快照后可安全忽略 `sequence <= snapshot_version` 的事件，并用
水位后的第一条同资源事件建立聚合版本基线，无需修改后端快照结构。

## 2. 变更要求

- REQ-CHG-158: 架构已冻结 `dio 5.7.0` 和 `flutter_secure_storage 9.2.0`。TASK-202 第一批次
  将二者加入 Windows 直接依赖并更新锁文件；不得引入 DTO、路由或序列化代码生成器。
- REQ-CHG-159: `client_instance_id` 由 TASK-202 首次启动时生成 UUID v4 并通过
  `flutter_secure_storage` 安全持久化。它在 logout、refresh 失败和更换服务端地址时保留，
  只有卸载或安全存储被系统清除时重新生成。
- REQ-CHG-160: 多个业务请求同时收到 401 时，共用一个 single-flight refresh。等待者使用
  同一轮新 token 各自最多重放一次；login、bootstrap、refresh、logout 和匿名连接测试不得
  进入 refresh 循环。refresh 失败原子清除内存 access 与安全存储 refresh。
- REQ-CHG-161: 应用 REST 快照后，对快照内资源记录“聚合版本未知”而不是猜测为 0。
  WebSocket 无游标重连并忽略 `sequence <= snapshot_version`；水位后第一条属于快照内已有
  资源的合法事件可浅合并并建立 `stream_version` 基线。基线建立后仍严格要求下一版本为
  `local_version + 1`。本地没有资源、全局 sequence 跳号、未知事件版本或字段非法仍拉快照。
- REQ-CHG-162: TASK-202 拥有进程生命周期、通知投递端口、未读恢复和展示成功后的幂等已读；
  测试使用 fake port。TASK-209 拥有 Windows 系统通知适配器、缓存通知文案/导航和“不自动
  播放”策略。TASK-202 不新增未冻结的平台通知依赖，也不得在无真实投递时提前标记已读。
- REQ-CHG-163: Windows v1 使用手写、不可变、严格解析的 OpenAPI/事件 DTO。JSON 只在
  网络边界表现为 `Map<String, Object?>`；缺字段、错类型、未知枚举或非法事件形状必须产生
  类型化协议错误或触发一次快照，不得把动态 map 传入业务层。
- REQ-CHG-164: 更换后端地址先尝试用旧地址/logout token 注销；无论请求成功、TLS 失败或
  旧服务端不可达，都清除本机 token、字幕缓存、事件游标/快照和内存状态，再保存新地址。

## 3. 行为边界

### 快照与事件

快照的 `snapshot_version` 是客户端恢复的唯一全局水位，`last_event_id` 只用于诊断和可用时的
游标信息。客户端应用快照后使用无游标连接，让后端重放仍保留的事件；旧事件由全局水位过滤。
快照不新增每资源版本字段，避免把后端聚合版本表扩散到所有公开 DTO。

### 通知所有权

TASK-202 提供可注销的生命周期监听和 `AppNotificationSink` 端口。只有 sink 明确返回已展示，
客户端才调用幂等已读 API。TASK-209 接入 Windows 平台通知后完成 AC-117 的可见平台行为；
两任务共享 AC 映射不表示 TASK-202 提前拥有 TASK-209 的平台文案和导航。

### 本地持久化

access token 和 bootstrap token 只存在内存。refresh token、稳定客户端实例 ID 和后端基址经
统一存储端口保存；基址虽非秘密，允许复用安全存储以避免新增未冻结 preferences 依赖。
密码只存在输入控件和当前请求作用域，控制器不持久化。

## 4. 同步与验证

| 工件 | 变更 | 风险 |
|---|---|---|
| TASK-202 | DoR、并发刷新、客户端 ID、DTO、通知和地址切换 | HIGH |
| realtime-events | 快照后的未知聚合版本基线 | HIGH |
| technical plan | AD-008 客户端恢复算法 | MEDIUM |
| TASK-209 | Windows 系统通知适配器所有权 | MEDIUM |
| TASK-302 | 后续复用相同 single-flight/版本基线原则 | LOW |
| traceability matrix | 记录新确定性边界 | LOW |

本变更与 TASK-202 实现、测试、任务状态和交接在同一中文提交中交付，不创建独立 TASK-CHG。

## 5. 回滚

TASK-202 提交前可整体回退本变更与客户端实现。提交后若要给快照增加聚合版本、引入 DTO
生成器或调整系统通知依赖，必须以前向变更规格同步 OpenAPI、架构、任务和追踪矩阵。
