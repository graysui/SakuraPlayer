# SakuraPlayer v1 运维健康与 Schema 门禁契约

**版本**: 1.0.0

**适用范围**: Docker API、worker、scheduler、PostgreSQL 与 Alembic 启动流程

## 1. API 探针

| 路径 | 语义 | 成功 | 失败 |
|---|---|---|---|
| `GET /health/live` | API 进程可以响应 | `200 {"status":"alive"}` | 进程不可响应 |
| `GET /health/ready` | 配置有效、PostgreSQL 可达且 Schema 为代码 head | `200 {"status":"ready"}` | `503 {"status":"not_ready"}` |

两个路径匿名可用、`Cache-Control: no-store`、不进入 `/api/v1` OpenAPI。响应不得包含数据库地址、revision、secret、异常正文或内部文件路径。

## 2. Worker 与 Scheduler

worker 和 scheduler 不开放 HTTP 端口。Docker 健康检查在各自容器内执行共享 ready CLI；该命令重新加载配置并检查 PostgreSQL 与 Schema head，成功返回 0，失败返回非 0。主进程退出时容器本身退出。

## 3. PostgreSQL

PostgreSQL 使用 `pg_isready` 检查容器内服务，不向宿主发布 5432 端口。

## 4. Schema 门禁

- 业务进程只检查 Schema，不自动迁移、`stamp`、创建或删除表。
- 可运行数据库的 `alembic_version` head 集合必须与代码迁移图 head 集合完全一致。
- 空库无版本、已知旧 revision 返回 `schema_migration_required`。
- 非空无版本、未知/领先/分叉 revision 或异常版本表返回 `schema_revision_unknown`。
- PostgreSQL 不可达返回 `database_unavailable`。
- 错误日志只记录稳定错误码和安全组件名，不记录 DSN 或实际 revision。

## 5. 迁移入口

部署通过一次性 `migrate` 服务这一单一显式迁移入口执行 `alembic upgrade head`。API、worker 和 scheduler 只执行 Schema head 检查。首次空库允许升级，重复升级必须幂等；发现非空无版本数据库时必须在 Alembic 执行前拒绝，旧 SakuraMedia Schema 不作为迁移输入。

初始 revision `0001_initial_skeleton` 不创建业务表。后续任务各自拥有其业务迁移。
