# OpenClaw：Agent 在哪些情况下会向 Gateway 发起 RPC？

本文档回答一个具体问题：**OpenClaw 的 agent 运行过程中，在哪些场景会向 Gateway 发起 RPC 请求？**

结论：几乎都可以归类为两大类——**（A）工具调用（LLM tool calls）**与**（B）内部控制流/子系统协作**。底层通常通过 `callGateway(...)` 或 `callGatewayTool(...)` 发起请求。

## 1. 统一调用入口

### 1.1 `callGateway(...)`（通用 RPC）

很多 agent 侧逻辑直接调用 `callGateway({ method, params, ... })`（例如 sessions 工具、子智能体清理等）。

### 1.2 `callGatewayTool(...)`（工具封装 + 最小权限 scopes）

工具侧常用 `callGatewayTool(method, opts, params)`，它会解析 gateway URL/token/timeout，并为方法计算最小权限 scopes：

- 代码：`src/agents/tools/gateway.ts`

```140:160:src/agents/tools/gateway.ts
export async function callGatewayTool<T = Record<string, unknown>>(
  method: string,
  opts: GatewayCallOptions,
  params?: unknown,
  extra?: { expectFinal?: boolean },
) {
  const gateway = resolveGatewayOptions(opts);
  const scopes = resolveLeastPrivilegeOperatorScopesForMethod(method);
  return await callGateway<T>({
    url: gateway.url,
    token: gateway.token,
    method,
    params,
    timeoutMs: gateway.timeoutMs,
    expectFinal: extra?.expectFinal,
    clientName: GATEWAY_CLIENT_NAMES.GATEWAY_CLIENT,
    clientDisplayName: "agent",
    mode: GATEWAY_CLIENT_MODES.BACKEND,
    scopes,
  });
}
```

## 2. A 类：工具调用（LLM 调用工具时触发）

当模型在 agent loop 中发起工具调用，工具实现可能需要借助 Gateway 的“控制面/会话面/节点面”等能力，于是会向 Gateway 发起 RPC。

### 2.1 控制面：`gateway` 工具

**场景**：模型需要修改配置或触发更新等控制面动作。

**常见 RPC 方法**：

- `config.apply`
- `config.patch`
- `update.run`

**代码**：`src/agents/tools/gateway-tool.ts`

### 2.2 控制面：`cron` 工具（owner-only）

**场景**：模型需要管理网关内置 cron 调度器（新增/修改/触发任务、wake 等）。

**常见 RPC 方法**：

- `cron.status` / `cron.list`
- `cron.add` / `cron.update` / `cron.remove`
- `cron.run` / `cron.runs`
- `wake`

**代码**：`src/agents/tools/cron-tool.ts`

```285:292:src/agents/tools/cron-tool.ts
case "status":
  return jsonResult(await callGateway("cron.status", gatewayOpts, {}));
case "list":
  return jsonResult(await callGateway("cron.list", gatewayOpts, { includeDisabled: Boolean(params.includeDisabled) }));
```

### 2.3 会话面：`sessions_list` / `sessions_send` 等

**场景**：

- 列出 session（可见性/沙箱限制）
- 按 label 解析 sessionKey
- 往另一个 session 注入消息并等待它完成（有些流程会用到 `agent.wait`）

**常见 RPC 方法**：

- `sessions.list`
- `sessions.resolve`
-（子智能体/会话编排场景下）`sessions.patch` / `sessions.delete`

**代表代码**：

- `src/agents/tools/sessions-list-tool.ts`
- `src/agents/tools/sessions-send-tool.ts`

```79:88:src/agents/tools/sessions-list-tool.ts
const list = await callGateway<{ sessions: Array<SessionListRow>; path: string }>({
  method: "sessions.list",
  params: { limit, activeMinutes, includeGlobal: !restrictToSpawned, includeUnknown: !restrictToSpawned, spawnedBy: restrictToSpawned ? effectiveRequesterKey : undefined },
});
```

