# 元数据提供方契约

**性质**: 后端内部端口

## 1. 提供方职责

| 提供方 | 允许写入 | 不允许决定 |
|---|---|---|
| JavDB | 影片核心字段、演员关系、标签、评分、榜单 | AVdb 来源是否存在、115 可播放性 |
| DMM | 影片原始简介补充 | 影片身份、演员、标签、可见性 |
| Actor Mapping | 中文名、日文名、权威别名、可用简介 | 影片关系、用户搜索别名 |
| GFriends | 唯一匹配后的头像/写真 URL 索引 | 演员身份合并、永久图片镜像 |
| OpenAI-compatible | 标题/简介/缺失中文演员简介的译文 | 番号、演员姓名、厂商、系列、标签 |

## 2. JavDB 端口

```text
search_movie(normalized_number) -> CoreMovieCandidate | NotFound
fetch_movie(candidate_id) -> CoreMovieMetadata
fetch_rankings(board, year?) -> ordered MovieNumber list
```

`CoreMovieMetadata` 至少包含：JavDB ID、番号、原始标题、发行日、厂商、系列、导演、演员稳定 ID/姓名/别名、标签、评分、封面 URL和剧照 URL。所有字段都先经 boundary schema 校验。

核心成功条件：影片主记录及影片-演员核心关系在一个短事务中提交。图片下载、DMM、GFriends、AI 不属于核心成功条件。

可选 JavDB 用户名和密码作为单个 `javdb.credentials` AES-GCM JSON envelope 通过 TASK-003 设置仓储 CAS 读写，避免分键读取产生混合版本。未配置或配置无效不得阻断公开影片核心抓取；需登录的 TOP250 由排行榜任务明确跳过或报告凭据无效。

## 3. DMM 端口

```text
fetch_description(normalized_number) -> Description | NotFound | Unavailable
```

- `NotFound` 是终态富化结果，不覆盖现有简介。
- `Unavailable` 记录 warning，不回滚核心元数据。
- HTML 只提取文本，禁止把脚本或原始 HTML 返回客户端。

## 3.1 永久目录图片端口

```text
store_movie_images(movie_id, cover_url, plot_urls) -> ImageResult list
```

- 只允许精确主机 `https://c0.jdbstatic.com`，禁止 userinfo、非默认端口、IP 字面量和通配子域；每次重定向都重新校验，最多 3 跳。
- 只接受 `image/jpeg`、`image/png`、`image/webp`，单图响应正文最多 8 MiB。
- Pillow 11.2.1 完整解码后的宽高分别为 1..12,000，总像素最多 40,000,000；声明 MIME 必须与真实格式一致。
- 服务端生成相对路径；同目录临时文件完成校验、flush、fsync 后原子替换。失败清理临时文件且不得覆盖既有 ready 文件。
- 下载或验证失败保存 `retry_pending` 和本地占位事实，形成 images stage warning；不得回滚 `core_ready`。
- 已有 ready 图片需要替换或上游列表缩短时保留最近成功文件；替换记录可在 `retry_pending` 状态继续指向旧文件，只有新文件验证和原子写入成功后才切换。

完整边界由 [TASK-008 永久图片安全边界](../changes/2026-07-26--task-008-image-security-boundaries.md) 冻结。

## 4. Actor Mapping 与 GFriends

- 每周获取一次，失败继续使用最近成功快照。
- XML 解析禁用 DTD、外部实体和网络。
- 权威别名先规范化再建立 `normalized_alias -> actor_ids` 多值索引。
- GFriends 名称只在索引恰好命中一个演员 ID 时关联；0 个或多个结果均丢弃。
- 服务端只保存 GFriends URL 与索引证据，客户端按需缓存图片。

## 5. OpenAI-compatible 翻译

HTTP 边界固定为兼容 `POST {base_url}/v1/chat/completions` 的适配器 `(derived)`。配置包含 `base_url`、`api_key`、`model` 和超时。

输入必须把不可改写字段放入结构化保护区：

```json
{
  "translatable": {
    "title": "...",
    "description": "..."
  },
  "protected": {
    "number": "ABP-123",
    "actors": ["..."],
    "maker": "...",
    "series": "...",
    "tags": ["..."]
  }
}
```

适配器只接受 JSON 结构化结果；若 protected 字段被改变，结果拒绝落库并记录 `translation_guardrail_failed`。`source_hash + model + prompt_version` 命中时直接复用。

## 6. 超时与重试边界

- 单影片元数据任务的全局硬截止是 600 秒，由父进程执行。
- provider 单个 HTTP 请求可以对网络异常、408、429、500、502、503、504做有上限的瞬时重试 `(derived)`，但不得越过全局截止。
- 影片任务最终 `failed` 后不得由 scheduler/worker 自动创建新尝试。
- DMM/GFriends/AI/图片失败在核心成功后形成 warning；管理员可通过 `retry-enrichment` 显式选择失败或缺失的可选阶段创建新尝试。
- 富化重试不得包含 `javdb_core`，不得自动创建，也不得在未选择 `translation` 时再次调用付费 AI。
- 原 `completed_with_warnings` job 和 stage 保持不可变，新尝试保存 `parent_job_id`、`retry_mode=missing_enrichment` 和阶段白名单。
- 当前 attempt 的 `javdb_core` 已成功提交后超时或异常退出形成的 `failed + core_ready` job，可由管理员显式选择尚未成功的可选阶段创建 `missing_enrichment`；旧 attempt 留下的 `core_ready` 不满足该条件，完整 retry 入口仍可由管理员主动选择。
- 可重试资格沿 attempt 父链读取最近的非 `skipped` stage 事实；阶段一旦 succeeded，不能借中间富化 attempt 的 skipped 状态再次调用，尤其不能重复调用已成功的付费翻译。

### 6.1 Worker/child Port

- TASK-007 worker 固定轮询三槽 supervisor；TASK-008 提供 `sakuraplayer.catalog.providers.runtime.build_metadata_stage_executor` 后才开始 claim，provider 未交付时 queued 事实保持不变。
- child 命令行只携带 job ID 和不可复用的 claim owner；数据库 URL与凭据只从 child 运行环境读取，不进入参数或日志。
- 每个 child 在自身进程内创建并关闭 SQLAlchemy Engine/Session 与 httpx Client，禁止继承或接收父进程活动 session/client。
- Linux 容器为后端 worker 运行边界。父 worker 通过管道 watchdog 持有 child 进程组；父进程异常死亡导致管道 EOF，child watchdog 强制终止自身完整进程组。

## 7. 可观察性

每次调用记录 provider、stage、movie ID/番号、HTTP 状态类别、elapsed_ms、attempt 和 error code。URL 只记录主机和路径模板；JavDB 密码、AI key、Cookie、响应 HTML 与完整 prompt 不进普通日志。
