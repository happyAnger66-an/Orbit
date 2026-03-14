# Console Channel 实现原理与代码流程

Console 是 MW4Agent 的「控制台」通道：入站来自 stdin 的逐行输入，出站通过 stdout 打印 AI 回复，用于本地调试或无 UI 场景。设计与 OpenClaw 的 channel 体系对齐，通过统一的 ChannelPlugin + ChannelDispatcher 接入。

---

## 1. 实现原理概览

- **入站**：在事件循环中异步读取 `sys.stdin` 的每一行，忽略空行；遇到 `/quit` 或 `/exit` 时退出 monitor。
- **会话与身份**：所有输入视为同一会话，固定 `session_key="console:main"`、`session_id="console-main"`；不区分用户，一律视为已授权、已 @ 提及（`was_mentioned=True`），因此不会触发 mention 过滤。
- **调用 Agent**：每条有效输入封装为 `InboundContext`，交给 `ChannelDispatcher.dispatch_inbound`；Dispatcher 根据是否配置 `gateway_base_url` 选择「直连 AgentRunner」或「经 Gateway RPC」调用 agent，拿到回复文本后再回调当前 channel 的 `deliver`。
- **出站**：Console 的 `deliver` 将回复（或错误）以 `[AI] ...` / `[ERR] ...` 前缀打印到 `sys.stdout` 并 flush。

因此整体是：**stdin → run_monitor 读行 → InboundContext → dispatch_inbound → Agent（直连或 Gateway）→ deliver → stdout**。

---

## 2. 代码流程（端到端）

### 2.1 CLI 入口

- 命令：`mw4agent channels console run [--session-file=...] [--gateway-url=URL]`
- 注册位置：`mw4agent/cli/channels/register.py` 的 `register_channels_cli`。
- 流程：
  1. 在 `channels` 下挂 `console` 子组，再挂 `run` 子命令。
  2. `run_console(session_file, gateway_url)` 被调用时，用 `asyncio.run(_run())` 进入异步入口 `_run()`。
  3. `_run()` 内：取全局 `ChannelRegistry`，若尚未注册 `console` 则 `registry.register_plugin(ConsoleChannel())`；构造 `SessionManager(session_file)`、`AgentRunner(session_manager)`；若 `--gateway-url` 或环境变量 `MW4AGENT_GATEWAY_URL` 有值，则 `ChannelRuntime(..., gateway_base_url=gateway_url)`，否则 `gateway_base_url=None`（直连 Agent）；最后 `await dispatcher.run_channel("console")`。

### 2.2 注册与获取 Plugin

- **Registry**：`mw4agent/channels/registry.py` 单例 `ChannelRegistry`，`register_plugin(plugin)` 把 `plugin` 与 `plugin.dock` 按 `plugin.id` 存起来；`get_plugin("console")` 返回 `ConsoleChannel` 实例。
- **ConsoleChannel**：`mw4agent/channels/plugins/console.py`。继承 `ChannelPlugin`，构造时固定：
  - `id="console"`
  - `ChannelCapabilities(chat_types=("direct",), native_commands=True, block_streaming=False)`
  - `ChannelDock(id="console", ..., resolve_require_mention=lambda _acct: False)`，即不需要 @ 提及。
  - `ChannelMeta(id="console", label="Console", docs_path="/channels/console")`

### 2.3 启动 Monitor：`run_channel("console")`

- 在 **dispatcher**（`mw4agent/channels/dispatcher.py`）中，`run_channel(channel_id)` 根据 `channel_id` 从 registry 取出对应 plugin，然后调用：
  ```text
  await plugin.run_monitor(on_inbound=self.dispatch_inbound)
  ```
  即把 `dispatch_inbound` 作为「入站回调」交给 channel。

### 2.4 Console 的 `run_monitor`（读 stdin → 构造 InboundContext → 回调）

- 实现位置：`mw4agent/channels/plugins/console.py` 的 `ConsoleChannel.run_monitor(on_inbound)`。
- 行为：
  1. 用 `loop.run_in_executor(None, sys.stdin.readline)` 异步读一行（避免阻塞事件循环）。
  2. 若读到 `None`（EOF）则 return；若为空行则 continue；若为 `/quit` 或 `/exit`（忽略大小写）则 return。
  3. 否则用当前行构造 `InboundContext`：
     - `channel="console"`, `text=line`, `session_key="console:main"`, `session_id="console-main"`, `agent_id="main"`, `chat_type="direct"`, `was_mentioned=True`, `command_authorized=True`, `sender_is_owner=True`, `sender_id="local"`, `sender_name="local"`, `timestamp_ms=...`
  4. 在 plugin 内再走一遍 `resolve_mention_gating`（console 的 dock 为不需 mention，所以实际不会 skip）。
  5. 调用 `await on_inbound(ctx)`，即进入 **dispatcher 的 `dispatch_inbound`**。

### 2.5 Dispatcher：`dispatch_inbound(ctx)`

