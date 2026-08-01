# 任务列表：运行修复

**规格**: [2026-07-24--sakuraplayer-v1.md](2026-07-24--sakuraplayer-v1.md)

**生成日期**: 2026-08-01

**语言**: General

**实施与验证流程**: [统一实施与验证工作流](implementation-workflow.md)

## 任务索引

| ID | 标题 | 主要焦点 | 依赖 | 跨边界 | 外部风险 |
|---|---|---|---|---|---|
| [TASK-220](tasks/TASK-220.md) | Windows 启动初始化恢复 | 安全存储超时、中文恢复、地址编辑 | TASK-202,TASK-219 | 否 | 否 |
| [TASK-221](tasks/TASK-221.md) | Windows 播放返回与详情布局恢复 | typed 返回目标、来源优先详情 | TASK-207,TASK-209,TASK-210,TASK-211,TASK-220 | 否 | 否 |

## 数量检查

- 实现任务：2，未超过 15。
- E2E：0。
- 清理：0；Windows 文件统一由 TASK-214 清理。

## 文件冲突结论

TASK-220 只修改 Windows 认证初始化和登录前服务端地址页面；TASK-221 只修改 Windows typed player route 和影片详情布局。两者由 TASK-214 在全部运行修复完成后统一执行卫生清理；不改变后端 API、数据库、认证协议或发布配置。
