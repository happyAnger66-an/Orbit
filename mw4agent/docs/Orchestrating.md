# AG2（AgentOS）多 Agent 编排系统解析（面向 mw4agent）

本文基于你加入到 workspace 的 `ag2`（AG2/AutoGen v2 系）源码，梳理其 **多 agent 编排（orchestration）** 的核心抽象、调度流程与扩展点，并给出与 `mw4agent` 现有架构（Gateway + per-agent workspace/session）对接时的映射建议。

> 代码入口提示：AG2 的“编排”并不是一个单独的 Orchestrator 类，而是由 **Pattern（编排模式）+ GroupChat/GroupChatManager（运行时）+ TransitionTarget/Handoffs（跳转规则）+ GroupToolExecutor（工具执行与转移）** 共同组成。

---

## 核心目标与整体形态

AG2 的多 agent 编排主要解决：

- **多角色协作对话**：一轮轮选择“下一个说话者（speaker）”，让不同 agent 以不同职责连续发言。
- **可插拔的调度策略**：自动选择、手动选择、随机、轮询、或自定义函数。
- **可组合的跳转/收敛**：每个 agent 可以定义 after-work/handoffs，把控制权交给另一个 agent、交给群管理器、或终止。
- **工具调用在群聊中可控地执行**：把工具执行集中到一个“工具执行 agent”（`GroupToolExecutor`），并能影响后续转移（例如工具结果决定交给哪个 agent）。
- **嵌套编排（Nested group chat）**：可以把一段群聊封装成一个“包装 agent”，在外层对话中像函数/工具一样被触发，结束后再回到父 agent。

在实现上，它非常“对话驱动”：**每一轮是“广播上一条消息 → 选择下一 speaker → speaker 生成回复 → 进入下一轮”**。

---

## 核心抽象（你需要记住的 4 层）

### 1) `GroupChat`：群聊状态 + “如何选 speaker”的策略入口

`GroupChat` 保存：

- 参与者列表 `agents`
- 群聊消息 `messages`
- 最大轮次 `max_round`
- speaker 选择方式 `speaker_selection_method`
- 允许/禁止的 speaker 转移图（allowed/disallowed transitions）
- 选择 speaker 时使用的 prompt 模板（auto 模式）

最关键点：`speaker_selection_method` 不仅可以是 `"auto"|"manual"|"random"|"round_robin"`，也可以是一个 **Callable**。Pattern 系统正是利用这一点，把“编排逻辑”塞进一个函数。

---

### 2) `GroupChatManager`：执行引擎（round loop）

`GroupChatManager.run_chat()` 是典型的“群聊轮次推进”循环：

1. 把当前消息追加进群聊历史 `groupchat.append(message, speaker)`
2. **广播**给除了 speaker 之外的所有 agent（并可插入 inter-agent guardrails）
3. 检查终止条件（termination message）或 max rounds
4. 选择下一 speaker：`speaker = groupchat.select_speaker(speaker, self)`
5. 让 speaker 生成回复（或走 guardrails 生成替代回复）
6. speaker 把回复发送给 manager（`speaker.send(reply, self, ...)`），manager 取到新 message，进入下一轮

这套模型的一个重要性质：

- agent 在“收消息”时，收件人看到的 sender 永远是 `GroupChatManager`，但可以通过 `sender.last_speaker` 得到“真实发言者”。

---

### 3) `Pattern`：把“编排策略”编译成可运行的 GroupChat + Manager

`Pattern.prepare_group_chat(...)` 是编排的“编译阶段”。它做的事情包括：

- 准备 agent（包括包装 agent、临时 user agent 等）
- 创建 `GroupToolExecutor`（工具执行 agent）
- 创建一个 `group_transition` 函数（闭包，带有“首轮一定由 initial_agent 开始”的状态）
- 构造 `GroupChat(... speaker_selection_method=group_transition ...)`
- 构造 `GroupChatManager(...)`
- 设置 context variables、把 agent 与 manager 链接起来

也就是说：**Pattern 把“编排”最终落成一个函数 `group_transition(last_speaker, groupchat) -> Agent|str|None`，交给 GroupChat 的 speaker_selection_method。**

Pattern 的变体（Auto / RoundRobin / Random / Manual）本质是在 **handoffs/after_work 的默认策略** 上做封装（比如 AutoPattern 把 group_after_work 固定成 GroupManagerTarget）。

---

### 4) `TransitionTarget` + `handoffs/after_work`：跳转规则（编排真正的“路由表”）

AG2 用 `TransitionTarget` 表达“下一步去哪里”：

- `AgentTarget(...)`：去某个 agent
- `GroupManagerTarget(...)`：交给 group manager（通常需要 LLM 来“挑选下一 agent”）
- `TerminateTarget()`：终止
- 以及其他 target（随机、回到用户、停留、嵌套 chat wrapper 等）

