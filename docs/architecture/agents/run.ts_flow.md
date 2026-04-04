# OpenClaw `runEmbeddedPiAgent` 执行时机与执行流程分析

本文档基于 `openclaw/src/agents/pi-embedded-runner/run.ts` 中的：

- `export async function runEmbeddedPiAgent(params: RunEmbeddedPiAgentParams): Promise<EmbeddedPiRunResult>`

对其 **何时被调用（执行时机）** 和 **内部执行流程** 进行梳理，作为 Orbit 设计与实现的参考资料。

---

## 1. 执行时机：谁会调用 `runEmbeddedPiAgent`

在 OpenClaw 中，`runEmbeddedPiAgent` 是“嵌入式智能体执行”的统一入口，只要需要“跑一轮智能体 + 工具 + 会话上下文”的地方，最终都会落到这里，典型包括：

- **Gateway RPC `agent`**
  - Gateway 收到 `method: "agent"` 的 RPC 请求时，会组装 `RunEmbeddedPiAgentParams` 并调用 `runEmbeddedPiAgent`。
  - 用于前端/Web、第三方集成等发起一次“智能体执行”的核心路径。

- **CLI 命令 `openclaw agent ...`**
  - 从命令行主动触发一次 agent 执行（包含 prompt、会话、模型等），CLI 最终调度到 `runEmbeddedPiAgent`。

- **消息通道自动回复（Slack/Telegram/Discord 等）**
  - 通道的 `Monitor` 收到一条需要 Agent 处理的消息后，会根据消息和路由规则构造 `params`：
    - `sessionId/sessionKey`（会话）
    - `messageChannel/messageProvider`（入口通道）
    - `prompt`（用户消息 + 系统 prompt）
  - 然后调用 `runEmbeddedPiAgent` 完成这一轮 LLM/工具执行。

- **定时任务 / Hook / 其他内部触发**
  - 如 cron 任务、webhook 回调、内部控制命令等，只要要“在当前配置下跑一次 Agent”，最终都会调用该函数。

> 可以理解为：**OpenClaw 的所有“智能体执行”落点，都会统一通过 `runEmbeddedPiAgent` 来完成实际 LLM+工具调用与上下文处理。**

---

## 2. 并发与排队模型：Session Lane + Global Lane

函数开头关键几行：

```ts
const sessionLane = resolveSessionLane(params.sessionKey?.trim() || params.sessionId);
const globalLane = resolveGlobalLane(params.lane);
const enqueueGlobal =
  params.enqueue ?? ((task, opts) => enqueueCommandInLane(globalLane, task, opts));
const enqueueSession =
  params.enqueue ?? ((task, opts) => enqueueCommandInLane(sessionLane, task, opts));
```

- **sessionLane**
  - 由 `sessionKey` 或 `sessionId` 推导出的“会话队列键”。
  - 主要保证：**同一个会话上的多次调用按顺序执行**，避免并发修改同一会话历史导致上下文错乱。

- **globalLane**
  - 全局或按 lane 维度的队列键。
  - 用于做更粗粒度的资源/并发控制，如整体限流或某类任务串行化。

封装后的调用方式：

```ts
return enqueueSession(() =>
  enqueueGlobal(async () => {
    // 真正的 LLM + 工具执行逻辑
  }),
);
```

执行顺序：

1. 外层：`enqueueSession` 按 session 将任务串行队列化；
2. 内层：在单个 session 任务内部，再通过 `enqueueGlobal` 进入 global 队列；
3. 最终：在 `enqueueGlobal(async () => { ... })` 的异步函数体中完成本次 run。

> 结果：**同一个 session 内严格有序**，并且 **可以再叠加全局级别的队列/限流策略**，从而保护整体网关和模型调用的稳定性。

---

## 3. 执行前准备：工作区、模型、上下文窗口、鉴权与 Hook

进入 `enqueueGlobal(async () => { ... })` 后，函数会先做一系列前置准备。

### 3.1 工作区解析与日志安全

```ts
const workspaceResolution = resolveRunWorkspaceDir({
  workspaceDir: params.workspaceDir,
  sessionKey: params.sessionKey,
  agentId: params.agentId,
  config: params.config,
});
const resolvedWorkspace = workspaceResolution.workspaceDir;
const redactedSessionId = redactRunIdentifier(params.sessionId);
const redactedSessionKey = redactRunIdentifier(params.sessionKey);
const redactedWorkspace = redactRunIdentifier(resolvedWorkspace);
if (workspaceResolution.usedFallback) {
  log.warn(`[workspace-fallback] caller=runEmbeddedPiAgent ...`);
}
const prevCwd = process.cwd();
```

