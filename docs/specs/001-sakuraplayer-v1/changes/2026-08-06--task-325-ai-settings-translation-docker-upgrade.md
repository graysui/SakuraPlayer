# Change Specification: TASK-325 AI 配置恢复、翻译瘦身与 Docker 原地升级

## 背景

Windows 管理员在“AI 翻译”中替换配置后，页面只采用 PATCH 响应并以不完整签名同步输入框，客户端重启后可能继续显示初始化时的旧值。现有 `sakuraplayer-zh-v2` 又会在每个字段请求中重复发送番号、全部演员、厂商、系列和标签，并要求模型完整回显；缺少 Actor Mapping 中文简介的演员还会进入付费 AI。Linux 远程安装器在已有 `.env` 时不会切换官方镜像版本，因此下载新 Release 后仍可能运行旧后端镜像。

## 变更

- REQ-CHG-312：新增 TASK-325，依赖 TASK-208、TASK-225 和 TASK-323，统一交付 AI 配置持久恢复、翻译请求瘦身和现有 Docker 部署原地升级。
- REQ-CHG-313 / AC-119：AI replace 成功后 Windows 必须重新读取权威 `/settings`；输入字段同步必须包含可回显的 AI base URL、model、timeout、configured 与 version。重新创建页面或重启客户端后只显示 PostgreSQL 中当前加密配置的非秘密投影，API key 仍只显示 configured 状态。
- REQ-CHG-314 / AC-055/056：AI 只翻译影片标题和影片简介，演员简介不再创建新 AI 请求。请求不得携带番号、演员、厂商、系列或标签原值；这些值实际出现在当前标题或简介时，由后端先替换为无业务含义占位符，严格校验响应中的占位符集合和次数后再本地恢复。
- REQ-CHG-315 / AC-056：新请求使用前向 `sakuraplayer-zh-v3` 协议；模型输出只允许 `schema_version` 和 `translated_text`。输出 token 上限按脱敏后的当前文本字符数保守估算，不再按完整 protected JSON 的 UTF-8 字节数和 1024/2048 固定下限扩张。
- REQ-CHG-316 / AC-057：v1/v2 的 reserved、dispatched、completed、rejected 和 unknown 记录保持不可变且不自动重派；v3 形成新业务键。历史演员 AI 译文和记录保留，但新任务不读取、修改或创建 `actor_bio` 付费事实。
- REQ-CHG-317 / AC-148/149/151：在现有安装目录再次运行 `install-latest.sh` 时，只允许把受支持的 Docker Hub 或 GHCR 官方完整 SemVer 镜像升级到当前 Release，保留 registry 并拒绝降级。覆盖发布文件前必须拒绝自定义、本地、digest、latest、缺失或重复镜像配置；`.env` 其余配置、`secrets/`、`data/`、PostgreSQL、加密设置、已刮削目录和 Compose override 原样保留，不执行 `down -v` 或删除旧卷。

## 范围与安全

- 默认测试只使用固定替身，不访问真实付费 AI、115、JavDB 写操作或 MGDB 网络。
- AI 请求和普通日志不得包含 API key、原始 protected 元数据、完整 source、译文、完整请求或响应。
- Docker 升级只自动管理明确受支持的官方镜像版本行；无法证明安全时在复制新发布文件和启动 Compose 前失败。
- 本变更不迁移或删除旧 translation 记录，不新增数据库迁移，不改变现有 bind mount 路径。

## 回滚

发布前可整体回退 TASK-325。发布后不得恢复 v2 新派发、演员 AI 翻译或覆盖式 Docker 安装；如需改变协议或镜像来源，必须建立新的前向变更并保留既有数据库、设置和付费事实。

## 验证边界

- Windows controller/widget 测试覆盖 replace 后权威 GET、相同 version 内容变化同步，以及页面重建后恢复当前 AI 非秘密配置。
- 后端设置集成测试覆盖 replace 后重建 service/store 并 GET，值与 version 保持一致且秘密不回显。
- 翻译单元/集成测试断言请求正文不含番号、演员、厂商、系列、标签，只有标题/简介进入 adapter，占位符缺失、重复、变形或伪造全部拒绝，v1/v2 事实不变。
- Linux 安装器测试比较升级前后 `.env` 非镜像内容、secret 和 data 文件字节不变，并覆盖同版本、升级、降级、自定义镜像、digest/latest 和非法布局。
