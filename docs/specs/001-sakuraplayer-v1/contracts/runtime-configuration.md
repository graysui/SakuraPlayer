# SakuraPlayer v1 运行配置契约

**版本**: 1.6.0

**适用范围**: Docker 后端、Windows 客户端、HarmonyOS 客户端、显式外部验收

## 1. 配置优先级

启动级秘密只允许来自 Docker Secret 文件或进程环境变量。存在 `_FILE` 时必须优先读取文件，并拒绝同时设置同名明文变量；客户端设置 API 不得读取、修改或回显这些值。

普通配置优先级：命令行测试覆盖 > 环境变量 > 固定默认值。生产环境不得读取仓库内 `.env` 文件；仓库只提供不含秘密的 `.env.example`。

## 2. 后端普通配置

| 名称 | 必填 | 默认值 | 规则 |
|---|---|---|---|
| `SAKURAPLAYER_ENV` | 是 | `development` | `test/development/production-private/acceptance-real115` |
| `SAKURAPLAYER_DATABASE_URL` | 是 | 无 | PostgreSQL DSN；生产不允许 SQLite |
| `SAKURAPLAYER_LOG_LEVEL` | 否 | `INFO` | `DEBUG/INFO/WARNING/ERROR`；秘密仍必须脱敏 |
| `SAKURAPLAYER_PUBLISH_HOST` | 否 | `127.0.0.1` | Compose 宿主发布地址；远程访问必须显式设置私网地址 |
| `SAKURAPLAYER_API_PORT` | 否 | `8000` | 1..65535 |
| `SAKURAPLAYER_TRUST_PROXY_HEADERS` | 否 | `false` | 只有受控反向代理部署可设为 `true` |
| `SAKURAPLAYER_JAVDB_HOST` | 否 | `jdforrepam.com` | 仅允许无 scheme、端口、userinfo、路径、query 或 fragment 的 DNS hostname |

调度时区固定为 `Asia/Shanghai`，API 时间固定输出 RFC 3339 UTC，不提供修改项。元数据并发 3、超时 600 秒和 115 的 2/10 上限不是运行配置。

## 3. 启动级秘密

| 用途 | 文件变量 | 环境变量回退 | 格式 |
|---|---|---|---|
| 设置 AES-GCM | `SAKURAPLAYER_SETTINGS_KEY_FILE` | `SAKURAPLAYER_SETTINGS_KEY` | URL-safe Base64 解码后恰好 32 字节 |
| JWT 签名 | `SAKURAPLAYER_TOKEN_KEY_FILE` | `SAKURAPLAYER_TOKEN_KEY` | URL-safe Base64 解码后至少 32 字节 |
| 播放 HMAC | `SAKURAPLAYER_PLAYBACK_KEY_FILE` | `SAKURAPLAYER_PLAYBACK_KEY` | URL-safe Base64 解码后至少 32 字节 |
| 首次初始化 | `SAKURAPLAYER_BOOTSTRAP_TOKEN_FILE` | `SAKURAPLAYER_BOOTSTRAP_TOKEN` | 至少 32 个随机字节编码为无 padding Base64URL 文本（43..512 字符） |

设置密钥还需要非秘密标识 `SAKURAPLAYER_SETTINGS_KEY_ID`，v1 默认 `v1`。四种用途不得复用相同字节。生产模式缺少、格式错误或检测到复用时，API、worker 和 scheduler 均拒绝启动且日志只输出变量名称和稳定错误码。

JWT 与播放 key 轮换会使既有访问令牌或播放能力失效。v1 不提供在线密钥轮换 UI；轮换必须在维护窗口完成。设置 AES 密钥不可在未重加密既有 `encrypted_setting` 前直接替换。

## 4. PostgreSQL Secret

官方 Compose 使用：

| 名称 | 规则 |
|---|---|
| `POSTGRES_DB` | 默认 `sakuraplayer` |
| `POSTGRES_USER` | 默认 `sakuraplayer` |
| `POSTGRES_PASSWORD_FILE` | 必须指向 Docker Secret；生产不接受仓库内明文密码 |

Compose 可在容器内组装 `SAKURAPLAYER_DATABASE_URL`，但最终 DSN 不得打印到日志或诊断响应。PostgreSQL 宿主端口不发布。

### 4.1 Compose 后端镜像

`SAKURAPLAYER_BACKEND_IMAGE` 只用于 Compose 插值，不注入应用进程。默认值为 `sakuraplayer-backend:local`，配合 `docker compose up --build` 从当前源码构建。使用 GitHub Release 对应镜像时，可显式设为 `ghcr.io/graysui/sakuraplayer-backend:X.Y.Z` 或 `docker.io/graysui/sakuraplayer-backend:X.Y.Z`，先 `docker compose pull`，再以 `docker compose up --no-build` 启动；同一正式版本在两个 registry 指向同一 digest。

API、migrate、worker、scheduler 必须引用相同的 `SAKURAPLAYER_BACKEND_IMAGE`，只通过 Compose `command` 区分进程；不得混用不同版本或仅更新其中一个进程。生产部署优先使用不可变 digest，其次使用完整 `X.Y.Z`，不得依赖可移动的 `latest` 做无人值守升级。

