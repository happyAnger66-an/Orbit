# mw4agent DAG 编排实施计划

本文在现有 **Gateway `Orchestrator`**（`mw4agent/gateway/orchestrator.py`：持久化 `OrchState`、后台任务里按轮次调用 `AgentRunner`）基础上，规划引入 **有向无环图（DAG）** 编排能力，并与桌面 `OrchestratePanel`、RPC 对齐。

---

## 1. 目标与非目标

### 1.1 目标

- 单次用户触发（`orchestrate.send`）可描述 **多节点、多依赖** 的执行图：节点映射到已有 `agentId`，边表示 **数据/语义依赖**（上游输出进入下游上下文）。
- **保证无环**；支持 **按层并行**（同一就绪层内可多 agent 同时 `run`）或 **整图严格串行**（便于调试）。
- 执行过程写入现有 `orch.json`（或可演进 schema），UI 可展示 **节点级状态与产物摘要**。
- 与现网一致：每节点仍走 `AgentRunParams` + 每 agent 独立 `session_id`（沿用 `agentSessions` 或按节点扩展），`session_key` 建议保持 `orch:{orchId}` 或子键区分便于排查。

### 1.2 非目标（首版可不做的）

- 不做完整 **Temporal 级** 工作流引擎（重放、长事务、持久化信号）。
- 不要求可视化 **拖拽式** DAG 编辑器（可用 JSON/YAML + 简易校验替代）。
- 不强制 **自动 LLM 分解** 生成 DAG（可作为 Phase 2 选项）；首版允许用户/前端显式提交图。
- 不引入 Shannon 级 **反思/多模式策略链**；DAG 仅解决 **依赖与并行**。

---

## 2. 现状简述

| 模块 | 行为 |
|------|------|
| `OrchState.strategy` | `round_robin` / `router_llm`，按 `currentRound` 线性选参与者 |
| `_task` 循环 | `last_text` 在轮次间传递；每轮对一个 `agent_id` 调用 `runner.run` |
| 持久化 | `~/.mw4agent/orchestrations/<orchId>/orch.json` |

DAG 需在 **调度层** 替换「for r in rounds」为 **就绪队列 + 拓扑推进**，并定义 **节点输入如何拼装**。

---

## 3. 概念模型

### 3.1 图定义（建议 JSON 与 `OrchState` 一同存储）

```jsonc
{
  "nodes": [
    { "id": "a", "agentId": "researcher", "title": "收集资料" },
    { "id": "b", "agentId": "writer", "title": "写摘要", "dependsOn": ["a"] },
    { "id": "c", "agentId": "reviewer", "title": "审阅", "dependsOn": ["b"] }
  ],
  "edges": [] 
}
```

- **dependsOn**：仅允许引用已存在节点 id；**禁止自环与环路**（提交时与运行前双重校验）。
- 可选字段（Phase 2）：`promptTemplate`、`toolsAllowlist`、节点级 `maxRounds`。

### 3.2 节点输入拼装

对每个节点 `n`：

- **基座**：用户本轮原始 `message`（编排总任务描述）。
- **上游上下文**：对所有 `d ∈ dependsOn(n)` 的已存储输出 `output[d]` 做有序拼接（如 Markdown 小节 `# {id}`），注入 `extra_system_prompt` 或单次 `message` 前缀，避免破坏现有 runner 契约。
- 首版建议：**系统侧追加固定格式说明**（「以下为上游节点输出，请基于它继续…」），减少 agent 误解。

### 3.3 并行策略

- `dagParallelism`: `1` 表示逐节点串行；`>1` 或 `0`（表示不限制）对 **当前就绪层** 内节点并发 `asyncio.gather` 调用 `runner.run`。
- 需限制全局并发（如信号量），避免压垮 LLM/本机。

### 3.4 与 `maxRounds` 的关系

- **round_robin 语义**：原 `maxRounds` 表示 assistant 轮数。
- **DAG 语义**建议：
  - 要么：**忽略** `maxRounds`，以「图中节点全覆盖」为结束条件；
  - 要么：`maxRounds` 表示 **单节点内部**仍由 runner 自有循环（通常一次 `run` 已是一轮工具链），编排层只调**每个节点一次**。  
  推荐首版：**每 DAG 节点单次 `runner.run`**，文档写明与轮询模式的区别。

---

## 4. 状态机扩展

在 `OrchState` 增加（字段名可再推敲）：

- `strategy`: 扩展为 `round_robin` | `router_llm` | **`dag`**
- `dagSpec`: 序列化后的图（nodes + 校验缓存）
- `dagProgress`: 如 `{ "nodeId": "pending|running|done|error", "outputPreview": "..." }`
- 可选 `dagParallelism: int`

