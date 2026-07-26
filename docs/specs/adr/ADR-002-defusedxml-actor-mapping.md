# ADR-002: 使用 defusedxml 解析 Actor Mapping

**日期**: 2026-07-26
**状态**: Accepted

## 背景

TASK-009 每周解析约 8.6 MiB 的外部 Actor Mapping XML，并必须拒绝 DTD、实体扩展和外部网络。标准库接口容易因 parser 配置遗漏而重新暴露 XXE 或实体扩展风险。

## 决策

后端固定使用 `defusedxml` 0.7.1 解析 Actor Mapping。HTTP 下载、响应上限、URL 白名单、重定向、摘要和原子文件生命周期仍由 SakuraPlayer 适配器负责。

## 后果

- Docker 后端与测试镜像增加一个固定版本依赖。
- 恶意 DTD、内部/外部实体和实体扩展 fixture 必须稳定失败。
- 解析器不负责上游 URL 信任、文件落盘或数据库状态转换。

## 替代方案

- 标准库 `ElementTree` 加调用点约定：安全依赖隐含在每个调用点，容易回归，拒绝。
- 正则或字符串解析 XML：无法可靠处理编码和属性，拒绝。
- 允许 DTD 但禁用网络：仍保留实体扩展风险，拒绝。