```114:118:src/agents/tools/sessions-send-tool.ts
const resolved = await callGateway<{ key: string }>({
  method: "sessions.resolve",
  params: resolveParams,
  timeoutMs: 10_000,
});
```

### 2.4 节点面：`nodes` 工具（node.invoke + 审批）

**场景**：模型通过 node 执行命令、抓取媒体、运行系统操作等，需要 Gateway 转发给 node；某些高风险命令会触发“审批流”。

**常见 RPC 方法**：

- `node.invoke`
- `exec.approval.request`（当 node 返回 “approval required” 时，走网关审批）

**代码**：`src/agents/tools/nodes-tool.ts`

```646:663:src/agents/tools/nodes-tool.ts
const prepareRaw = await callGatewayTool<{ payload?: unknown }>(
  "node.invoke",
  gatewayOpts,
  { nodeId, command: "system.run.prepare", params: { command, rawCommand: formatExecCommand(command), cwd, agentId, sessionKey }, timeoutMs: invokeTimeoutMs, idempotencyKey: crypto.randomUUID() },
);
```

## 3. B 类：内部控制流/子系统协作（不是 LLM 直接 tool call）

这类 RPC 并非来自模型“工具调用”，而是 OpenClaw 自己为了编排 agent / 子智能体 / session 生命周期而调用 Gateway。

### 3.1 等待 run 终态：`agent.wait`

**场景**：当一个流程需要“触发 run 后等待结束”（例如 nested agent step、子智能体完成通知等）。

**典型代码**：`src/agents/tools/agent-step.ts`

```44:75:src/agents/tools/agent-step.ts
const response = await callGateway<{ runId?: string }>({ method: "agent", params: {...}, timeoutMs: 10_000 });
...
const wait = await callGateway<{ status?: string }>({
  method: "agent.wait",
  params: { runId: resolvedRunId, timeoutMs: stepWaitMs },
  timeoutMs: stepWaitMs + 2000,
});
```

**其他相关位置**（同样会用到 `agent.wait`）：

- `src/agents/subagent-registry.ts`
- `src/agents/subagent-announce.ts`
- `src/agents/tools/subagents-tool.ts`
- `src/agents/tools/sessions-send-tool.ts` / `sessions-send-tool.a2a.ts`

### 3.2 子智能体/会话清理与元信息更新：`sessions.patch` / `sessions.delete`

**场景**：

- 子智能体创建失败后清理 provisional session
- 子智能体结束后按策略 delete/keep transcript
- 在运行记录/标签/可见性等层面更新 session store

**典型代码**：`src/agents/subagent-spawn.ts`（best-effort cleanup）

```150:158:src/agents/subagent-spawn.ts
await callGateway({
  method: "sessions.delete",
  params: { key: childSessionKey, emitLifecycleHooks: options?.emitLifecycleHooks === true, deleteTranscript: options?.deleteTranscript === true },
  timeoutMs: 10_000,
});
```

此外还会在：

- `src/agents/subagent-registry.ts`
- `src/agents/subagent-announce.ts`
- `src/agents/acp-spawn.ts`

看到 `sessions.patch` / `sessions.delete` 的调用。

## 4. 快速清单：常见的 Gateway RPC 方法族

按语义分组：

- **Agent run 编排**：`agent`、`agent.wait`
- **会话目录/元信息**：`sessions.list`、`sessions.resolve`、`sessions.patch`、`sessions.delete`
- **控制面**：`config.apply`、`config.patch`、`update.run`
- **调度器**：`cron.*`、`wake`
- **节点/设备调用与审批**：`node.invoke`、`exec.approval.request`

## 5. 小结

OpenClaw 的 agent 之所以会“向 gateway 发 RPC”，根本原因是 Gateway 承担了 **控制面 + 资源编排/访问的中心**：

- 模型工具要访问 cron/config/node 等能力 → 走 gateway
- 子智能体/跨会话行为需要统一的 session store 与等待语义 → 走 gateway
- 一些高风险动作需要审批/权限 scopes → 由 gateway 统一仲裁

