# Change Specification: 实施准备与契约补强

**Type**: Delta
**Date**: 2026-07-24
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

实施前审计发现首次管理员创建、传输边界、客户端后端地址、运行密钥、待识别查询、收藏集合、设置返回、排行榜无快照、富化重试和稳定错误码存在未冻结或不完整契约。本变更只补齐实现所需行为，不扩大 v1 的媒体来源、平台或用户范围。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 4 |
| MODIFIED | 6 |
| REMOVED | 0 |

---

## ADDED

### 一次性管理员初始化口令

**Description**: 未创建管理员时，匿名 bootstrap 请求还必须提交由 Docker Secret 或环境变量提供的一次性初始化口令；管理员创建后该口令不再具有任何产品权限。

**Requirements**:
- REQ-CHG-001: 当系统尚无管理员时，系统必须在创建管理员前常量时间校验初始化口令。

**Acceptance Criteria**:
- [ ] AC-133：缺失或错误口令不能创建管理员，并且日志不得输出口令。

**Impact**: 运行配置、认证 OpenAPI、错误码、TASK-001、TASK-002。

### 私有部署传输边界

**Description**: 远程客户端只能通过 HTTPS 或可信加密 VPN 访问；明文 HTTP 只允许 loopback 或明确接受风险的隔离私网部署，不提供公网暴露流程。

**Requirements**:
- REQ-CHG-002: 当 API 可被远程客户端访问时，部署文档和配置必须明确安全传输路径。

**Acceptance Criteria**:
- [ ] AC-134：默认 Compose 只发布到 loopback；远程发布需要显式地址，并由 HTTPS 反向代理或可信 VPN 保护。

**Impact**: Compose、部署文档、运行配置、TASK-001。

### 客户端后端地址

**Description**: Windows 与 HarmonyOS 首次登录前配置一个后端基址，安全校验并持久化为非敏感本机设置。

**Requirements**:
- REQ-CHG-003: 当客户端没有有效后端地址时，客户端必须先完成地址配置和连接测试再显示登录提交。

**Acceptance Criteria**:
- [ ] AC-135：地址不得包含用户信息、查询或 fragment；远程明文 HTTP 需要风险确认且只能指向私有地址。

**Impact**: 两端登录流程、客户端本地配置、TASK-202、TASK-302。

### 实施入口与运行契约

**Description**: 新增根目录协作规则、会话交接、运行配置和 AVdb 数据源契约，使新会话和新工作树不依赖聊天历史或未跟踪资料。

**Requirements**:
- REQ-CHG-004: 实施者必须能从版本库确定读取顺序、下一任务、环境变量、密钥职责和 AVdb 解密格式。

**Acceptance Criteria**:
- [ ] `AGENTS.md`、`SESSION-HANDOFF.md`、`runtime-configuration.md` 和 `avdb-source.md` 均已提交且互相链接。

**Impact**: 项目治理与 TASK-001/TASK-004 Definition of Ready。

---

## MODIFIED

### 管理查询和收藏集合

**Previous Behavior**: OpenAPI 只能提交待识别关联、收藏或取消收藏。

**New Behavior**: 增加待识别资源分页查询；影片和演员列表支持 `favorite=true`，形成可浏览的单一收藏集合。

**Requirements**:
- REQ-CHG-005: 现有 AC-028、AC-029、AC-077 必须具备完整读写契约。

**Acceptance Criteria**:
- [ ] 待识别响应不含磁力，支持状态、搜索和游标分页。
- [ ] 影片与演员收藏可分别分页查询。

**Impact**: OpenAPI、TASK-005、TASK-011；Breaking: NO。

### 设置与同步状态

**Previous Behavior**: `Settings` 只返回 provider 状态，无法回显非敏感 JavDB/AI 配置或 AVdb 同步状态。

**New Behavior**: 返回结构化的 JavDB、AI、provider 和全量/增量同步状态，秘密仍只返回 `configured`。

**Requirements**:
- REQ-CHG-006: 现有 AC-119 必须允许客户端完整展示并管理当前配置。

**Acceptance Criteria**:
- [ ] API 不回显密码或 key，但可回显用户名、模型、Base URL、超时和同步时间/错误码。

**Impact**: OpenAPI、TASK-013、TASK-208、TASK-308；Breaking: NO，尚未实现。

### 排行榜无快照状态

**Previous Behavior**: TOP250 未配置 JavDB 凭据或首次同步未完成时没有稳定响应语义。

