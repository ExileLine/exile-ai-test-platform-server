# exile-ai-test-platform-server

放逐测试平台重构，AI增强。

## 项目背景

本项目定位为一个面向接口自动化测试的执行与管理平台。  
核心目标是将零散的 API 调试、数据准备、场景串联和结果追踪统一到一个系统中，支持从“单接口验证”逐步升级到“业务流程级回归验证”。

## 核心功能定位

1. 测试用例管理（`ApiRequest`）  
每个接口请求被抽象为一个可复用测试用例，支持状态管理、可见性和执行权限控制。

2. 数据驱动测试（`ApiRequestDataset`）  
一个用例可绑定多组参数数据，实现同一请求模板的多轮验证。

3. 测试场景编排（`TestScenario` + `TestScenarioCase`）  
支持将多个测试用例按顺序编排成业务流程场景，例如“登录 -> 创建订单 -> 支付”。

4. 执行记录与回溯（`ApiRequestRun`）  
完整记录请求快照、数据集快照、响应结果、耗时与错误信息，便于问题排查与结果审计。

## 未来开发方向

1. 执行引擎增强  
支持变量提取、前后置处理、失败重试、并发与限流策略。

2. 断言与校验体系  
支持状态码断言、JSONPath 断言、文本匹配和自定义断言表达式。

3. 报告与分析  
提供场景执行报告、趋势统计、失败聚类与历史对比。

4. 团队协作与权限治理  
支持共享用例库、角色权限、审计日志与可见性隔离。

5. 流水线集成  
支持对接 CI/CD（如 GitHub Actions、Jenkins），实现自动回归触发与结果回传。

## 环境与依赖管理（uv）

1. 安装依赖

```bash
uv sync
```

2. 启动服务

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 7777 --reload
```

3. 启动 Celery Worker（用于消费测试场景执行任务）

```bash
uv run celery -A app.tasks.celery_app:celery_app worker -Q exile_scenario_tasks --loglevel INFO
```

4. 运行测试

```bash
uv run pytest
```

## 生产部署建议（Gunicorn + Celery）

1. 启动 API 进程（示例）

```bash
gunicorn -w 8 -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:5001 \
  --access-logfile /srv/access.log --error-logfile /srv/error.log \
  --log-level debug --timeout 300 --capture-output -D
```

2. 启动 Celery Worker（示例）

```bash
uv run celery -A app.tasks.celery_app:celery_app worker \
  -Q exile_scenario_tasks \
  --loglevel=info \
  --concurrency=8 \
  --pool=threads \
  --logfile=/srv/logs/ors_server/celery/worker.log \
  --pidfile=/srv/logs/ors_server/celery/worker.pid \
  --detach
```

## Celery 队列说明

- `task_default_queue` 在 `app/tasks/celery_app.py` 中配置，当前默认值是 `exile_scenario_tasks`。
- `run_scenario_task.delay(...)` 未显式指定 `queue`，会进入 `task_default_queue`。
- Worker 使用 `-Q exile_scenario_tasks` 时，只会消费该队列。
- 若后续引入多种任务，建议使用 `task_routes` 按任务类型分队列，并为不同队列部署不同 worker。

## ORM 说明

项目已从 `tortoise` 迁移为 `SQLAlchemy 2.0 Async`。

默认数据库后端为 `mysql`，可通过环境变量切换：

```env
DB_BACKEND=mysql
```

## 数据迁移（Alembic）

1. 生成迁移文件（基于模型自动对比）

```bash
uv run alembic revision --autogenerate -m "init schema"
```

2. 执行迁移到最新版本

```bash
uv run alembic upgrade head
```

3. 回滚一个版本

```bash
uv run alembic downgrade -1
```

4. 查看当前版本和历史

```bash
uv run alembic current
uv run alembic history --verbose
```
