# OpenClaw：Agent 如何与 Gateway 交互（RPC/事件流/等待语义）

本文档梳理 OpenClaw 中 **Agent 执行系统**与 **Gateway** 的交互方式，聚焦：

- Gateway RPC：`agent` / `agent.wait`
- 入口校验、幂等去重（dedupe）与异步执行
- Agent 运行时如何发出事件（lifecycle/assistant/tool）
- Gateway 如何广播事件并实现 wait 语义

该模型可作为 MW4Agent 后续实现 “Gateway + Agent Runner + 多通道” 的参考。

## 1. 总览：一次 Agent Run 的端到端链路

典型路径（以 Gateway RPC 触发为例）：

1. 客户端调用 **RPC `agent`**
2. Gateway 校验参数、解析会话/路由、写入 dedupe “已接受”快照 → **立即返回 `{ runId, acceptedAt }`**
3. Gateway 异步调用 `agentCommandFromIngress(...)` → `agentCommandInternal(...)`
4. `agentCommandInternal` 组装运行参数，调用 `runEmbeddedPiAgent(...)`
5. `runEmbeddedPiAgent` 内部创建/恢复会话、订阅 pi 事件，将事件映射为 OpenClaw 事件流，并在关键节点 `emitAgentEvent(...)`
6. Gateway 侧 `createAgentEventHandler(...)` 将 agent 事件广播到 WebSocket 客户端/节点订阅者
7. 客户端可调用 **RPC `agent.wait`** 等待 lifecycle 结束（end/error/timeout）

## 2. Gateway RPC：`agent`（触发执行）

### 2.1 核心行为

`src/gateway/server-methods/agent.ts` 的 `agent` handler 做了三件关键事：

- **校验与标准化**：验证请求、解析 `sessionKey/sessionId`、channel/to/thread、attachments 等
- **幂等去重（dedupe）**：
  - 使用 `idempotencyKey`（请求参数）作为去重键
  - 先写入 “in-flight accepted” 到 `context.dedupe`，避免重试触发重复 run
- **异步执行**：
  - 立刻返回 accepted
  - 在后台 `void agentCommandFromIngress(...)`
  - 完成后把终态结果再写入 dedupe，并（二次）respond 以兼容 `expectFinal` 的 TS 客户端

关键代码（节选）：

```588:694:src/gateway/server-methods/agent.ts
const accepted = { runId, status: "accepted" as const, acceptedAt: Date.now() };
setGatewayDedupeEntry({ dedupe: context.dedupe, key: `agent:${idem}`, entry: { ts: Date.now(), ok: true, payload: accepted } });
respond(true, accepted, undefined, { runId });

void agentCommandFromIngress(
  { message, sessionId: resolvedSessionId, sessionKey: resolvedSessionKey, ..., runId, lane: request.lane, senderIsOwner },
  defaultRuntime,
  context.deps,
)
  .then((result) => {
    const payload = { runId, status: "ok" as const, summary: "completed", result };
    setGatewayDedupeEntry({ dedupe: context.dedupe, key: `agent:${idem}`, entry: { ts: Date.now(), ok: true, payload } });
    respond(true, payload, undefined, { runId });
  })
  .catch((err) => { ... });
```

### 2.2 为什么要 “accepted 立即返回 + 后台执行”

- WebSocket/RPC 连接可能短；模型推理与工具链路可能长
- 让客户端能立刻拿到 `runId`，并通过 `agent.wait` 或事件流继续跟踪
- `dedupe` 确保网络重试不会产生重复执行

## 3. 从 Gateway 到 Agent：`agentCommandFromIngress` 的桥

`src/commands/agent.ts` 定义了 `agentCommand`（CLI 入口）与 `agentCommandFromIngress`（Gateway ingress 入口）。

### 3.1 ingress 的一个关键防线：强制显式 `senderIsOwner`

Gateway 入口调用必须显式传 `senderIsOwner`，否则直接抛错（防止非 TS 调用方遗漏导致 owner-only 工具策略错误）。

```966:982:src/commands/agent.ts
export async function agentCommandFromIngress(opts: AgentCommandIngressOpts, runtime = defaultRuntime, deps = createDefaultDeps()) {
  if (typeof opts.senderIsOwner !== "boolean") {
    throw new Error("senderIsOwner must be explicitly set for ingress agent runs.");
  }
  return await agentCommandInternal({ ...opts, senderIsOwner: opts.senderIsOwner }, runtime, deps);
}
```

### 3.2 最终落点：`runEmbeddedPiAgent(...)`

`agentCommandInternal` 最终会调用 `runEmbeddedPiAgent(...)`，把路由/线程/群聊上下文、`runId/lane`、`senderIsOwner` 等全部透传下去：

```288:330:src/commands/agent.ts
return runEmbeddedPiAgent({
  sessionId,
  sessionKey,
  agentId: sessionAgentId,
  trigger: "user",
  messageChannel,
  messageTo,
  messageThreadId,
  groupId,
  groupChannel,
  groupSpace,
  spawnedBy,
  senderIsOwner: opts.senderIsOwner,
  ...
  runId,
  lane: opts.lane,
  extraSystemPrompt: opts.extraSystemPrompt,
});
```

## 4. Agent → Gateway：事件流（`emitAgentEvent`）与 lifecycle

### 4.1 lifecycle 事件从哪里来

在 pi 运行时订阅层（`subscribeEmbeddedPiSession` 的 handlers）里，OpenClaw 把底层 session 的生命周期映射为：

- `lifecycle:start`
- `lifecycle:end`
- `lifecycle:error`

