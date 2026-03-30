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
- **拖拽式画布**：**Phase D** 已提供 XYFlow 可视化编辑，并与 JSON 双向同步；后端仍由 `normalize_dag_dict` 校验。
- 不强制 **自动 LLM 分解** 生成 DAG（可作为后续选项）；首版允许用户/前端显式提交图。
- 不引入 Shannon 级 **反思/多模式策略链**；DAG 仅解决 **依赖与并行**。

### 1.3 稳定图规范（为拖拽 UI 预留）

- 逻辑依赖仍以 **`dependsOn`** 为真源；**`position: { x, y }` 仅布局**，不参与调度。
- 规范化入口：`mw4agent/gateway/dag_spec.py` 的 `normalize_dag_dict`（Web/CLI/RPC 共用，避免画布与后端各写一套规则）。
- 持久化：`orch.json` 中 `dagSpec` **不写**派生字段 `topologicalOrder`（磁盘精简）；运行时再归一化。

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

### Phase A — 后端核心（**已实现**）

1. **校验与归一化**：`mw4agent/gateway/dag_spec.normalize_dag_dict`（id 唯一、`dependsOn` 合法、无环、并行度裁剪、`position` 透传）。
2. **`Orchestrator`**：`strategy=dag` 时 `create(..., dag=...)`；`send` 走 `_task_dag`（就绪集 + `asyncio.Semaphore` 并行；fail-fast）。
3. **状态字段**：`dagSpec`、`dagProgress`、`dagParallelism`、`dagNodeSessions`；`OrchMessage.nodeId`。
4. **RPC**：`orchestrate.create` / `orchestrate.run` 支持 `dag`；`orchestrate.get` 返回 `dagSpec` / `dagProgress` / `orchSchemaVersion` 等。
5. **单测**：`tests/test_dag_spec.py`、`tests/test_orchestrator_dag.py`。

### Phase B — Web 编排最小可用（**部分已实现**）

1. **`gateway.ts`**：`OrchestrateDagSpec`、`orchestrate.create/run` 传 `dag`，`orchestrate.get` 消费 DAG 字段。
2. **`OrchestratePanel`**：策略中选 **DAG**，JSON 编辑默认链示例；侧栏展示 `dagProgress`；消息元数据展示 `nodeId`。
3. **i18n**：中英 DAG 文案。

### Phase C — 可选增强

1. **LLM 分解**：自然语言 → 草稿 `dagSpec`，需用户确认后 `create`。
2. **节点重试**：`retryPolicy` 每节点 1～2 次。
3. **只读缩略图**：仅展示依赖边、不可编辑（过渡 UI）。

### Phase D — Web **拖拽式** DAG 编辑器（**已落地**）

**目标**：在编排页用画布 **增删节点、拖线建依赖**，导出与 Phase A 相同的 JSON 再调用 `orchestrate.create`。

**实现要点**：

- [@xyflow/react](https://reactflow.dev/)：`OrchestrateDagCanvas.tsx`，自定义节点（`agentId` 下拉、`title` 输入）、`dependsOn` ↔ 边（上游 → 下游）。
- **转换层**：`mw4agent/desktop/lib/orchestrateDagFlow.ts`（`specToFlow` / `flowToSpec`、`specHasCycle`）。
- **`OrchestratePanel`**：DAG 策略下 **可视化 / JSON** 切换；JSON 合法时 `key` 重挂载画布；创建前环检测。
- **布局**：拖拽存 `position`；未做自动 dagre（可后续加）。

**依赖 Phase A/B**：必须先稳定 **schema** 与 **get 回显**（当前已具备），画布只做 **可视化编辑层**。

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
| A | 校验 + `_task_dag` + RPC + pytest | **已落地** |
| B | 类型 + JSON 创建 + 进度展示 | **已落地**；菱形并行 e2e 可补 |
| C | LLM 分解 / 重试 / 缩略图 | 按需 |
| D | XYFlow 画布、dependsOn 同步、布局 | **已落地** |

以上为实施计划基线；**拖拽编辑**以 Phase D 单独立项，避免与调度语义耦合。
