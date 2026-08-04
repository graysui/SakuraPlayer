# SakuraPlayer Linux Docker 部署

这个目录是固定版本的官方 Docker 部署包，不需要克隆源码。

## 环境要求

- Linux x86_64 主机或 NAS
- Docker Engine
- Docker Compose v2
- OpenSSL、`flock`

## 一键安装

推荐直接复制下面这一行执行。它会自动找到最新正式 Release、下载 Docker 部署包、临时解压并启动服务，不需要手动下载 Release、解压或执行 SHA256 校验：

```bash
curl -fsSL https://raw.githubusercontent.com/graysui/SakuraPlayer/main/backend/install-latest.sh | bash
```

也可以在已解压的官方部署包目录执行本地安装器：

```bash
./install.sh
```

安装器会创建发布版 `.env`，自动生成五个用途独立的强随机 secret，拉取当前固定版本镜像，并等待所有服务健康。重复执行会保留有效的 `.env`、secret 和 Docker volumes，不会重置数据库密码或加密密钥。

成功后，API 默认只监听 `http://127.0.0.1:8000`。首次创建管理员时，按安装器提示读取 `secrets/bootstrap_token.txt`；不要把内容发到聊天、日志或截图中。

## 私网访问

默认 loopback 适合同机使用或放在 HTTPS 反向代理后。确需从可信局域网访问时，编辑 `.env` 中的 `SAKURAPLAYER_PUBLISH_HOST` 为服务器私网 IP，再执行：

```bash
./install.sh
```

不要填写 `0.0.0.0`，也不要把 API 端口映射到公网。远程访问必须使用 HTTPS 或可信加密 VPN。

## 常用命令

```bash
# 查看状态
docker compose --env-file .env -p sakuraplayer ps

# 查看脱敏日志
docker compose --env-file .env -p sakuraplayer logs --tail 200

# 停止服务并保留数据
docker compose --env-file .env -p sakuraplayer down

# 再次启动或应用配置
./install.sh
```

不要执行 `docker compose down -v`，它会删除数据库、图片和缓存卷。SakuraPlayer v1 不提供自动备份；升级或迁移前请自行备份 Docker volumes、`.env` 和 `secrets/`。

正式 Release 仍会提供 SHA256 文件，供需要自行核对发布资产的高级用户选择使用；推荐的一键命令不会要求这一步。

许可证与第三方声明见同目录的 `LICENSE` 和 `THIRD_PARTY_NOTICES.md`。