- 实现位置：`mw4agent/channels/dispatcher.py`。
- 流程：
  1. 用 `ctx.channel` 从 registry 取 `plugin` 和 `dock`；若无 plugin 则抛 `ValueError`。
  2. **Mention 门控**：根据 `dock.require_mention(None)` 与 `ctx.chat_type`、`ctx.was_mentioned` 调用 `resolve_mention_gating`；若 `gate.should_skip` 为 True 则直接 return（console 不会走到这里）。
  3. **调用 Agent**：
     - 若 `runtime.gateway_base_url` 有值：走 `_call_agent_via_gateway(ctx)`，对 Gateway 发 `agent` + `agent.wait` RPC，从 payload 取 `replyText` 作为 `result_text`。
     - 否则：走 `_call_agent_direct(ctx)`，用 `AgentRunParams` 调 `runtime.agent_runner.run(params)`，从 `result.payloads` 拼出文本作为 `result_text`。
  4. 若 `result_text` 非空，则 `await plugin.deliver(OutboundPayload(text=result_text, is_error=False, extra={}))`。

因此对 console 而言，`dispatch_inbound` = 校验 channel + mention → 调 agent（直连或 Gateway）→ 用同一 plugin 把回复交给 `deliver`。

### 2.6 Console 的 `deliver(payload)`

- 实现位置：`mw4agent/channels/plugins/console.py` 的 `ConsoleChannel.deliver`。
- 行为：根据 `payload.is_error` 选前缀 `"ERR"` 或 `"AI"`，向 `sys.stdout` 写 `"[{prefix}] {payload.text}\n"` 并 `flush()`。

---

## 3. 数据与类型

- **InboundContext**（`mw4agent/channels/types.py`）：channel、text、session_key、session_id、agent_id、chat_type、was_mentioned、command_authorized、sender_is_owner、sender_id、sender_name、timestamp_ms、extra 等；Console 构造时全部填满，且始终「已提及、已授权」。
- **OutboundPayload**：text、is_error、extra；Dispatcher 只填 text，deliver 侧用 is_error 决定前缀。
- **ChannelRuntime**（dispatcher）：`session_manager`、`agent_runner`、可选 `gateway_base_url`；`channels console run` 不设 `gateway_base_url`，故始终直连 `AgentRunner`。

---

## 4. 相关文件一览

| 角色 | 文件 |
|------|------|
| CLI 注册与入口 | `mw4agent/cli/channels/register.py` |
| Console 插件实现 | `mw4agent/channels/plugins/console.py` |
| 插件基类与类型 | `mw4agent/channels/plugins/base.py`，`mw4agent/channels/types.py` |
| Dock / 策略 | `mw4agent/channels/dock.py` |
| 调度与 Agent 调用 | `mw4agent/channels/dispatcher.py` |
| Mention 门控 | `mw4agent/channels/mention_gating.py` |
| 全局 Registry | `mw4agent/channels/registry.py` |

---

## 5. 如何走 Gateway 而不是直连 Agent

默认情况下 `mw4agent channels console run` 使用**直连 AgentRunner**（不经过 Gateway）。若要经 **Gateway RPC** 调用 agent，需满足两点：

1. **先启动 Gateway**（可与 channel 同机或远程）：
   ```bash
   mw4agent gateway run --bind 127.0.0.1 --port 18790
   ```

2. **启动 console（或其它 channel）时指定 Gateway 地址**，任选其一：
   - 命令行：`mw4agent channels console run --gateway-url http://127.0.0.1:18790`
   - 环境变量：`export MW4AGENT_GATEWAY_URL=http://127.0.0.1:18790`，然后执行 `mw4agent channels console run`

只要 `ChannelRuntime` 的 `gateway_base_url` 被设置为非空，`ChannelDispatcher.dispatch_inbound` 就会走 `_call_agent_via_gateway`（对 Gateway 发 `agent` + `agent.wait` RPC），而不会直连 `AgentRunner.run()`。  
其他 channel（telegram、webhook、feishu）的 `run` 子命令同样支持 `--gateway-url` 与 `MW4AGENT_GATEWAY_URL`，用法一致。

---

## 6. 小结

- **Console** 以 stdin 为输入、stdout 为输出，通过 **ConsoleChannel** 实现 `run_monitor`（读行 → 构造 InboundContext → 调用 `on_inbound`）和 `deliver`（按前缀写 stdout）。
- **ChannelDispatcher** 提供统一入口 `dispatch_inbound` 和 `run_channel`；`run_channel("console")` 启动 console 的 monitor，并把 `dispatch_inbound` 作为 `on_inbound` 传入。
- **Agent 调用** 在 dispatcher 内二选一：无 `gateway_base_url` 时直连 `AgentRunner.run()`，有则通过 Gateway 的 `agent` + `agent.wait` RPC；得到文本后由同一 plugin 的 `deliver` 输出。
- **走 Gateway**：先启动 `mw4agent gateway run`，再在运行 channel 时加上 `--gateway-url http://127.0.0.1:18790` 或设置环境变量 `MW4AGENT_GATEWAY_URL`。
- 整体流程：**CLI `channels console run` [--gateway-url=...] → 注册 ConsoleChannel → dispatcher.run_channel("console") → plugin.run_monitor(dispatch_inbound) → 读 stdin → InboundContext → dispatch_inbound → Agent（直连或 Gateway）→ plugin.deliver → stdout**。
