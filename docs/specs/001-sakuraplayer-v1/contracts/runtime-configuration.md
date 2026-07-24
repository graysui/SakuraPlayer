# SakuraPlayer v1 运行配置契约

**版本**: 1.0.0

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

调度时区固定为 `Asia/Shanghai`，API 时间固定输出 RFC 3339 UTC，不提供修改项。元数据并发 3、超时 600 秒和 115 的 2/10 上限不是运行配置。

## 3. 启动级秘密

| 用途 | 文件变量 | 环境变量回退 | 格式 |
|---|---|---|---|
| 设置 AES-GCM | `SAKURAPLAYER_SETTINGS_KEY_FILE` | `SAKURAPLAYER_SETTINGS_KEY` | URL-safe Base64 解码后恰好 32 字节 |
| JWT 签名 | `SAKURAPLAYER_TOKEN_KEY_FILE` | `SAKURAPLAYER_TOKEN_KEY` | URL-safe Base64 解码后至少 32 字节 |
| 播放 HMAC | `SAKURAPLAYER_PLAYBACK_KEY_FILE` | `SAKURAPLAYER_PLAYBACK_KEY` | URL-safe Base64 解码后至少 32 字节 |
| 首次初始化 | `SAKURAPLAYER_BOOTSTRAP_TOKEN_FILE` | `SAKURAPLAYER_BOOTSTRAP_TOKEN` | 至少 32 个随机字节的 URL-safe 文本 |

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

## 5. 管理员可修改配置

以下配置通过已认证的 `/api/v1/settings` 保存到 `encrypted_setting`，不作为启动环境变量：

- JavDB 用户名和密码。
- AI `base_url`、`api_key`、`model`、超时。
- 缓存 TTL 1..168 小时。

115 Cookie 只通过扫码流程写入。DMM、演员映射和 GFriends 使用冻结的公共地址，不接受客户端任意 URL。

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
- Windows 可通过 `--dart-define=SAKURAPLAYER_DEFAULT_API_BASE_URL=...` 预置默认值；HarmonyOS 可由本地构建参数预置，但用户仍可在退出登录后修改。
- 更改地址必须先尝试注销当前会话；无论旧服务端是否可达都清除本机令牌、字幕缓存和内存状态，不同服务端的状态不得混合。

## 9. 测试与验收开关

默认测试不读取真实凭据。真实测试必须同时满足显式 marker 和所需 secret：

| 名称 | 用途 |
|---|---|
| `SAKURAPLAYER_TEST_REAL115=1` | Windows/后端真实 115 门禁 |
| `SAKURAPLAYER_TEST_HARMONY_API24=1` | HarmonyOS API 24 真机探针 |

缺少 marker 时套件必须明确 skip，不能尝试网络。测试报告不得输出 secret、Cookie、磁力或完整签名 URL。
