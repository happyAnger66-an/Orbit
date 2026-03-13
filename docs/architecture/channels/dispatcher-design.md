# Channels Dispatcher 设计说明

## 问题：Console Channel 直接调用 AgentRunner

在 MW4Agent 的初始实现中，`ChannelDispatcher` 直接调用 `AgentRunner.run()`，这与 OpenClaw 的设计不一致。

### OpenClaw 的设计

OpenClaw 中，channels 通过 Gateway RPC 调用 agent：

1. **统一入口**：所有 agent 调用都经过 Gateway
2. **事件流**：Gateway 负责广播 agent 生命周期、assistant、tool 事件
3. **幂等性**：Gateway 提供 dedupe 机制
4. **监控**：Gateway 维护运行状态和快照

### MW4Agent 的改进

MW4Agent 的 `ChannelDispatcher` 现在支持两种模式：

#### 模式 1：通过 Gateway RPC（对齐 OpenClaw）

```python
from mw4agent.channels.dispatcher import ChannelDispatcher, ChannelRuntime
from mw4agent.agents.session.manager import SessionManager
from mw4agent.agents.runner.runner import AgentRunner

# 配置 gateway_base_url
runtime = ChannelRuntime(
    session_manager=SessionManager(...),
    agent_runner=AgentRunner(...),
    gateway_base_url="http://127.0.0.1:18790"  # 通过 Gateway 调用
)

dispatcher = ChannelDispatcher(runtime=runtime)
await dispatcher.dispatch_inbound(ctx)
```

**工作流程**：
1. `dispatch_inbound` 调用 `_call_agent_via_gateway()`
2. 发送 `agent` RPC 到 Gateway
3. 等待 `agent.wait` RPC 返回
4. 从 payload 中提取 `replyText`
5. 调用 `plugin.deliver()` 发送回复

#### 模式 2：直接调用 AgentRunner（简化模式）

```python
# 不配置 gateway_base_url（或设为 None）
runtime = ChannelRuntime(
    session_manager=SessionManager(...),
    agent_runner=AgentRunner(...),
    gateway_base_url=None  # 直接调用 AgentRunner
)

dispatcher = ChannelDispatcher(runtime=runtime)
await dispatcher.dispatch_inbound(ctx)
```

**工作流程**：
1. `dispatch_inbound` 调用 `_call_agent_direct()`
2. 直接调用 `AgentRunner.run()`
3. 从 `AgentRunResult.payloads` 提取文本
4. 调用 `plugin.deliver()` 发送回复

## 设计决策

### 为什么支持两种模式？

1. **开发/测试便利性**：简化模式下不需要启动 Gateway，便于快速测试
2. **对齐 OpenClaw**：Gateway 模式与 OpenClaw 设计一致，便于后续扩展
3. **灵活性**：根据场景选择合适模式

### Gateway 模式的优势

1. **统一监控**：所有 agent 调用都经过 Gateway，便于监控和调试
2. **事件流**：Gateway 提供 WebSocket 事件流，支持实时监控
3. **幂等性**：Gateway 的 dedupe 机制防止重复执行
4. **扩展性**：便于添加认证、限流、日志等功能

### 直接模式的优势

1. **简单**：不需要启动 Gateway 服务
2. **低延迟**：减少一次 HTTP RPC 调用
3. **测试友好**：单元测试更简单

## 实现细节

### Gateway 模式实现

```python
async def _call_agent_via_gateway(self, ctx: InboundContext) -> Optional[str]:
    """Call agent via Gateway RPC (aligned with OpenClaw)."""
    base_url = self.runtime.gateway_base_url or "http://127.0.0.1:18790"
    idem_key = str(uuid.uuid4())

    # Call agent RPC
    agent_params = {
        "message": ctx.text,
        "sessionKey": ctx.session_key,
        "sessionId": ctx.session_id,
        "agentId": ctx.agent_id,
        "idempotencyKey": idem_key,
    }
    start_res = call_rpc(base_url=base_url, method="agent", params=agent_params, timeout_ms=30000)

    run_id = start_res.get("runId")
    if not run_id:
        return None

    # Wait for completion
    wait_res = call_rpc(
        base_url=base_url,
        method="agent.wait",
        params={"runId": run_id, "timeoutMs": 30000},
        timeout_ms=32000,
    )

    payload = wait_res.get("payload", {})
    if payload.get("status") != "ok":
        error = payload.get("error")
        return f"[Error: {error}]" if error else None

    # Extract reply text from payload
    reply_text = payload.get("replyText") or ""
    return reply_text.strip() if reply_text else None
```

### Gateway 回复文本提取

Gateway 在 `agent.wait` 的 payload 中返回 `replyText`：

```python
# Gateway server 在 RunSnapshot 中保存 reply_text
@dataclass
class RunSnapshot:
    run_id: str
    status: str
    started_at: Optional[int] = None
    ended_at: Optional[int] = None
    error: Optional[str] = None
    reply_text: Optional[str] = None  # 累积的 assistant 回复文本

# Gateway 在 assistant 事件中累积文本
if evt.stream == "assistant":
    text = evt.data.get("text") or evt.data.get("delta") or ""
    if text and isinstance(text, str):
        rec.reply_text_buffer += text
    # ... 广播事件

# 在 lifecycle end 时保存到 snapshot
state.mark_run_terminal(
    run_id,
    RunSnapshot(
        run_id=run_id,
        status="ok",
        started_at=rec.started_at_ms,
        ended_at=int(ended_at),
        reply_text=rec.reply_text_buffer.strip() if rec.reply_text_buffer else None,
    ),
)
```

## 使用建议

### 生产环境

**推荐使用 Gateway 模式**：

```python
runtime = ChannelRuntime(
    session_manager=session_mgr,
    agent_runner=agent_runner,
    gateway_base_url="http://127.0.0.1:18790"  # 必须配置
)
```

**原因**：
- 统一监控和日志
- 支持事件流订阅
- 幂等性保护
- 便于扩展（认证、限流等）

### 开发/测试环境

**可以使用直接模式**：

```python
runtime = ChannelRuntime(
    session_manager=session_mgr,
    agent_runner=agent_runner,
    gateway_base_url=None  # 简化模式
)
```

**原因**：
- 不需要启动 Gateway
- 测试更简单
- 调试更方便

## 迁移指南

### 从直接模式迁移到 Gateway 模式

1. **启动 Gateway**：
   ```bash
   mw4agent gateway run --bind 127.0.0.1 --port 18790
   ```

2. **修改 ChannelRuntime 配置**：
   ```python
   # 之前
   runtime = ChannelRuntime(
       session_manager=session_mgr,
       agent_runner=agent_runner,
   )

   # 之后
   runtime = ChannelRuntime(
       session_manager=session_mgr,
       agent_runner=agent_runner,
       gateway_base_url="http://127.0.0.1:18790",
   )
   ```

3. **验证**：运行 channel，确认通过 Gateway 调用 agent

## 相关文档

- [Gateway 架构](gateway/mw4agent-gateway-agent-interaction.md)
- [Channels 实现](channels/mw4agent-channels-implementation.md)
- [OpenClaw Channels 架构](channels/openclaw-channels-architecture.md)