核心思想是：

- **每个 agent 可以设置 after_work/handoffs**（上下文条件、LLM 条件、默认 after_work）
- **群级别也有一个 group_after_work**（兜底行为）
- “下一 speaker”由 `determine_next_agent(...)` 统一计算：
  - 先处理首轮 initial_agent
  - 再处理工具执行相关的特殊情况
  - 再评估 agent 的 after_works 条件
  - 再落到 group_after_work.resolve(...)

这使得“编排”既可以像 FSM（状态机）一样写死跳转，也可以引入 LLM 作为路由器（GroupManagerTarget）。

---

## 工具执行：为什么需要 `GroupToolExecutor`？

群聊里如果每个 agent 都直接执行工具，会带来：

- 不同 agent 工具集不一致导致路由困难
- 工具执行权限/日志/审计难统一
- 工具结果如何影响“下一步该谁说”难以结构化表达

因此 AG2 引入 `GroupToolExecutor`（一个特殊的 `ConversableAgent`），把群内工具执行集中化：

- 它会收集并注册所有 agents 的 tools/function_map
- 支持把 `context_variables` 参数改造为依赖注入（让 tool 读到群级 context）
- 能在工具调用/guardrails 时设置 “next target”，由 `determine_next_agent` 决定后续跳转

对 mw4agent 的启示：如果你要做“编排”，建议也把“工具执行”从“发言 agent”里剥离，变成 **统一的工具执行节点**（更容易做权限与审计，也更像一个 AgentOS runtime）。

---

## 嵌套群聊（Nested chat / GroupChatTarget wrapper）

AG2 支持把一个 group chat 作为“目标”嵌入另一个对话流，但 `GroupChatTarget` 本身不能直接 resolve（因为 speaker selection 期望是一个 agent）。

所以它提供 `create_wrapper_agent(...)`：

- 生成一个包装 `ConversableAgent`
- 该 agent 的 reply_func 会在触发时调用 `initiate_group_chat(...)` 跑一段内层群聊
- 内层完成后，把 summary 作为 wrapper agent 的回复
- wrapper agent 的 after_work 会回到 parent agent（`AgentTarget(parent_agent)`）

对 mw4agent 的启示：如果你未来要把“多 agent 编排”与“单 agent 运行（Gateway agent RPC）”兼容，**“把一段编排当成一个可调用的 agent/工具”** 是很实用的桥接方式。

---

## 运行入口与事件流（同步 / 异步 / 流式）

`multi_agent_chat.py` 提供了面向用户的运行 API：

- `initiate_group_chat(...)`：同步直接跑完，返回 `ChatResult`
- `a_initiate_group_chat(...)`：异步版本
- `run_group_chat(...)`：后台线程运行，返回可迭代的 `RunResponse`
- `run_group_chat_iter(...)` / async iter：逐事件迭代（便于 UI 流式展示）

这些入口都共享同一个核心：**Pattern.prepare_group_chat → manager.resume/启动 → last_agent.initiate_chat(manager, ...) → manager.run_chat 循环**。

---

## 与 mw4agent 的映射建议（如果要把 AG2 编排落到 mw4agent）

mw4agent 当前能力（你已实现并验证过）：

- 每个 agent 独立 `workspace_dir`、`sessions.json`、`agent.json(llm)`（见 `docs/architecture/multi_agents.md`）
- Gateway `POST /rpc` 的 `method=="agent"`：按 `agentId` 路由 workspace/session，并调用 `AgentRunner.run(AgentRunParams...)`

要对接 AG2 风格编排，你可以把 AG2 的概念映射为：

- **AG2 的 `ConversableAgent`** ↔ **mw4agent 的 agentId（以及其 agent.json/LLM/workspace）**
- **AG2 的 GroupChatManager** ↔ **mw4agent 的“编排器服务”（可以先做在 Gateway 内）**
- **AG2 的一次 speaker 回合** ↔ **一次 `Gateway.method="agent"` 调用**
- **AG2 的 groupchat.messages** ↔ **mw4agent 的 session transcript（per-agent 或专门的 orchestrator session）**
- **AG2 的 GroupToolExecutor** ↔ **mw4agent 现有 tool 执行体系中的“统一工具执行器”（可通过权限策略/工具白名单实现）**

### 一个最小可行的 mw4agent 编排接口（建议）

新增 Gateway RPC，例如：

- `orchestrate.run`：
  - 输入：`orchestrationId/pattern`、`participants=[agentId...]`、`message`、`sessionKey`
  - 输出：流式事件（每轮谁发言、工具调用、最终总结）

内部逻辑：