- 基于 `workspaceDir/agentId/sessionKey/config` 解析本次运行使用的 **工作目录**：
  - 存放会话文件、日志、诊断信息等。
- 对 `sessionId/sessionKey/workspaceDir` 做脱敏（redact），避免日志里直接泄露敏感路径/ID。
- 使用 `process.cwd()` 保存原工作目录，后续会切换到 `resolvedWorkspace`，在 `finally` 中再切回。

### 3.2 provider/model 初始化与 fallback 配置

```ts
let provider = (params.provider ?? DEFAULT_PROVIDER).trim() || DEFAULT_PROVIDER;
let modelId = (params.model ?? DEFAULT_MODEL).trim() || DEFAULT_MODEL;
const agentDir = params.agentDir ?? resolveOpenClawAgentDir();
const fallbackConfigured = hasConfiguredModelFallbacks({ cfg: params.config, ... });
await ensureOpenClawModelsJson(params.config, agentDir);
```

- 初始化本次 run 打算使用的 **provider** 与 **modelId**（例如 `openai/gpt-4o-mini`）。
- 检测配置中是否对当前 agent/session 配置了 **模型 fallback 策略**（多模型、多账号冗余）。
- 确认 `openclaw-models.json` 已存在，作为模型/提供商能力说明的注册中心。

### 3.3 Hook：在模型解析前允许插件动态改写

```ts
const hookRunner = getGlobalHookRunner();
const hookCtx = {
  agentId: workspaceResolution.agentId,
  sessionKey: params.sessionKey,
  sessionId: params.sessionId,
  workspaceDir: resolvedWorkspace,
  messageProvider: params.messageProvider ?? undefined,
  trigger: params.trigger,
  channelId: params.messageChannel ?? params.messageProvider ?? undefined,
};

if (hookRunner?.hasHooks("before_model_resolve")) {
  modelResolveOverride = await hookRunner.runBeforeModelResolve({ prompt: params.prompt }, hookCtx);
}
if (hookRunner?.hasHooks("before_agent_start")) {
  legacyBeforeAgentStartResult = await hookRunner.runBeforeAgentStart({ prompt: params.prompt }, hookCtx);
  // 合并老 hook 的 provider/model 覆盖结果
}
if (modelResolveOverride?.providerOverride) provider = modelResolveOverride.providerOverride;
if (modelResolveOverride?.modelOverride) modelId = modelResolveOverride.modelOverride;
```

- `before_model_resolve`：插件可以根据 prompt / channel / trigger 等信息**动态改路由**到不同 provider/model。
- `before_agent_start`：兼容旧的 hook，输出也会被合并进入 `modelResolveOverride`。
- 通过这种机制，OpenClaw 可以实现：
  - 某些频道默认走自托管模型
  - 某些触发类型（cron/系统消息）走便宜模型
  - A/B 测试不同模型组合等。

### 3.4 模型解析与上下文窗口防护

```ts
const { model, error, authStorage, modelRegistry } = resolveModel(provider, modelId, agentDir, params.config);
if (!model) {
  throw new FailoverError(error ?? `Unknown model: ${provider}/${modelId}`, { ... });
}

const ctxInfo = resolveContextWindowInfo({ cfg: params.config, provider, modelId, ... });
const ctxGuard = evaluateContextWindowGuard({ info: ctxInfo, ... });
if (ctxGuard.shouldWarn) log.warn("low context window...");
if (ctxGuard.shouldBlock) {
  throw new FailoverError("Model context window too small ...", { ... });
}
```

- `resolveModel`：
  - 校验是否存在对应 provider/model；若不存在，抛 `FailoverError("model_not_found")`。
  - 返回模型的上下文窗口大小等元信息。
- 上下文窗口防护：
  - 若模型 context 太小（低于阈值），会提前 block，避免后续频繁遇到 overflow 错误。

### 3.5 鉴权 Profile 选择与 Copilot token 管理

接下来的大段逻辑围绕：

