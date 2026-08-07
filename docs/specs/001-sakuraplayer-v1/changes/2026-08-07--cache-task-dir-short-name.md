# Change Specification: TASK-330 缓存任务目录名缩短为 10 字符内无连字符

**Type**: Delta
**Date**: 2026-08-07
**Status**: Accepted
**Parent Spec**: [SakuraPlayer v1 功能需求规格](../2026-07-24--sakuraplayer-v1.md)

## Summary

真实运行发现：115 端任务目录名为 `cache-<32 位 hex>`（37 字符），且 115 离线任务会在该目录下
再创建种子相对路径子目录（如 `SakuraPlayer-Cache/cache-e878aff0705e4226a71832646ff13215/KTB-120/...`），
深层长路径影响 115 端操作效率。本次变更把新建缓存任务目录名缩短为 10 字符内、不含连字符
（`uuid.uuid4().hex[:10]`，10 位十六进制、40 bit 熵），仅影响新建任务；既有任务的
`task_dir_name` 不迁移，worker/cleanup 继续按存储值精确匹配。

## ADDED

- REQ-CHG-336: 新建缓存任务目录名由 `cache-<32 位 hex>` 改为 `uuid.uuid4().hex[:10]`
  （≤10 字符、无连字符、随机且不可由标题控制），降低 115 端路径长度；`task_dir_name`
  长度 1-128 与"随机不可由标题控制"约束不变（`data-model.md` 第 10.2 节），既有任务不迁移。

## MODIFIED

- `data-model.md` 10.2 节 `task_dir_name` 行：补充"新建任务为 10 字符十六进制短名"说明。

## Acceptance Criteria

- [ ] 新建缓存任务目录名为 10 字符内、不含 `-`、随机且不可由标题控制。
- [ ] 既有任务 `task_dir_name` 保持不变，worker/cleanup/ownership 按存储值精确匹配不受影响。
- [ ] 短名碰撞概率可接受（40 bit 熵），find_or_create_directory 幂等语义不变。

## Task Synchronization

本变更创建独立实现任务 `TASK-330`，依赖 TASK-104；不新增产品 AC。不做数据迁移，不重命名
既有远端目录。

## Testing Strategy

- play_request 创建测试：断言新建任务 `task_dir_name` 为 10 字符十六进制且无连字符。
- Fast 运行相关 Ruff、cache 测试及差异/秘密检查；默认测试不访问真实 115。

## Rollback Plan

TASK-330 提交可整体回退；回退不影响既有任务目录（未迁移）。旧格式目录随既有任务生命周期
自然收敛。