1. 维护一个“编排 session”（而不是复用某个单 agent 的 session）
2. 每轮调用 `method="agent"` 派活到某个 agentId（把编排上下文注入 extraSystemPrompt 或 context 文件）
3. 根据“调度策略”（round-robin / auto router / graph）决定下一 agent
4. 终止条件：max rounds / tool result / 模式定义等

这样你能在不引入 AG2 全量运行时的情况下，复用 mw4agent 现有 agent 执行与工具体系，先实现“编排层”。

---

## 关键源码索引（AG2）

- 运行入口（同步/异步/迭代事件）：`ag2/autogen/agentchat/group/multi_agent_chat.py`
- 核心数据结构与 speaker selection：`ag2/autogen/agentchat/groupchat.py`（`GroupChat`, `GroupChatManager.run_chat`）
- Pattern “编译阶段”：`ag2/autogen/agentchat/group/patterns/pattern.py`
- group_transition / determine_next_agent / manager 创建：`ag2/autogen/agentchat/group/group_utils.py`
- 工具执行器：`ag2/autogen/agentchat/group/group_tool_executor.py`
- 嵌套群聊 wrapper：`ag2/autogen/agentchat/group/targets/group_chat_target.py`

---

## 附：一句话总结 AG2 编排的实现原理

AG2 的多 agent 编排 = **把“下一 speaker 的选择”抽象成 `speaker_selection_method`（可调用函数）**，并把“路由规则”抽象成 **TransitionTarget/handoffs/after_work**；再由 `GroupChatManager` 的 round loop 持续执行“广播 → 选人 → 发言/工具 → 终止”。

---

## mw4agent Orchestrator 设计草案（追加）

本节给出一个可逐步落地的 mw4agent 编排器设计，目标是在**最大复用现有能力**（Gateway `agent` RPC、per-agent workspace/session、WS 事件流、工具执行/权限策略）的前提下，引入“多 agent 调度层”。

### 目标

- **多 agent 协作编排**：支持 Round-robin、随机、规则图、以及“LLM 选人（router）”等调度策略。
- **可流式观测**：前端可看到每轮“选了谁”“派了什么活”“输出/工具调用摘要”“什么时候结束/为什么结束”。
- **幂等与可恢复**：在网络抖动/前端刷新/网关重启后，能用 `orchestrate.wait` / `orchestrate.get` 恢复状态。
- **不破坏现有单 agent 运行**：依然保留 `method == "agent"` 的直接派活方式。

非目标（第一阶段不做）：

- 复杂 DAG/分叉并行、投票/共识、跨运行的强一致分布式调度。
- 将 AG2 全量运行时嵌入 mw4agent（可以后续做成可选 backend）。

---

## 1. 核心概念与数据模型

### 1.1 Orchestration（编排会话）

一场编排运行对应一个 `orchId`，它有自己的“全局会话”：

- `orchId`: string（uuid）
- `sessionKey`: string（对用户暴露，用来复用/续跑）
- `participants`: `[{ agentId, role?, weight?, tags? }]`
- `strategy`: oneof
  - `round_robin`
  - `random`
  - `graph`（允许/禁止转移）
  - `router_llm`（LLM 根据上下文选下一 agent）
- `maxRounds`: int
- `status`: `accepted|running|completed|error|aborted|timeout`
- `createdAt/updatedAt`
- `cursor`: 当前轮次、当前 speaker、最后一次输出摘要等

### 1.2 Step（编排步）

一轮编排包含若干 step（最小粒度以“一次派活到某个 agentId 的 Gateway `agent` 调用”为主）：

- `stepId`: string（uuid）
- `round`: int
- `agentId`: string
- `input`: string（本轮派活内容：来自用户、或来自上轮输出/工具结果）
- `runId`: string（复用现有 Gateway `runId`）
- `status`: `accepted|running|done|error`
- `summary`: string（可选：该 agent 产出的摘要/关键结论）
- `ts`

> 关键点：`step.runId` 直接复用 Gateway 现有运行记录与 `agent.wait` 机制，避免再造一套执行/超时体系。

---

## 2. 与现有 mw4agent 运行接口的对接

### 2.1 复用 `method == "agent"` 作为“派活原语”

Orchestrator 不直接执行 LLM/tool，而是每步调用一次 Gateway 的 `agent` RPC：

- 输入：`{ message, agentId, sessionKey, sessionId?, idempotencyKey, extraSystemPrompt?, reasoningLevel?, ... }`
- 输出：`{ runId, status=accepted, sessionId, ... }`

然后用 `agent.wait(runId)` 或 WS 事件跟踪该步完成。

### 2.2 会话隔离与记录

建议两套会话并存：

- **Per-agent session**：保持现状（每个 agent 自己的 sessions/转录）。好处是 agent 的短期记忆自然隔离。
- **Orchestrator session**：新增（用于记录编排的“全局对话”与调度决策）。

实现选择：