消息列表 `messages`：

- 首版可继续追加 **assistant** 行，形如 `speaker: agentId` 且 `text` 带节点 id 前缀，或扩展 `OrchMessage` 增加 `nodeId?: string`（需同步 gateway.ts 与前端类型）。

---

## 5. 实施阶段

### Phase A — 后端核心（无 UI 大改）

1. **校验器**：`validate_dag(nodes) -> None | ValueError`（id 唯一、依赖存在、拓扑排序检测环）。
2. **`Orchestrator.create` / `send`**：
   - `strategy == dag` 时要求传入 `dagSpec`（或从 `create` 参数进入）。
   - `send` 启动 `_task_dag` 而非原循环。
3. **`_task_dag` 算法**：
   - 初始化入度表；`ready = [id | indegree==0]`；
   - while 未完成：对 `ready` 按并行策略 batch `runner.run`；写 `dagProgress`；将新就绪节点入队；
   - 任一节点的异常 → 整 orchestration `status=error`，或可配置「失败后跳过下游」（首版建议 **fail-fast**）。
4. **单测**：拓扑（链、菱形、并行扇入）、成环拒绝、fail-fast。
5. **RPC**：`orchestrate.create`、`orchestrate.get` payload 带上 `dagSpec` / `dagProgress`（见 `server.py` 现有 orchestrate 分支）。

### Phase B — 前端与 DX

1. **`gateway.ts` 类型**：`OrchState`/`create` 参数扩展。
2. **`OrchestratePanel`**：
   - 创建编排时可选 **DAG**：提供 JSON 文本框 **或** 固定「链式三步」模板生成器；
   - 列表/详情展示节点状态（颜色/标签）。
3. **i18n**：DAG 相关文案。

### Phase C — 可选增强

1. **LLM 分解**：用户只输入自然语言，调用轻量 `call_openai_chat` / 本地模板，生成 `dagSpec`（需人在 UI 确认再运行，避免乱图）。
2. **节点重试**：`retryPolicy` 每节点 1～2 次。
3. **与 Shannon 对齐的阅读材料**：内部参考 `mw4agent/docs/orchestrating_shannon.md` 的 DAG 分层思路，但不引入 Temporal。

---

## 6. API 草案

```text
orchestrate.create
  params:
    sessionKey, name, participants  // DAG 模式下 participants 可为 nodes 中 agent 并集供展示
    strategy: "dag"
    dag:
      nodes: [{ id, agentId, dependsOn?: string[], title?: string }]
      parallelism?: number   // 默认 4 或 8
```

`orchestrate.send`：行为与现有一致（触发一次完整 DAG 运行）；若需「同一张图多轮用户输入」Phase C 再议（每节点 message 是否覆盖全局 task）。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 并行压垮 provider | 默认并发上限 + 配置 `dagParallelism` |
| 输出传递过长导致超上下文 | 节点输出摘要（截断）+ 可选「只传 ref 到 session」 |
| 与 `round_robin` 语义混淆 | UI/文档明确 strategy；`maxRounds` 在 DAG 下隐藏或禁用 |
| 持久化 schema 演进 | `orch.json` 增加 `schemaVersion: 1` |

---

## 8. 验收标准（Phase A+B）

- 三节点链式 DAG：一次 `send`，顺序执行，最终 `status=idle`，`messages`/`dagProgress` 可查。
- 菱形 DAG：中间两层并行（在 `parallelism>1` 下），日志/结果顺序可预期（下游等待两上游均完成）。
- 成环 spec：`create` 或 `send` 前拒绝并返回明确错误。
- 前端可创建最小 DAG 并看到节点级完成态。

---

## 9. 参考代码位置

- 编排器：`mw4agent/gateway/orchestrator.py`
- RPC：`mw4agent/gateway/server.py`（`orchestrate.*`）
- 桌面：`mw4agent/desktop/components/OrchestratePanel.tsx`、`mw4agent/desktop/lib/gateway.ts`
- 类比阅读：`mw4agent/docs/orchestrating_shannon.md`（Shannon DAG 分层与分解，仅供设计对照）

---

## 10. 建议排期（粗估）

| 阶段 | 内容 | 人天（粗） |
|------|------|------------|
| A | 校验 + `_task_dag` + RPC 字段 + pytest | 2–4 |
| B | 类型 + 面板最小编辑 + 展示 | 2–3 |
| C | LLM 分解 / 重试等 | 按需 |

以上为实施计划基线，可在评审后固化到 issue/里程碑并按 Phase A 拆分 PR。
