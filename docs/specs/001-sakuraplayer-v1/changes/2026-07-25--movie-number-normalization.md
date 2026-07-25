# Change Specification: 影片番号规范化输入边界

**Type**: Delta
**Date**: 2026-07-25
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

### Summary

TASK-005 的 Definition of Ready 要求番号规范化规则和特殊 FC2 固定样本已经存在，但当前已提交契约只说明番号允许为空，没有冻结可接受语法。直接实现会导致不同任务以不同规则合并影片。本变更补齐保守、可测试的输入边界，不扩大数据源、分类或影片合并范围。

### Change Summary

| Classification | Count |
|---|---:|
| ADDED | 1 |
| MODIFIED | 1 |
| REMOVED | 0 |

## ADDED

### 标准番号与 FC2 规范化

**Description**: 在建立影片骨架前，以确定性规则把可信的单一番号转换为共享 `MovieNumber`；不能可靠解析的值保留为待识别来源。

**Requirements**:

- REQ-CHG-035: 系统必须先对原始番号执行 Unicode NFKC、首尾空白清理和 ASCII 大写转换，再按完整字符串匹配标准番号或 FC2；不得从标题、多个候选或任意子串猜测番号。
- REQ-CHG-036: 标准番号必须由 2..16 位、以 ASCII 字母开头的 ASCII 字母数字前缀和 2..10 位数字序号组成，输入可用空白、`-`、`_`、`.` 或 `/` 分隔；只有纯字母前缀可省略分隔符，含数字前缀必须显式分隔以避免拆分歧义。输出固定为 `PREFIX-NUMBER` 并保留数字前导零。
- REQ-CHG-037: FC2 输入必须为 `FC2`、可选 `PPV` 和 5..10 位数字 ID 的完整匹配；输出固定为 `FC2-PPV-ID`。空值、超长值、单数字、尾缀、多番号和其他非完整匹配必须返回不可识别，不得建立影片骨架。

**Acceptance Criteria**:

- [ ] `abp 001`、`ABP_001`、`abp001` 和全角 `ＡＢＰ－００１` 均规范化为 `ABP-001`。
- [ ] `t28/123` 规范化为 `T28-123`，前缀中的数字和序号前导零保持稳定。
- [ ] `fc2 ppv 1234567`、`FC2-PPV-1234567` 和 `fc2_1234567` 均规范化为 `FC2-PPV-1234567`。
- [ ] 空值、`12345`、`ABP-1`、`T28123`、`ABP-123-CD`、`ABP-123 FC2-1234567` 和超过 128 字符的值进入待识别。

**Impact**: AVdb 输入契约、TASK-005 番号单测、来源导入和精确搜索共享值对象。

## MODIFIED

### TASK-005 Definition of Ready

**Previous Behavior**: 任务要求已有固定样本，但版本库没有样本语法的权威来源。

**New Behavior**: `contracts/avdb-source.md` 保存权威规范化表和拒绝边界，TASK-005 测试只依赖该提交内容。

**Requirements**:

- REQ-CHG-038: TASK-005 必须以版本化契约中的固定样本驱动实现，不能依赖根目录未跟踪指南或从真实上游数据反推规则。

**Acceptance Criteria**:

- [ ] 规范化单元测试覆盖契约中的成功与拒绝样本。
- [ ] 导入测试证明不可识别来源不创建 `movie` 且不进入自动元数据候选。

**Impact**: TASK-005；Breaking: NO，相关生产代码尚未实现。

## REMOVED

无。

## Affected Components

| Component | Change Type | Risk |
|---|---|---|
| AVdb 防腐层契约 | ADDED | MEDIUM |
| TASK-005 DoR 与测试 | MODIFIED | LOW |
| 后续搜索和元数据输入 | ADDED | MEDIUM |

## Task Synchronization

本变更不创建独立 `TASK-CHG`。规则直接由尚在实施中的 TASK-005 交付；TASK-007 及后续任务只消费其规范化结果。

## Testing Strategy

- 参数化单元测试覆盖标准、FC2、全角、空白、分隔符和拒绝样本。
- PostgreSQL 集成测试覆盖相同规范化番号的并发去重和原始别名保留。
- 待识别测试证明保守拒绝不会进入影片骨架或自动候选。

## Rollback Plan

生产导入前可与 TASK-005 实现整体回退。上线后若要放宽规则，必须新建 Delta 并只重新处理待识别来源，不得静默重写既有影片主键或自动合并影片。