- 从 auth store 中解析当前 provider 可用的 **鉴权 profile 列表**；
- 支持用户锁定 profile（`authProfileIdSource === "user"`）；
- 通过 `resolveAuthProfileOrder` 决定尝试顺序；
- 定义：
  - `advanceAuthProfile`：在 quota/rate limit/auth 错误时切换下一个 profile；
  - `maybeMarkAuthProfileFailure`：记录 profile 失败原因并做冷却；
  - `throwAuthProfileFailover`：在全部 profile 不可用时抛 FailoverError。

同时，对于 `github-copilot` provider：

- 维护 `CopilotTokenState`，包括 githubToken、copilot token 的过期时间、refresh 计时器；
- 通过 `scheduleCopilotRefresh` 和 `refreshCopilotToken` 在运行过程中自动刷新 token；
- 在 `finally` 中调用 `stopCopilotRefreshTimer` 清理计时器。

---

## 4. 主运行循环：多次 attempt + 压缩 + 截断 + failover

完成上述准备后，`runEmbeddedPiAgent` 进入核心的 **attempt 重试循环**。整体模式可以概括为：

> 「一次 run 可以包含多次 attempt；每次 attempt 调用 `runEmbeddedAttempt` 做一次完整的 LLM+工具执行；根据错误类型决定是否重试 / 压缩会话 / 截断工具结果 / 切换账号 / fallback 模型。」

### 4.1 控制变量与 usage 累积

函数定义了多个控制变量：

- `MAX_RUN_LOOP_ITERATIONS`：单次 run 允许的最大 attempt 次数（与 profile 数量相关）。
- `overflowCompactionAttempts`：上下文溢出的自动压缩尝试次数。
- `toolResultTruncationAttempted`：是否已经尝试过截断过大的工具结果。
- `usageAccumulator`、`lastRunPromptUsage`、`lastTurnTotal` 等：用于统计 token 使用情况，最终写入 `agentMeta`。

同时维护：

- `attemptedThinking`：记录已尝试过的 thinking level，后续根据错误信息决定是否切换。
- `lastProfileId`：记录当前使用的鉴权 profile，以便在错误后标记/冷却。

### 4.2 调用 `runEmbeddedAttempt`

在每轮循环中：

```ts
const prompt =
  provider === "anthropic" ? scrubAnthropicRefusalMagic(params.prompt) : params.prompt;

const attempt = await runEmbeddedAttempt({
  sessionId: params.sessionId,
  sessionKey: params.sessionKey,
  ...
  prompt,
  images: params.images,
  disableTools: params.disableTools,
  provider,
  modelId,
  model,
  authStorage,
  modelRegistry,
  ...
  extraSystemPrompt: params.extraSystemPrompt,
  ...
});
```

- `runEmbeddedAttempt` 内部负责：
  - 构建本次调用的 prompt 与 messages；
  - 与具体 LLM 提供方通信；
  - 处理工具调用循环（tool calls → 执行 → 再回到 LLM）；
  - 收集：
    - `assistantTexts`
    - `toolMetas`
    - `lastAssistant`（含 provider/model/usage/errorMessage 等）
    - `systemPromptReport`
    - `didSendViaMessagingTool` 等边界信息。

### 4.3 上下文溢出（Context Overflow）处理

根据 `promptError` 和 `assistantError` 文本判断是否为上下文溢出：

- 如果是 overflow：
  1. 尝试自动 compaction（`compactEmbeddedPiSessionDirect`）：
     - 压缩会话历史，减少 token 数。
  2. 如果 compaction 已失败或达到最大 compaction 次数：
     - 尝试 **截断超大的工具结果**（`truncateOversizedToolResultsInSession`）。
  3. 若依然无法恢复：
     - 直接返回一个带“Prompt 太大 / 请 /reset 或使用大 context 模型”提示的错误 payload。

这个步骤相当于 OpenClaw 在 **session 级别自动“瘦身”** 会话历史，以避免 context window 被撑爆。

### 4.4 提交阶段错误（promptError）的处理

如果在提交 prompt 给 LLM 之前就出错且不属于 overflow：

- 优先尝试 Copilot token 刷新（针对 `github-copilot`）；
- 检测是否为 image size 错误，返回包含 maxMB 等信息的友好提示；
- 根据错误文本分类 failover reason：
  - 按需标记当前 profile 失败；
  - 调用 `advanceAuthProfile()` 切换下一个账号；
  - 若配置了 model fallback，则抛 `FailoverError` 交由上层做 provider/model 级别的切换；
  - 若没有 fallback 且无法恢复，则重新抛出原始 error。

