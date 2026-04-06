# 桌面派活：子智能体（`/subagents`）

Orbit 网关在 **`agent` RPC** 路径上识别以 **`/subagents`** 开头的用户消息，在**当前主会话**（`agentId` + `sessionId` + `sessionKey`，与桌面「派活框」一致）上下文中执行子命令，**不经过**主会话的 LLM 工具环。

实现代码：

- `orbit/gateway/subagents_cmd.py` — RPC 挂接、后台 `runner.run`、WS 合成回复
- `orbit/gateway/subagents_logic.py` — 记录过滤、`#` / runId 解析、transcript 尾部读取、帮助文案
- `orbit/gateway/subagents_parse.py` — `shlex` 分词（支持引号）
- `orbit/gateway/server.py` — `schedule_subagents_if_needed` 在 `asyncio.create_task(_run)` 之前短路

自动化测试（位于 `tests/`，见下文「测试」）：

- `tests/test_subagents_parse.py`、`tests/test_subagents_logic.py`、`tests/test_subagents_cmd_integration.py`

## 行为摘要

| 项目 | 说明 |
|------|------|
| 触发 | 用户消息（strip 后首词为 `/subagents`），且未被 `/reset` 清空 |
| 作用域 | 子运行列表按 `parent_agent_id` + `parent_session_id` 过滤 |
| 并行 | 子任务使用 `session_key = {原 sessionKey}:subagent:{uuid}` 与新 `session_id`，与主会话不同队列 lane，可并行 |
| 存储 | `GatewayState.desktop_subagents` 内存列表；**网关重启后丢失** |
| 主聊天 | 子任务完成后**不会**自动把结果插回主会话；用 `list` / `log` 查看 |

## 子命令

- **`/subagents`** / **`help`** — 帮助（Markdown 片段）
- **`list`** — 本会话下子运行（序号用于 `#N`）
- **`spawn <agentId> <任务…>`** — 后台 `AgentRunParams` 调用 `runner.run`；继承派活框的 `reasoningLevel`
- **`info <#N|runId前缀>`** — 元数据 + transcript 路径
- **`log <#N|runId前缀> [行数]`** — transcript 文件尾部（默认 40 行，上限 500）
- **`kill <#N|runId前缀|all>`** — 对 `asyncio.Task.cancel()`，**尽力而为**（进行中 LLM/工具未必立刻停）

未实现（可与 OpenClaw 对齐的后续项）：`send` / `steer`、向主会话 announce、持久化注册表、嵌套深度与 `maxConcurrent` 全局上限。

## 与 OpenClaw 的差异

OpenClaw 使用 `sessions_spawn`、插件钩子、`agent:<id>:subagent:<uuid>` 会话键与 announce 回主渠道。Orbit 本实现为 **网关内轻量版**：同一套 **斜杠习惯**，语义接近，但**无** OpenClaw 配置项与跨渠道投递。

参考：<https://docs.openclaw.ai/tools/subagents>

## 测试

测试放在仓库根目录的 **`tests/`** 下（与业务代码分离）；`tests/conftest.py` 的 `pytest_sessionstart` 会确保从本仓库导入 `orbit`。

不依赖 FastAPI（可单独跑）：

```bash
cd /path/to/mw4agent
python -m pytest tests/test_subagents_parse.py tests/test_subagents_logic.py -q
```

依赖 FastAPI（与网关相同环境）：

```bash
python -m pytest tests/test_subagents_cmd_integration.py -q
```

若未安装 FastAPI，集成文件会在收集阶段 **skip**（`pytest.importorskip("fastapi")`）。

## 相关文档

- [实现状态（总览）](./implementation-status.md)
