# Orbit 简易 node-host：用法与改动总结

Orbit 内置了一个与 OpenClaw Gateway 兼容的简易 node-host，可将本机注册为一台 node，并在本机执行 `system.run` / `system.run.prepare` 等命令。

---

## 1. 用法

### 1.1 CLI 命令

```bash
# 连接 OpenClaw Gateway（需先在 Gateway 侧完成该 node 的配对）
orbit node-host run --url ws://127.0.0.1:18789 --node-id orbit-node

# 若 Gateway 需要认证，传入 token
orbit node-host run --url ws://127.0.0.1:18789 --node-id my-node --token YOUR_TOKEN

# 断开后不再重连（默认会每 5 秒重连）
orbit node-host run --url ws://127.0.0.1:18789 --no-reconnect
```

### 1.2 参数说明

| 参数 | 说明 |
|------|------|
| `--url` | （必填）Gateway WebSocket 地址，如 `ws://127.0.0.1:18789` |
| `--node-id` | Node ID，默认 `orbit-node`，需与 Gateway 侧配对一致 |
| `--display-name` | 可选，本 node 的显示名称 |
| `--token` | Gateway 需要认证时使用 |
| `--no-reconnect` | 断开后不自动重连；默认每 5 秒重连 |

### 1.3 使用步骤

1. **安装依赖**：`pip install websockets` 或 `pip install -e .`
2. **在 OpenClaw Gateway 侧配对该 node**（使用 OpenClaw 的配对流程，使 Gateway 认识该 nodeId）。
3. **在本机启动 node-host**：执行上述 `orbit node-host run ...`。
4. 通过 OpenClaw Agent 的 nodes 工具或 Dashboard 对该 node 发起 `node.invoke`（如 `system.run`），本机 node-host 会执行命令并回传结果。

---

## 2. 改动总结

### 2.1 新增模块

- **`orbit/node_host/`**
  - **`client.py`**：WebSocket 客户端。连接 OpenClaw Gateway；收到 `connect.challenge` 后发送 `connect`（role=node、nodeId、caps、commands、token）；收到 `node.invoke.request` 时执行对应 command 并回复 `node.invoke.result`。
  - **`runner.py`**：本地执行 `system.run`。接收 `command`(argv)、`cwd`、`env`、`timeoutMs`，用 `subprocess.run` 执行，返回 `stdout`、`stderr`、`exitCode`。
  - 支持的 **command**：`system.run`（执行 shell 命令）、`system.run.prepare`（返回执行计划，供 Gateway/Agent 审批流程使用）。

### 2.2 新增 CLI

- **`orbit node-host run`**：见上文用法。注册在 `orbit/cli/node_host/register.py`，在 `orbit/cli/main.py` 中通过 `CommandEntry` 注册到主程序。

### 2.3 依赖

- **`websockets>=12.0`**：已加入 `setup.py` 的 `install_requires`。

### 2.4 协议与实现要点

- **协议**：WebSocket 连接后等待 Gateway 下发的 `connect.challenge` 事件，再发送 `connect` 请求（role=node、client.id=nodeId、caps=`["system"]`、commands=`["system.run.prepare", "system.run"]`）；收到 `node.invoke.request` 时执行对应命令并回复 `node.invoke.result`。
- **代码位置**：`orbit/node_host/`（`client.py` 负责连接与协议，`runner.py` 负责 `system.run` 的 subprocess 执行），CLI 注册在 `orbit/cli/node_host/register.py`。

### 2.5 相关文档

- OpenClaw 多 node 管理与跨 node 执行命令：`docs/openclaw/nodes.md`
- Gateway 节点面与 node.invoke：`docs/architecture/gateway/agent_call_gateway.md`

---

## 3. Gateway 对 node 的认证（Orbit Gateway）

Orbit Gateway 支持 node 连接（WebSocket 路径 `/ws-node`）并对 node 做 **token 认证**。

### 3.1 行为说明

- **未配置 token**（默认）：不校验 node 的 auth，任何连接至 `/ws-node` 且 `connect` 时 `role=node` 的客户端都会被接受并注册为 node（仅适合本机/开发环境）。
- **已配置 token**：仅当 `connect` 请求中 `params.auth.token` 与 Gateway 配置的 token **完全一致**时，才接受该 node 连接；否则返回错误 `node authentication required (invalid or missing token)`。

### 3.2 配置方式

- **环境变量**：`GATEWAY_NODE_TOKEN=<token>`（启动 Gateway 前设置）。
- **CLI**：`orbit gateway run --node-token <token>`。

两种方式可同时使用；CLI 的 `--node-token` 会覆盖环境变量。若需“必须认证”，则至少配置其中一种。

### 3.3 node-host 侧

连接 **Orbit Gateway** 时，node-host 需使用 **WebSocket 路径 `/ws-node`**，例如：

```bash
# 无认证（Gateway 未设置 node token）
orbit node-host run --url ws://127.0.0.1:18790/ws-node --node-id orbit-node

# 有认证（Gateway 已设置 GATEWAY_NODE_TOKEN 或 --node-token）
orbit node-host run --url ws://127.0.0.1:18790/ws-node --node-id orbit-node --token YOUR_TOKEN
```

Orbit Gateway 默认端口为 **18790**（与 OpenClaw 的 18789 不同）。

### 3.4 实现位置

