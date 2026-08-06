# Change Specification: AI base_url 允许 `/v1` 尾段

## 背景

TASK-010 冻结的 REQ-CHG-075 要求 `base_url` 是不含 `/v1` 尾段的 provider root，适配器总是请求 `{base_url}/v1/chat/completions`。真实 OpenAI 兼容提供商（如 opencode.ai 网关）官方文档给出的 base URL 本身自带 `/v1` 尾段（例如 `https://opencode.ai/zen/go/v1`）。Windows 管理员按提供商文档填写后，后端保存校验直接拒绝，前端只笼统显示"输入内容不符合要求"，无法定位原因；即使绕过校验，适配器也会请求 `{base_url}/v1/chat/completions` 产生 `/v1/v1/` 双前缀导致 404。

## 变更

- REQ-CHG-323：`base_url` 允许以 `/v1` 尾段结尾（`parsed.path.rstrip("/").endswith("/v1")` 不再是拒绝条件）。其余校验保持不变：绝对 `http/https` URI、非空 netloc、无 userinfo/password、无 query、无 fragment、长度不超过 2048，规范化时只移除尾部 `/`。
- REQ-CHG-324：OpenAI 兼容端点拼接规则改为按 base_url 形态自适应：
  - base_url path 以 `/v1` 结尾时：chat completions 端点为 `{base_url}/chat/completions`，models 端点为 `{base_url}/models`；
  - 否则保持原语义：`{base_url}/v1/chat/completions`、`{base_url}/v1/models`。
  - 两种填法等价且均可用，保存后不做归一化改写，保持用户输入（去尾部斜杠后）原样持久化。
- 契约更新：`contracts/runtime-configuration.md` 中 AI `base_url` 段落从"不含 `/v1` 尾段"改为"可带 `/v1` 尾段，带与不带等价"；追踪矩阵中 REQ-CHG-075 语义由本变更规格修订。

## 范围与安全

- 不改动 prompt、协议版本、占位符、输出校验、付费幂等、配置加密与版本 CAS 语义。
- 不访问真实付费 AI；默认测试仍使用本地 MockTransport 替身。
- API key 与完整配置载荷仍然不得进入日志、异常或测试快照。

## 回滚

发布前可整体回退本变更规格，恢复"不含 `/v1` 尾段"语义；已保存的带 `/v1` 尾段配置在新后端下仍按新规则解析，回滚后需用户改填不带 `/v1` 的根地址。

## 验证边界

- `config` 单元测试：带 `/v1` 尾段的 base_url 可以保存并原样回读（仍去尾部斜杠）。
- `adapter` 单元测试：带 `/v1` 尾段的 base_url 请求 `/chat/completions` 与 `/models`；不带 `/v1` 的 base_url 仍请求 `/v1/chat/completions`（回归断言保持）。
