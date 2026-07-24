# AVdb 数据源与解密契约

**版本**: 1.0.0

**性质**: v1 资源接入防腐层的权威输入契约

## 1. Release 来源

| 角色 | GitHub 仓库 | API 基址 |
|---|---|---|
| 主源 | `li-peifeng/AVdb-Only` | `https://api.github.com/repos/li-peifeng/AVdb-Only` |
| 备用源 | `jzdxjk/AVdb-Only` | `https://api.github.com/repos/jzdxjk/AVdb-Only` |

只允许 GitHub API 返回的 HTTPS `browser_download_url`，且最终重定向主机必须在 GitHub Release 资产白名单中。主源失败时按相同 Release tag 和资产类型查询备用源；两个来源都可用时，下载后 SHA-256 必须一致，否则停止导入并记录 `avdb_asset_digest_mismatch`。

## 2. 资产选择

| 模式 | 允许的资产名 | 处理规则 |
|---|---|---|
| 全量 | `All_sehuatang_{count}_{timestamp}.zip` | 与 X1080X 全量资产组成同一对账批次 |
| 全量 | `All_X1080X_{count}_{timestamp}.zip` | 与 sehuatang 全量资产组成同一对账批次 |
| 增量 | `30D_{timestamp}.zip` | 每日导入最近 30 天来源 |

资产名必须完整匹配白名单正则，不能使用子串判断。全量批次只有两个全量资产均验证并导入成功后才标记完成；其中一个失败时已提交批次保留，但当前同步运行标记失败且不执行“缺失对账”。

每日 03:00 运行 30D 增量；每周日 04:00 运行全量对账，时区固定 `Asia/Shanghai`。同一 `(repository, release_id, mode)` 幂等。

## 3. 外层加密包

外层 ZIP 只允许两个根文件：

```text
avdb-resource-library.json
avdb-resource-library.bin
```

清单必须包含：

| 字段 | 约束 |
|---|---|
| `salt` | 标准 Base64，解码后 16 字节 |
| `nonce` | 标准 Base64，解码后 12 字节 |
| `tag` | 标准 Base64，解码后 16 字节 |
| `iterations` | 整数且恰好 200000 |

若清单包含算法、KDF 或密钥长度字段，其值必须分别等价于 `AES-256-GCM`、`PBKDF2-HMAC-SHA256` 和 32 字节。未知算法、重复文件、绝对路径、`..` 路径、符号链接或额外可执行文件必须拒绝。

## 4. 密钥派生与解密

固定公共密钥材料为 32 字节 hex：

```text
ca42e687df5818e2e88da0ff5b9fd2c60f7e22721f682b66c3e50485a00d06d5
```

该值是上游公开格式常量，不是 SakuraPlayer 管理员 secret，也不得与设置、JWT 或播放签名密钥混用。

解密算法固定为：

```text
password = bytes.fromhex(public_password_digest)
key = PBKDF2-HMAC-SHA256(password, salt, iterations=200000, dklen=32)
plain_zip = AES-256-GCM.decrypt(nonce, ciphertext || tag, associated_data=None)
```

GCM 认证失败时不得尝试无认证解密、旧算法或降级路径，返回 `avdb_decryption_failed`。

## 5. 解密后内容

解密结果必须是标准 ZIP，并且只包含一个 UTF-8 或 UTF-8 BOM CSV。CSV 表头必须包含以下 13 个字段，多余字段仅记录 warning 后忽略，缺少必需字段则拒绝资产：

| 字段 | 边界类型 | 规则 |
|---|---|---|
| `tid` | int64 | 来源网站内帖子 ID |
| `number` | string/null | 允许为空，后续规范化 |
| `title` | string | 非空 |
| `publish_date` | date/null | 无效值保留原始错误并按 null 处理 |
| `magnet` | string | 仅进入加密资源载荷，不进入日志/响应 |
| `preview_images` | string/null | 逗号分隔 URL，逐个过白名单 |
| `detail_url` | string/null | 上游帖子 URL |
| `size` | int/null | MB；表示资源包大小，不代表视频文件大小 |
| `section` | string | 顶级版块 |
| `category` | string/null | 子分类 |
| `website` | string | `sehuatang/x1080x` |
| `create_time` | datetime/null | 上游创建时间 |
| `update_time` | datetime/null | 上游更新时间 |

来源唯一键为 `(website, tid)`，不能只使用 `tid`。只有六个目标 section 进入 v1：亚洲有码、亚洲无码、中文字幕、4K原版、素人有码、FC2。

## 6. 资源限制

以下是 v1 实现边界 `(derived)`：

- 外层 ZIP、加密 bin 和单个 HTTP 响应分别最多 512 MiB。
- manifest 最多 64 KiB。
- 解密后内层 ZIP 最多 1 GiB，CSV 解压采用流式读取，不整体展开到内存。
- ZIP 总文件数最多 4，压缩比异常或声明大小越界时拒绝。
- 下载先写临时文件，完成 SHA-256 和 GCM 校验后再原子改名。

## 7. 分类与标签事实

- `section=中文字幕` 产生 `subtitle`。
- `category=无码破解` 或标题明确出现同义标记才产生 `cracked`，不能把整个亚洲无码标为破解。
- `section=4K原版` 产生 `4k`。
- 只有明确 category 或元数据证据产生 `censored`，历史空 category 不得推断。

## 8. 测试样本

测试 fixture 至少包含：正确包、错误 tag、错误迭代、错误长度、额外 ZIP 文件、路径穿越、主备摘要不同、UTF-8 BOM、空番号、重复 `(website,tid)`、跨网站相同 tid、六目标与非目标分类，以及破解/4K/有码组合标签。

原始用户指南可用于人工溯源，但实现和自动测试只能依赖本契约及提交到 `backend/tests/fixtures/` 的最小脱敏样本。