### 4.5 thinking level 回退

根据模型返回的错误信息，使用 `pickFallbackThinkingLevel(...)` 挑选一个更保守的 thinking level（例如从 `high` 降到 `off`），并重试当前 provider/model/profile。

### 4.6 LLM 响应阶段错误处理（auth / rateLimit / billing / timeout / failover）

当 `runEmbeddedAttempt` 成功返回但 `lastAssistant` 表示错误时，逻辑会：

- 识别错误类型：
  - Authorization 错误
  - Rate limit
  - Billing 错误
  - Failover 错误（模型/网络层）
  - Timeout（含 compaction 前后不同场景）
- 针对不同错误：
  - 对 profile 做 mark failure / cooldown；
  - 再次调用 `advanceAuthProfile()` 切换账号；
  - 若有 fallback 配置，则构造 `FailoverError`，上送给上层进行 provider/model 级别的 fallback。

> 这部分逻辑是 OpenClaw **高可用与多账号容错** 能力的关键所在。

### 4.7 成功路径：构造 payloads + meta 并返回

当没有触发上述需要重试或 failover 的条件时：

- 使用 `mergeUsageIntoAccumulator` 等函数更新 usage 统计；
- 构建 `EmbeddedPiAgentMeta`：

```ts
const agentMeta: EmbeddedPiAgentMeta = {
  sessionId: sessionIdUsed,
  provider: lastAssistant?.provider ?? provider,
  model: lastAssistant?.model ?? model.id,
  usage,
  lastCallUsage,
  promptTokens,
  compactionCount: autoCompactionCount > 0 ? autoCompactionCount : undefined,
};
```

- 调用 `buildEmbeddedRunPayloads(...)` 生成最终的 payloads：
  - 汇总 assistant 文本、工具调用结果、工具错误等；
  - 处理是否通过 messaging tool 已经发送过消息；
  - 处理 client tool calls（OpenResponses hosted tools）的 `pendingToolCalls`。

- 特殊处理：
  - timeout 但 payload 为空时，返回显式的 timeout 文案（避免“静默丢失”该轮请求）。

最终 `runEmbeddedPiAgent` 返回：

- `payloads`：给上层（Gateway/CLI/Channel）的直接输出；
- `meta`：包含 usage、agentMeta、systemPromptReport、aborted 状态、pendingToolCalls 等；
- 若有 side-effect 行为（发送消息、添加 cron 等），也会在结果中带出相应字段。

---

## 5. 总结：`runEmbeddedPiAgent` 的角色与特点

- **角色**
  - 是 OpenClaw 智能体执行系统的“心脏”：
    - 上层的 RPC、CLI、Channel、Hooks 统一走这个入口；
    - 对下对接 `runEmbeddedAttempt` 与各类 provider/模型/工具。

- **并发控制**
  - 通过 session lane + global lane 双层队列模型，实现：
    - 会话内串行；
    - 全局或 lane 级限流。

- **前置决策**
  - 工作目录/会话文件组织；
  - provider/model 选择与 hook-based 改写；
  - 上下文窗口 guard；
  - 鉴权 profile 选择与 Copilot token 管理。

- **鲁棒性**
  - 通过多层 failover：
    - 上下文溢出自动压缩与工具结果截断；
    - 多账号 profile 轮询与冷却；
    - provider/model fallback；
    - thinking level 回退；
    - 各类错误（image size、role ordering、timeout 等）的友好文案。

对于 Orbit 而言，可以将 `runEmbeddedPiAgent` 看作高阶版本的 `AgentRunner.run`：

- 当前 Orbit 已有：
  - runId/session 串行化（`CommandQueue` + `SessionManager`）
  - LLM backend 抽象（`orbit.llm.backends.generate_reply`）
  - 事件流（`StreamEvent` + `EventStream`）
- 未来如果要增强高可用和多账号/多模型容错，可以逐步引入：
  - provider/model 解析与 fallback 策略；
  - 多 profile 鉴权与 failover；
  - 自动 session compaction / tool result 截断；
  - 更丰富的 meta 和 usage 统计。 