**New Behavior**: 返回 `ranking_snapshot_unavailable`，details 只含安全原因和可重试提示；其他榜单与旧快照不受影响。

**Requirements**:
- REQ-CHG-007: AC-046 和 AC-073 的不可用状态必须可由客户端区分。

**Acceptance Criteria**:
- [ ] 已有快照继续返回；从未有快照时返回稳定错误码而不是空的伪成功快照。

**Impact**: OpenAPI、错误码、TASK-012/205/305；Breaking: NO。

### 可选富化重试

**Previous Behavior**: 文档允许重试富化，但 API 只允许重试整体 `failed` 任务。

**New Behavior**: `completed_with_warnings` 可显式创建只运行失败/缺失可选阶段的新尝试；不得重跑 JavDB 核心或自动重跑付费 AI。

**Requirements**:
- REQ-CHG-008: 手动富化重试必须指定阶段并保留原任务事实。

**Acceptance Criteria**:
- [ ] 无可重试阶段时返回 `metadata_job_no_retryable_enrichment`。
- [ ] 新尝试有独立 ID、父任务、阶段白名单和审计记录。

**Impact**: 数据模型、OpenAPI、错误码、TASK-007/013；Breaking: NO。

### 稳定错误码完整性

**Previous Behavior**: `cloud115_submit_uncertain` 与 `translation_guardrail_failed` 被其他契约引用但未登记。

**New Behavior**: 所有跨契约分支码进入统一错误码目录，并补充 bootstrap、排行榜和富化重试错误。

**Requirements**:
- REQ-CHG-009: 客户端或任务状态使用的错误码必须在目录中有唯一语义。

**Acceptance Criteria**:
- [ ] 契约扫描不存在未登记的稳定错误码。

**Impact**: error-codes.md、OpenAPI、测试 fixture；Breaking: NO。

### 启动级密钥职责

**Previous Behavior**: 文档提到主密钥、JWT 和播放 HMAC，但没有名称、格式或职责分离。

**New Behavior**: 设置加密、令牌签名、播放签名和初始化口令使用独立随机 secret，Docker Secret 文件优先于环境变量。

**Requirements**:
- REQ-CHG-010: 不同密码学用途不得复用同一密钥材料。

**Acceptance Criteria**:
- [ ] 生产模式缺少任一必需 secret 时拒绝启动，测试可注入固定替身。

**Impact**: 运行配置、架构、TASK-001/002/003/108；Breaking: NO，尚未实现。

---

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| 身份与运行配置 | ADDED/MODIFIED | HIGH |
| OpenAPI 与错误码 | MODIFIED | MEDIUM |
| 元数据任务模型 | MODIFIED | MEDIUM |
| Windows/HarmonyOS 登录 | ADDED | MEDIUM |
| 项目治理和交接 | ADDED | LOW |

## Task Synchronization

本次不创建独立 `TASK-CHG`，因为产品代码尚未实施，变化直接进入尚为 `pending` 的既有任务：

| Change | Existing tasks |
|---|---|
| 运行配置、loopback 和传输边界 | TASK-001 |
| bootstrap token 与用途分离 JWT | TASK-001、TASK-002、TASK-202、TASK-302 |
| AVdb 自包含输入契约 | TASK-004 |
| 待识别读取 | TASK-005 |
| 富化阶段重试 | TASK-007、TASK-008、TASK-013、TASK-208、TASK-308 |
| 收藏集合 | TASK-011、TASK-204、TASK-206、TASK-207、TASK-304、TASK-306、TASK-307 |
| 排行榜无快照 | TASK-012、TASK-205、TASK-305 |
| 设置、同步和诊断 DTO | TASK-013、TASK-208、TASK-308 |
| 客户端后端地址 | TASK-202、TASK-302 |
| Windows/HarmonyOS E2E | TASK-014、TASK-213、TASK-313 |

## Testing Strategy

- OpenAPI 解析、引用和安全覆盖检查。
- bootstrap 错误/缺失/正确/重复/并发测试，日志秘密扫描。
- 待识别、收藏、设置、排行榜和富化重试契约测试。
- 任务依赖、AC 覆盖、Markdown 链接和 Git whitespace 检查。

## Rollback Plan

产品代码尚未实现，可通过回退本变更提交恢复原文档；不得只回退 OpenAPI 而保留新增 AC 或任务映射。