- **Gateway**：`orbit/gateway/server.py` 中 `/ws-node` 在收到 `connect` 且 `role=node` 时，若 `state.node_token` 非空则校验 `params.auth.token`；`orbit/gateway/state.py` 中 `GatewayState.node_token` 与 `GatewayState.node_registry`；`orbit/gateway/node_registry.py` 中 node 注册与 `node.invoke` 转发。
- **CLI**：`orbit gateway run --node-token` 在 `orbit/cli/gateway/register.py` 中注册并传入 `create_app(node_token=...)`。

---

## 4. 本机测试步骤

### 4.1 使用 Orbit Gateway（推荐：无需 OpenClaw）

1. **终端 A**：启动 Gateway（可选：开启 node 认证）
   ```bash
   # 无认证
   orbit gateway run
   # 或带 node token
   orbit gateway run --node-token my-secret-token
   ```
2. **终端 B**：启动 node-host（URL 使用 `/ws-node`，端口 18790）
   ```bash
   orbit node-host run --url ws://127.0.0.1:18790/ws-node --node-id orbit-node
   # 若 Gateway 使用了 --node-token，则加：--token my-secret-token
   ```
3. **终端 C**：通过 RPC 查看节点并发起调用
   ```bash
   # 列出节点（需使用 HTTP RPC，如 curl）
   curl -s -X POST http://127.0.0.1:18790/rpc -H "Content-Type: application/json" -d '{"id":"1","method":"node.list","params":{}}'
   # 对 node 执行命令
   curl -s -X POST http://127.0.0.1:18790/rpc -H "Content-Type: application/json" -d '{"id":"2","method":"node.invoke","params":{"nodeId":"orbit-node","command":"system.run","params":{"command":["echo","hello"]}}}'
   ```

### 4.2 使用 OpenClaw Gateway

node-host 也可连接 **OpenClaw 的 Gateway**（WebSocket 协议含 `connect.challenge`、`node.invoke.request` 等）。**orbit 自带的 Gateway 不支持 node 协议**，因此本机联调需要先起 OpenClaw Gateway，再起 orbit node-host，最后用 OpenClaw CLI 或 Dashboard 发起调用。

### 4.3 前提（OpenClaw 方案）

- 本机已安装并能运行 **OpenClaw**（Gateway + CLI），例如 clone 同级的 `openclaw` 仓库并 `pnpm install && pnpm build`。
- 本机已安装 **orbit** 且可执行 `orbit node-host run`（`pip install -e .` 或 `pip install websockets`）。

### 4.4 执行顺序与各侧命令（OpenClaw）

| 顺序 | 角色 | 终端 | 执行命令 | 说明 |
|------|------|------|----------|------|
| 1 | **Gateway** | 终端 A | 在 openclaw 仓库根目录执行：<br/>`pnpm gateway` 或 `openclaw gateway` | 启动 OpenClaw Gateway，默认监听 `ws://127.0.0.1:18789`。若配置了认证，记下 token 或 password。 |
| 2 | **Node** | 终端 B | `orbit node-host run --url ws://127.0.0.1:18789 --node-id orbit-node`<br/>（若 Gateway 需认证则加 `--token YOUR_TOKEN`） | 以 node 身份连接 Gateway；日志出现 “Hello OK from gateway” 表示已注册成功。 |
| 3 | **调用方** | 终端 C | 在 openclaw 仓库下执行：<br/>`openclaw nodes list`<br/>`openclaw nodes invoke --node orbit-node --command system.run --params '{"command":["echo","hello"]}'` | 先确认 node 在列表中且为 connected；再对该 node 发起 `system.run`，本机 node-host 会执行并回传结果。 |

### 4.5 分步说明（OpenClaw）

**步骤 1：启动 Gateway（终端 A）**

```bash
# 进入 OpenClaw 仓库
cd /path/to/openclaw
pnpm gateway
# 或
openclaw gateway
```

- 默认 HTTP/WS 端口为 **18789**（`http://127.0.0.1:18789` / `ws://127.0.0.1:18789`）。
- 若本地配置了 `gateway.auth.token` 或 password，后续 node 连接与 CLI 调用需带上相同 token 或 password。

**步骤 2：启动 node-host（终端 B）**

```bash
# 在 orbit 环境中
orbit node-host run --url ws://127.0.0.1:18789 --node-id orbit-node
```

- 若 Gateway 需要认证：  
  `orbit node-host run --url ws://127.0.0.1:18789 --node-id orbit-node --token YOUR_TOKEN`
- 看到日志中的 “Hello OK from gateway” 即表示已连接并注册为 node。

**步骤 3：查看 node 列表并发起调用（终端 C）**

```bash
# 列出节点（应能看到 orbit-node 且 connected）
openclaw nodes list

# 对 orbit-node 执行一条简单命令
openclaw nodes invoke --node orbit-node --command system.run --params '{"command":["echo","hello"]}'
```

- 若使用 **nodes run** 封装（会走 system.run.prepare + system.run）：  
  `openclaw nodes run --node orbit-node --raw "echo hello"`

### 4.6 小结（OpenClaw）

| 侧 | 执行内容 |
|----|----------|
| **Gateway** | 先启动 OpenClaw Gateway（`pnpm gateway` / `openclaw gateway`），保证 `ws://127.0.0.1:18789` 可连。 |
| **Node** | 再启动 orbit node-host（`orbit node-host run --url ws://127.0.0.1:18789 --node-id orbit-node`），确认日志出现 Hello OK。 |
| **调用** | 最后用 OpenClaw CLI（`openclaw nodes list` / `openclaw nodes invoke` 或 `nodes run`）或 Dashboard 对该 node 发起 `node.invoke`。 |