- 简单起步：Orchestrator session 存到 `~/.mw4agent/orchestrations/<orchId>/orch.json + transcript.jsonl`
- 或复用现有 session/transcript 结构：引入一个虚拟 agentId（如 `_orch`）的 session store

---

## 3. RPC 设计（建议）

所有接口都走现有 `POST /rpc`。

### 3.1 创建/启动

`orchestrate.run`

输入（示例）：

- `sessionKey`: string（默认 `"main"`）
- `message`: string（用户发起任务）
- `participants`: string[]（agentId 列表）
- `strategy`: `"round_robin" | "random" | "graph" | "router_llm"`
- `maxRounds`: number（默认 8~20）
- `idempotencyKey`: string（必填，确保重复点击不重复创建）
- `router`: 可选（当 strategy=router_llm 时）
  - `provider/model/base_url/api_key/thinking_level`（可复用现有 LLM 配置解析逻辑）
  - `promptTemplate`（可选）

输出：

- `orchId`
- `status=accepted`
- `acceptedAt`
- `firstStep`: 可选（立即创建第一步并返回其 `runId`）

### 3.2 等待/流式

`orchestrate.wait`

- 输入：`{ orchId, timeoutMs }`
- 输出：`{ status, done, currentRound, lastStep?, events? }`

更推荐走 WS：

- WS 事件类型：`orchestrator`
  - `phase=start|step_start|step_end|select_next|end|error`
  - `orchId, stepId, agentId, runId, round, payload`

### 3.3 查询/取消

- `orchestrate.get { orchId }`：返回编排状态、steps 列表（可分页）
- `orchestrate.abort { orchId }`：终止编排（尽力取消正在运行的 step；至少标记为 aborted）

---

## 4. 调度策略（可插拔）

将调度策略做成纯函数/类接口：

```text
select_next(ctx) -> agentId | None
```

其中 `ctx` 包含：

- participants + 历史 steps
- 最近一次输出（可选：拉取 agent 的 summary/最后消息）
- 工具结果摘要（若有）
- 终止信号（max rounds / user abort）

### 4.1 Round-robin

- 固定顺序循环
- 支持 `allow_repeat=false`（避免连续同一人）

### 4.2 Graph（允许/禁止转移）

- 用一个 adjacency 约束 `lastAgentId -> nextAgentId`
- 可用 mw4agent 的现有多 agent 文档里“允许/禁止转移”概念对齐 AG2

### 4.3 Router LLM（自动选人）

用一个“路由器 LLM”只做一件事：从候选列表里选下一 agentId。

实现建议：

- Prompt 只给：候选角色描述 + 最近 N 轮摘要 + 当前目标
- 输出严格约束为：`<agentId>`（可用 JSON schema/正则校验）
- 重试：0~2 次，仍失败则回退 round-robin

---

## 5. 上下文注入与隔离（关键设计点）

### 5.1 注入编排上下文到每个 agent

每次派活到 agent 时，可以使用 `extraSystemPrompt` 注入：

- 当前总目标
- 编排规则（你是第 X 个角色，你要输出什么格式）
- 上轮/全局摘要（避免把全部 transcript 塞进去）

后续如果要对齐 OpenClaw/AG2 的“文件式记忆”，也可以把 orchestrator 的摘要写入每个 agent workspace 下的某个文件（例如 `memory/orch_summary.md`），由 memory_tool 检索到。

### 5.2 不同 agent 的 workspace/session 仍保持隔离

Orchestrator 只是“派活层”，不应该把所有 agent 强行共享同一 workspace（除非用户明确要求）。

---

## 6. 最小落地路径（建议分两阶段）

### Phase A：串行编排（最快上线）

- Gateway 新增 `orchestrate.run/get/wait/abort`
- Orchestrator 内部串行调用 `agent` + `agent.wait`
- 只实现 `round_robin` + `random`
- 事件：用现有 WS broadcast 机制新增 `orchestrator` stream

### Phase B：LLM Router + 规则图

- 增加 `router_llm` 策略（复用 mw4agent LLM provider 解析）
- 增加 graph 约束
- 增加“失败回退策略”（router 输出非法时回退）

---

## 7. 与现有代码的落点建议（文件级）

（仅建议，不强制）

- Orchestrator 状态与执行：
  - `mw4agent/gateway/orchestrator.py`（新）
  - `mw4agent/gateway/state.py` 扩展（记录 orch runs）
- RPC 接口：
  - `mw4agent/gateway/server.py` 增加 `orchestrate.*` 分支
- 持久化：
  - `mw4agent/config/paths.py` 增加 orchestrations 路径解析
  - 或复用 `agents/session/transcript.py` 的 JSONL 机制
- 前端：
  - `desktop/components/ChatPanel.tsx` 增加“编排模式”入口（后续）