并通过 `emitAgentEvent(...)` 发到全局 agent event bus。

关键代码（节选）：

```12:73:src/agents/pi-embedded-subscribe.handlers.lifecycle.ts
export function handleAgentStart(ctx: EmbeddedPiSubscribeContext) {
  emitAgentEvent({ runId: ctx.params.runId, stream: "lifecycle", data: { phase: "start", startedAt: Date.now() } });
}

export function handleAgentEnd(ctx: EmbeddedPiSubscribeContext) {
  if (isError) {
    emitAgentEvent({ runId: ctx.params.runId, stream: "lifecycle", data: { phase: "error", error: errorText, endedAt: Date.now() } });
  } else {
    emitAgentEvent({ runId: ctx.params.runId, stream: "lifecycle", data: { phase: "end", endedAt: Date.now() } });
  }
}
```

除 lifecycle 外，还会有 `assistant`（流式回复 delta）与 `tool`（工具执行 start/update/end）事件；这些由 subscribe 层其他 handlers 产生，并同样走 `emitAgentEvent`。

### 4.2 Gateway 如何把事件广播出去

Gateway 在 `src/gateway/server-chat.ts` 中构建 `createAgentEventHandler(...)`，接收 agent event bus 的事件并：

- 广播到 WebSocket（`broadcast("agent", ...)`）
- 转发到 session 订阅者（`nodeSendToSession(sessionKey, "agent", ...)`）
- 对 chat 流（`stream=assistant`）做缓冲与 delta/final 的节流与合并

关键点：tool 事件会根据 capability/verbose 设置决定广播对象（WS “tool-events” 订阅者与消息面是否输出 tool 详情是两回事）。

## 5. Gateway RPC：`agent.wait`（等待语义）

### 5.1 `agent.wait` 要解决什么

`agent` RPC 是异步触发；客户端需要一个可靠方式判断 run 是否结束：

- 成功结束：lifecycle `end`
- 失败结束：lifecycle `error`
- 超时：在指定 `timeoutMs` 内未看到终态

### 5.2 `agent.wait` 的实现要点

在 `src/gateway/server-methods/agent.ts` 里，`agent.wait` 会：

1. 解析 `runId/timeoutMs`（默认 30s）
2. 先尝试从 dedupe 里读取终态快照（避免重复等待）
3. 并行等待两种信号，谁先到用谁：
   - **lifecycle 监听**：`waitForAgentJob(...)`（监听 `emitAgentEvent` 的 lifecycle end/error）
   - **dedupe 终态**：`waitForTerminalGatewayDedupe(...)`
4. 返回 `{ status, startedAt, endedAt, error? }` 或 timeout

相关入口见：

- `src/gateway/server-methods/agent.ts`：`"agent.wait": ...`
- `src/gateway/server-methods/agent-job.ts`：`waitForAgentJob(...)`

### 5.3 `waitForAgentJob(...)` 的机制

`waitForAgentJob` 会确保有一个全局 listener 订阅 agent event bus，只关心 lifecycle 事件：

- `phase=start`：记录 startedAt，清理旧 cache
- `phase=end/error`：生成 snapshot 并缓存
- 对 `error` 有一个 grace period（避免“错误后立刻重试又 start”时 wait 提前返回旧错误）

关键代码（节选）：

```79:137:src/gateway/server-methods/agent-job.ts
onAgentEvent((evt) => {
  if (evt.stream !== "lifecycle") return;
  const phase = evt.data?.phase;
  if (phase === "start") { agentRunStarts.set(evt.runId, startedAt ?? Date.now()); agentRunCache.delete(evt.runId); return; }
  if (phase !== "end" && phase !== "error") return;
  const snapshot = createSnapshotFromLifecycleEvent({ runId: evt.runId, phase, data: evt.data });
  if (phase === "error") { schedulePendingAgentRunError(snapshot); return; }
  recordAgentRunSnapshot(snapshot);
});
```

## 6. 设计要点（可迁移到 MW4Agent）

### 6.1 关键数据：`runId` + `idempotencyKey`

- `runId`：用于事件流关联、wait、日志、UI
- `idempotencyKey`：用于 dedupe，避免重试导致重复执行

### 6.2 关键语义：事件驱动 + 等待补偿

OpenClaw 不是只靠 “RPC 返回结果”，而是：

- 事件流实时推送（assistant/tool/lifecycle）
- `agent.wait` 作为补偿机制（只关心终态）
- dedupe snapshot 作为缓存（快速返回终态，兼容 expectFinal）

### 6.3 关键安全点：显式 `senderIsOwner`

Ingress 调用强制传 `senderIsOwner`，保证 owner-only 工具策略不会因为“未知 owner 状态”而被误放行或误拒绝。

## 7. 关键文件索引（OpenClaw）

- `src/gateway/server-methods/agent.ts`：`agent` / `agent.wait`
- `src/commands/agent.ts`：`agentCommand` / `agentCommandFromIngress` → `runEmbeddedPiAgent`
- `src/agents/pi-embedded-runner/run.ts`：`runEmbeddedPiAgent`（队列、attempt loop、结果）
- `src/agents/pi-embedded-runner/run/attempt.ts`：订阅 `subscribeEmbeddedPiSession(... onAgentEvent ...)`
- `src/agents/pi-embedded-subscribe.handlers.lifecycle.ts`：`emitAgentEvent` lifecycle
- `src/gateway/server-methods/agent-job.ts`：`waitForAgentJob`（lifecycle 等待与缓存）
- `src/gateway/server-chat.ts`：`createAgentEventHandler`（广播/节流/chat delta/final）

