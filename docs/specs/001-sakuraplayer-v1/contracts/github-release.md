# GitHub 自动发布契约

**Version**: 1.3.0
**Status**: Accepted
**Owner**: TASK-316、TASK-318、TASK-319

## 验证工作流

- `.github/workflows/verify.yml` 在 pull request 和 `main` push 上运行。
- 只使用公开源码、固定工具链和离线 fixture，不读取业务 secret，不访问真实 115、JavDB 写操作或付费 AI。
- 后端验证包含锁定 Python 测试镜像中的 Ruff、自包含 pytest、host Docker 配置断言和 `runtime` target 构建。
- Windows 验证包含 Flutter 3.29.2 的 analyze、test 和 x64 release build。
- Linux runner 固定 `ubuntu-24.04`，Windows runner 固定 `windows-2022`；Python 3.10.16 slim 基础镜像固定 manifest digest。

## 发布触发与版本

- `.github/workflows/release.yml` 只接受 `refs/tags/vX.Y.Z`。
- tag 工作流在发布前调用同一份验证工作流，不能只依赖历史 `main` 结果。
- `X.Y.Z` 必须与 `windows/pubspec.yaml` 的 `version: X.Y.Z+B` 主版本完全一致。
- Windows 资产版本使用 `X.Y.Z-B`；容器版本不包含 Flutter build number。
- 失败、取消或不匹配的 tag 不创建 GitHub Release，也不移动或覆盖既有版本制品。

## Windows 资产

- ZIP：`SakuraPlayer-Windows-X.Y.Z-B.zip`
- 外层校验：`SakuraPlayer-Windows-X.Y.Z-B.zip.sha256`
- ZIP 由 `windows/tool/build_private_release.ps1` 生成；脚本负责 release build、包内容、GPL/NOTICE、包内清单与外层 SHA-256。
- 公共 CI 没有个人代码签名证书，Windows 资产明确为 unsigned；GitHub artifact attestation 不能替代 Authenticode。

### Windows 单文件安装器

- 安装器：`SakuraPlayer-Windows-X.Y.Z-B-Setup.exe`
- 外层校验：`SakuraPlayer-Windows-X.Y.Z-B-Setup.exe.sha256`
- 安装器由 `windows/tool/build_windows_installer.ps1` 从已通过 `verify_release_contents.ps1` 的同一份 ZIP bundle 生成，使用固定 Inno Setup 6.4.2；不得单独构造或省略 Flutter/native DLL、AOT/ICU 数据、许可证和第三方声明。
- 安装器默认写入 `%LOCALAPPDATA%\Programs\SakuraPlayer`，`PrivilegesRequired=lowest`，不要求管理员权限；用户数据不由安装器删除或迁移。
- “单文件安装器”表示单个下载文件，不表示 Flutter 应用成为真正单一可执行文件；运行时依赖在安装器内部展开到安装目录。
- 安装器及其校验文件与 ZIP 资产一起生成 GitHub artifact attestation。公共 CI 没有个人代码签名证书，安装器明确为 unsigned；attestation 不能替代 Authenticode。

## Linux Docker 部署资产

- 压缩包：`SakuraPlayer-Docker-X.Y.Z.tar.gz`
- 外层校验：`SakuraPlayer-Docker-X.Y.Z.tar.gz.sha256`
- 包内固定包含 `docker-compose.yml`、`.env.example`、`.release-version`、`install.sh`、`install-latest.sh`、`README.md`、`LICENSE` 和 `THIRD_PARTY_NOTICES.md`，不得包含 `.env`、`secrets/`、Git 元数据、构建缓存或业务数据。
- `.release-version` 只包含与 tag 相同的规范 `X.Y.Z`；安装脚本据此选择 Docker Hub 完整版本镜像，不使用 `latest`。
- 归档必须使用稳定相对路径且解压后可直接运行 `./install.sh`；工作流在上传前检查文件白名单、脚本 Bash 语法、版本一致性和 SHA-256。
- 压缩包与校验文件均生成 GitHub artifact attestation；该证明覆盖发布字节和来源工作流，不替代操作者对下载校验文件的核对。
- `install-latest.sh` 是新手推荐的远程引导器：通过 `releases/latest` 重定向解析规范 `vX.Y.Z`，按固定资产名称下载归档，在临时目录解压后把固定发布文件复制到执行命令时的当前目录，再调用该持久目录内的 `install.sh`。新归档必须包含自身副本；为兼容已发布的旧归档，缺少 `install-latest.sh` 时仍可安装，只要 Compose、环境模板、版本文件、`install.sh`、部署说明和许可证文件齐全。它不要求用户手动下载、解压或执行 SHA-256；首次交互运行可选择合法 IPv4 发布地址和 API 端口，无 TTY 时使用 `127.0.0.1:8000`，已有 `.env` 保持原值。非法版本、下载失败和归档布局异常必须在 Compose 启动前失败并清理临时目录；`.env` 和 `secrets/` 不得依赖临时目录。

## 后端镜像

- Registries：GitHub Container Registry 与 Docker Hub。
- Repositories：`ghcr.io/graysui/sakuraplayer-backend`、`docker.io/graysui/sakuraplayer-backend`。
- Platform：`linux/amd64`
- Docker target：`runtime`
- Tag：`X.Y.Z`、`X.Y`、`X`、`latest`、`sha-<short-sha>`。
- 两个 registry 必须由同一次 Buildx 构建同时推送，相同版本标签必须指向同一镜像 digest。
- API、migrate、worker、scheduler 必须使用同一镜像 digest，以既有 Compose command 区分进程。

## 权限与供应链

- workflow 顶层默认 `contents: read`。
- 验证 job 不授予写权限。
- Windows 与 Linux 部署资产证明只申请 `id-token: write` 与 `attestations: write`；镜像发布只申请 `packages: write`、`id-token: write` 与 `attestations: write`；Release 汇总只申请 `contents: write`。
- 所有第三方 `uses:` 固定到 40 字符 commit SHA，并以注释记录人类可读版本。
- 所有源码 checkout 禁止持久化临时仓库凭据。
- GitHub Release 与 GHCR 只使用 GitHub 自动提供的仓库 token；Docker Hub 只使用仓库级 Actions Secret `DOCKERHUB_TOKEN` 和固定用户名 `graysui`。不得使用个人 GitHub PAT 或任何业务 secret。
- Windows ZIP/校验文件、Windows 安装器/校验文件、Linux Docker 压缩包/校验文件、GHCR digest 与 Docker Hub digest 均生成 GitHub artifact attestation。

## 发布顺序

```text
严格 tag 与版本校验
  -> Windows 构建 ZIP 与安装器、校验、attestation、artifact
  -> Linux Docker 部署包白名单、校验、attestation、artifact
  -> 单次 Docker build，同时推送 GHCR/Docker Hub、分别登记 digest attestation
  -> 汇总下载 Windows 与 Linux artifact
  -> 创建 GitHub Release 并上传 Windows 两组资产、Linux 资产及 SHA-256
```

Release 创建必须依赖 Windows、Linux 部署包与 Docker 三条发布路径成功，避免只发布一部分版本。
