# MW4Agent CLI 使用手册

本文介绍 `mw4agent` 命令行工具的基本用法，重点围绕当前已经实现的四大命令组：

- `gateway`：运行 / 诊断 Gateway
- `agent`：通过 Gateway 触发一次智能体执行
- `channels`：运行各类通道（console / telegram / webhook / feishu）
- `config`：读写加密配置文件

所有示例均假设你在仓库根目录运行：

```bash
cd /path/to/mw4agent
python -m mw4agent --help
```

---

## 1. 顶级结构概览

运行：

```bash
python -m mw4agent --help
```

可以看到当前可用命令：

- `gateway`：运行、探测和调用 Gateway RPC
- `agent`：通过 Gateway 触发一次 Agent 运行
- `channels`：运行 console / telegram / webhook / feishu 通道
- `config`：读写加密配置文件（`ConfigManager` 封装）

---

## 2. `gateway` 命令组

### 2.1 启动 Gateway

```bash
python -m mw4agent gateway run \
  --bind 127.0.0.1 \
  --port 18789 \
  --session-file mw4agent.sessions.json
```

- **`--bind`**：监听地址（本机测试推荐 `127.0.0.1`）
- **`--port`**：HTTP 端口（默认 `18789`，与测试用例一致）
- **`--session-file`**：Gateway 的 session 存储文件路径

### 2.2 查看 Gateway 状态

```bash
python -m mw4agent gateway status --url http://127.0.0.1:18789
```

或输出 JSON：

```bash
python -m mw4agent gateway status \
  --url http://127.0.0.1:18789 \
  --json
```

### 2.3 直接调用 RPC 方法

```bash
python -m mw4agent gateway call health \
  --url http://127.0.0.1:18789 \
  --params '{}' \
  --json
```

也可以调用 `agent` / `agent.wait` 等方法（等价于测试里的 `_rpc_call`）：

```bash
python -m mw4agent gateway call agent \
  --url http://127.0.0.1:18789 \
  --params '{"message":"hi","sessionKey":"cli:test","sessionId":"cli-test","agentId":"cli","idempotencyKey":"test-1"}' \
  --json
```

### 2.4 其他辅助子命令

目前还提供了占位性质的：

- `gateway health`：简单封装 health 调用
- `gateway discover` / `gateway probe`：预留扩展位（当前返回静态结果）

---

## 3. `agent` 命令组（通过 Gateway 跑一次 Agent）

### 3.1 最小示例：跑一次 echo LLM

确保 Gateway 已在本地 `http://127.0.0.1:18789` 运行后：

```bash
python -m mw4agent agent run \
  --message "Hello from CLI" \
  --url http://127.0.0.1:18789
```

关键参数：

- **`--message`**：发送给 Agent 的用户消息（必填）
- **`--url`**：Gateway 地址（不填默认 `http://127.0.0.1:18789`）
- **`--session-key`**：会话 key，默认 `cli:default`
- **`--session-id`**：会话 id，默认 `cli-default`
- **`--timeout`**：`agent.wait` 超时时间（毫秒）
- **`--json`**：输出完整 `agent` + `agent.wait` 的 JSON 结果

### 3.2 带工具的运行：预先调用 `gateway_ls` 工具

`agent run` 支持在真正跑 LLM 前先调用一个工具（目前是 `gateway_ls`）并把结果注入 system prompt：

```bash
python -m mw4agent agent run \
  --message "请根据当前目录结构给出下一步建议" \
  --with-gateway-ls \
  --ls-path "." \
  --url http://127.0.0.1:18789
```

行为：

1. CLI 先通过 `GatewayLsTool` 调用 Gateway 的 `ls` RPC；
2. 把目录列表以文本形式塞进一个增强的 `extraSystemPrompt`；
3. 再调用 Gateway 的 `agent` + `agent.wait` 跑完整的 LLM 回合；
4. 最终在终端输出运行状态（或 JSON）。

---

## 4. `channels` 命令组（运行通道）

`channels` 子命令负责启动不同的通道 monitor，并将入站消息统一交给 `ChannelDispatcher` → `AgentRunner`。

### 4.1 console 通道（本地 stdin/stdout）

```bash
python -m mw4agent channels console run \
  --session-file mw4agent.sessions.json
```

启动后：

- 你可以在终端输入一行文本，按回车；
- console channel 会构造一个 `InboundContext`，通过 dispatcher 交给 `AgentRunner`；
- Agent 回复会以 `[AI] ...` 的形式打印到 stdout。

这是目前最简单的“本地聊天”方式，适合验证 AgentRunner/LLM/tool-call 是否工作正常。

### 4.2 Telegram 通道（长轮询）

```bash
export TELEGRAM_BOT_TOKEN="你的 Bot Token"

python -m mw4agent channels telegram run \
  --session-file mw4agent.sessions.json
```

- **`--bot-token`**：可显式传入，也可通过环境变量 `TELEGRAM_BOT_TOKEN` 提供；
- **`--session-file`**：会话存储文件，与 Gateway 共用同一格式。

### 4.3 Webhook 通道（泛用 HTTP Webhook）

```bash
python -m mw4agent channels webhook run \
  --host 0.0.0.0 \
  --port 8080 \
  --path /webhook \
  --session-file mw4agent.sessions.json
```

常见场景：从第三方系统（CI/CD、监控、业务系统）以 HTTP POST 的方式推消息进来，再由 Agent 处理。

### 4.4 Feishu 通道（Webhook / WebSocket 占位）

Webhook 模式示例：

```bash
python -m mw4agent channels feishu run \
  --mode webhook \
  --host 0.0.0.0 \
  --port 8081 \
  --path /feishu/webhook \
  --session-file mw4agent.sessions.json
```

当前 WebSocket 模式尚未实现，CLI 会给出明确报错与文档指引。

---

## 5. `config` 命令组（加密配置读写）

`config` 子命令封装了 `ConfigManager` 加密读写逻辑，用于统一管理诸如 `llm.json`、通道配置等敏感配置文件。

### 5.1 读取配置

```bash
python -m mw4agent config read llm
```

- 默认从 `~/.mw4agent/config/llm.json`（或 `MW4AGENT_CONFIG_DIR` 指定目录）读取；
- 如果配置被加密，内部会自动解密；
- 输出为格式化 JSON。

如果希望得到一行原始 JSON：

```bash
python -m mw4agent config read llm --raw
```

### 5.2 写入配置

从 JSON 文件写入（推荐方式）：

```bash
python -m mw4agent config write llm --input llm.json
```

从 stdin 管道写入：

```bash
echo '{"provider":"openai","model":"gpt-4o-mini"}' | \
  python -m mw4agent config write llm --stdin
```

写入后，实际磁盘上的 `llm.json` 将以 AES-GCM 加密存储，只有在提供正确的 `MW4AGENT_SECRET_KEY` 时才能被解密读取。

---

## 6. 小结

- 使用 `gateway run` + `channels console run` 可以在本机快速搭建一个“Gateway + Console Chat”的测试环境；
- 使用 `agent run` 可以脚本化触发单次 Agent 回合（支持在调用前执行工具）；
- 使用 `config read/write` 可以安全地管理加密配置（LLM provider、通道配置等），避免手工处理加密细节。

后续可以在 `docs/manuals/` 下为不同通道、不同运行模式补充更详细的 CLI 示例（如与 mock LLM server 联动的完整演示）。 