### 4.2 Linux 一键安装

正式 Release 的 Linux Docker 部署包提供 `install.sh`，由宿主机负责准备配置，业务容器仍只消费本节冻结的文件变量。脚本必须满足：

- 从脚本自身目录定位 `docker-compose.yml`、`.env.example` 和 `.release-version`，不依赖调用者当前目录。
- 只在 `.env` 缺失时由模板原子创建，并把后端镜像固定为 `docker.io/graysui/sakuraplayer-backend:X.Y.Z`；已存在 `.env` 视为操作者配置，不自动覆盖。
- 远程 `install-latest.sh` 首次安装把发布文件、`.env`、`secrets/` 和 `data/` 持久化到执行命令时的当前目录；下载和解压中间文件才允许留在临时目录。首次交互运行可选择合法 IPv4 发布地址和 `1..65535` API 端口，直接回车或无 TTY 时使用 `127.0.0.1:8000`，并把选择写入 `.env`。已有 `.env` 不询问；只允许把单一 Docker Hub/GHCR 官方完整 SemVer 镜像行升级到当前 Release 并保留 registry，其他行保持不变。相同版本不改写 `.env`；降级、自定义、本地、digest、`latest`、缺失或重复镜像行在发布文件覆盖前拒绝。旧归档使用 `sakuraplayer_*` named volume 时，安装器在 Compose 启动前复制到对应 `data/` 子目录且不删除旧卷。
- 以 `umask 077` 创建 `secrets/`，五个文件分别使用 32、32、48、48、48 个 CSPRNG 字节编码为无 padding Base64URL；文件名和 Compose 引用保持现有契约。
- 生成前获取单实例文件锁；拒绝 secret 目录/文件符号链接、非普通文件、错误长度、非规范字符或用途复用。有效既有文件保持内容不变，只允许把目录/文件权限收紧到 `0700/0600`。
- 新文件先写同目录临时文件、验证后原子安装；中断或 Compose 失败不得删除或重新生成已完成的 secret，重复执行可安全恢复。
- 标准输出和错误只包含稳定阶段、非敏感错误、默认访问地址和 `bootstrap_token.txt` 路径，不得输出任何 secret 值、摘要、长度以外的派生材料或完整数据库 DSN。
- 启动顺序固定为 `docker compose config`、`pull`、准备/同步 PostgreSQL 凭据、`up -d --no-build --wait`；成功以 Compose 健康条件为准，默认发布地址仍为 `127.0.0.1`。已有数据库必须先同步当前 `postgres_password.txt` 对应的角色密码，避免旧数据库与新 secret 不一致导致迁移认证失败。

源码仓库中的 `backend/install.sh` 可从 `windows/pubspec.yaml` 推导当前完整 SemVer；正式部署包必须带严格 `X.Y.Z` 的 `.release-version`，不依赖 Git、Flutter 源码或 `latest` 标签。包内 `install.sh` 不负责升级既有 `.env`；远程 `install-latest.sh` 只负责上述官方 SemVer 原地升级。两者都不负责备份、在线密钥轮换、证书签发或公网暴露。

## 5. 管理员可修改配置

以下配置通过已认证的 `/api/v1/settings` 保存到 `encrypted_setting`，不作为启动环境变量：

- JavDB 用户名和密码；两者作为单个 `javdb.credentials` 加密 JSON envelope 原子 CAS，不保存分键明文。
- AI `base_url`、`api_key`、`model`、超时。
- MGDB GitHub 数据源仓库地址，使用 `mgdb.source` AES-GCM envelope 和对象级 CAS；不配置时不执行同步网络请求。
- 缓存 TTL 1..168 小时。

115 Cookie 只通过扫码流程写入。DMM、演员映射和 GFriends 使用冻结的公共地址，不接受客户端任意 URL。MGDB 只接受契约规定的 GitHub 仓库 URL；JavDB host 只允许由受控部署环境设置，客户端设置 API 不提供修改入口。

TASK-010 将 AI 四字段以单个 key `ai.configuration` 的 AES-GCM JSON 载荷保存并使用版本 CAS 原子更新，避免 provider 地址、模型和 key 来自不同配置版本。`base_url` 是绝对 `http/https` provider root，最长 2048 字符，不得包含 userinfo、query 或 fragment；尾部 `/` 在保存前移除。`base_url` 可带 `/v1` 尾段也可不带，两种形态等价：带 `/v1` 尾段时直接作为 OpenAI 兼容 API 版本前缀（chat completions 端点 `{base_url}/chat/completions`、models 端点 `{base_url}/models`），不带时请求自动追加 `/v1`（REQ-CHG-323/324 修订 REQ-CHG-075）。`model` 为 1..255 字符，`api_key` 为 1..8192 UTF-8 字节，`timeout_seconds` 为 1..600。TASK-013 的设置 API 解密后只回显 base_url/model/timeout 和 `api_key_configured`，不回显 key；Windows replace 后和页面重建时以权威 GET 恢复这些非秘密值。

TASK-009 固定公共地址：

| 用途 | 固定地址 |
|---|---|
| Actor Mapping | `https://raw.githubusercontent.com/li-peifeng/Jav-Actors-Mapping/main/actor-mapping.xml` |
| GFriends Filetree | `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Filetree.json` |
| GFriends Content 基址 | `https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content` |

三个地址不是环境变量或管理员设置。实现必须使用完整 URL 等值校验；不得允许上游载荷改变 scheme、主机、仓库、分支或固定资产路径。

## 6. 首次管理员初始化

1. 操作者生成 bootstrap token 并通过 Secret/环境变量提供。
2. 客户端先读取 `/auth/bootstrap-status`。
3. 若尚无管理员，创建请求同时提交 bootstrap token、用户名、密码和客户端实例 ID。
4. 服务端以常量时间比较 token；成功创建唯一管理员后，所有后续 bootstrap 请求都返回 `bootstrap_already_completed`，即使 token 正确。
5. token 不写数据库、事件、普通日志或 API 响应。v1 中它仍是 API、worker 和 scheduler 的启动依赖，但管理员创建后永久失去初始化权限；运维可轮换其值，不得从运行配置中移除。

## 7. 网络与传输

- Compose 默认发布到 `127.0.0.1`。
- 同机 Windows 客户端可使用 loopback HTTP。
- 其他设备必须通过 HTTPS 反向代理或可信加密 VPN 访问。
- 明文 HTTP 远程地址只允许 RFC1918 IPv4 或 IPv6 ULA/链路本地地址，并要求客户端一次明确风险确认；不得接受公网 IP 或公网主机名的明文 HTTP。
- API 不提供自动证书签发或公网部署向导。

## 8. 客户端后端地址

客户端保存一个非敏感的 `api_base_url` 本机设置：

- 必须是绝对 `http` 或 `https` URL。
- 禁止 userinfo、query、fragment 和路径穿越；规范化后路径为 `/api/v1`。
- 保存前调用 `/auth/bootstrap-status` 做连接测试，并显示 TLS、超时和 API 版本错误。
- HTTPS 接受系统信任链，不提供“忽略证书错误”开关。
- Windows 可通过 `--dart-define=SAKURAPLAYER_DEFAULT_API_BASE_URL=...` 预置默认值；仅在没有已保存地址时校验、测试并保存该值，已保存地址优先且非法默认值不得绕过同一地址策略。HarmonyOS 可由本地构建参数预置，但用户仍可在退出登录后修改。
- 更改地址必须先尝试注销当前会话；无论旧服务端是否可达都清除本机令牌、字幕缓存和内存状态，不同服务端的状态不得混合。

## 9. 测试与验收开关

默认测试不读取真实凭据。真实测试必须同时满足显式 marker 和所需 secret：

| 名称 | 用途 |
|---|---|
| `SAKURAPLAYER_TEST_REAL115=1` | Windows/后端真实 115 门禁 |
| `SAKURAPLAYER_TEST_HARMONY_API24_FIXTURE=1` | HarmonyOS API 24 SDK/契约 fixture 验证；不连接物理真机、不代表真实设备证据 |

缺少 marker 时套件必须明确 skip，不能尝试网络。测试报告不得输出 secret、Cookie、磁力或完整签名 URL。

Windows real115 harness 还要求以下本地运行环境；这些值不写入仓库、发布包或测试快照：

| 名称 | 用途与约束 |
|---|---|
| `SAKURAPLAYER_REAL115_API_BASE_URL` | 待验收后端 `/api/v1` 基址；遵循客户端后端地址规则 |
| `SAKURAPLAYER_REAL115_USERNAME` | 专用验收管理员用户名；不得输出 |
| `SAKURAPLAYER_REAL115_PASSWORD` | 专用验收管理员密码；不得输出 |
| `SAKURAPLAYER_REAL115_MOVIE_ID` | 位于验收样本内的影片 UUID |
| `SAKURAPLAYER_REAL115_SOURCE_ID` | 位于应用受管测试根的来源 UUID |
| `SAKURAPLAYER_REAL115_CONFIRM_MANAGED_ROOT=1` | 操作者确认样本只使用应用受管测试根；缺少时拒绝运行 |
| `SAKURAPLAYER_REAL115_SKIP_EXTERNAL_SUBTITLES=1` | 仅 TASK-213 本轮按批准 Delta 跳过真实 `.srt` / `.ass` 样本下载；默认不设置，其他非空值拒绝 |

TASK-212 harness 只输出阶段、HTTP 状态以及 source/job/session UUID，并把二维码 PNG 临时写入系统临时目录；结束时删除二维码副本。失败后若仍有 job/session，仅输出其 UUID 供操作者通过后端受管接口清理，不输出 Cookie、密码、磁力、二维码内容或完整能力 URL。TASK-213 负责实际执行、专属目录确认与 AC-130 最终证据；本轮外置字幕豁免必须输出 `subtitle_external_skipped state=operator_approved`，不得写成 `subtitle_download`。
