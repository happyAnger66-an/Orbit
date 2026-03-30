# Shannon 智能体编排实现分析

本文基于姊妹仓库 **Shannon**（与 mw4agent 同级的 `Shannon/` 目录）中 **Go Orchestrator** 的源码与 `Shannon/docs/` 官方说明，梳理其「多工作流、DAG / ReAct / Research」等的**实现原理**。不涉及 Shannon 各语言服务的部署细节。

---

## 1. 设计总览

Shannon 将编排分为三层（官方架构图见 `Shannon/docs/multi-agent-workflow-architecture.md`）：

| 层级 | 职责 | 主要代码位置 |
|------|------|----------------|
| **Orchestrator Router** | 模板匹配、学习路由、任务分解、复杂度与策略选择、预算预检 | `go/orchestrator/internal/workflows/orchestrator_router.go` |
| **Strategy Workflows** | 按「认知策略」组织一整次任务：DAG、ReAct、Research、Exploratory、Scientific 等 | `go/orchestrator/internal/workflows/strategies/*.go` |
| **Patterns Library** | 可复用的推理与执行原语：ReAct 循环、反思、CoT、辩论、ToT；并行/顺序/依赖图执行 | `go/orchestrator/internal/workflows/patterns/` 及 `patterns/execution/` |

**运行时**：策略与路由均为 **Temporal Workflow**（可回放、可发暂停/取消/人工审批信号）；具体 LLM 调用、分解、工具执行等在 **Activity** 中完成，由 Python `llm-service` 等承接。

---

## 2. 统一入口：`OrchestratorWorkflow`

`OrchestratorWorkflow` 是薄入口：**不直接跑 Agent**，只做「规划一次 + 派生子工作流」（见 `orchestrator_router.go` 文件头注释）。

典型顺序（逻辑上，非严格线性）：

1. **控制面**：注册 `ControlSignalHandler`（暂停 / 恢复 / 取消）；可选异步生成会话标题。
2. **System 1 — 模板**：若请求带模板名且注册表命中，则 `ExecuteChildWorkflow(TemplateWorkflow, …)`；失败且开启 fallback 时回到 AI 分解路径（见 `template-workflows.md`）。
3. **学习路由**：在配置开启时，可调用 `recommendStrategy`；若返回已知策略，则 `routeStrategyWorkflow` 直接派发到对应 Strategy Workflow。
4. **早退路由**（避免重复分解、省 token）：
   - `skip_synthesis` → `SimpleTaskWorkflow`
   - `force_swarm` → `SwarmWorkflow`（自带 Lead 规划）
   - `force_research` → 可注入当前日期、可选 **HITL 研究计划审批**（生成计划 Activity → Signal 等待用户批准）→ `ResearchWorkflow`
   - `agent` / `role` 指定时可 **绕过 LLM 分解**，生成固定单步子任务计划
5. **主路径**：`DecomposeTaskActivity` 产出 `DecompositionResult`（子任务、依赖、复杂度、`CognitiveStrategy`、`ExecutionStrategy` 等），经预算预检后写入 `input.PreplannedDecomposition`，再交给子工作流避免二次分解。
6. **分发**：根据 `decomp.CognitiveStrategy`、`browser_use` 版本、`force_research` 等调用 `routeStrategyWorkflow`，映射到 `ReactWorkflow`、`ResearchWorkflow`、`DAGWorkflow`、`SimpleTaskWorkflow` 等。

**小结**：「DAG / ReAct / Research」在 Shannon 里**不是三个互斥产品**，而是：**默认大量多子任务走 DAGWorkflow**；分解阶段或上下文把认知策略标成 `react` / `research` 等时，则进入对应 Strategy，其内部再 **组合** `patterns` 包中的 ReAct、并行、反思等能力。

---

## 3. DAG 型编排：`DAGWorkflow`

文件：`strategies/dag.go`。

**原理要点**：

1. **输入计划**：优先使用上级传入的 `PreplannedDecomposition`；否则本工作流内再调 `DecomposeTaskActivity`。
2. **DAG 合法性**：多子任务时对 `Dependencies` 做**环检测**（`validation.ValidateDAGDependencies`），防止 Temporal 侧无限等待。
3. **简单任务短路**：若「零子任务」或「单子任务且不需要工具 + 复杂度低于阈值」等条件满足，则不走多 Agent，直接 `ExecuteSimpleTask` Activity。
4. **复杂执行**：按分解结果选择执行器：
   - 存在依赖边 → **`executeHybridPattern`**（依赖图 + 拓扑含义上的混合执行，见 `patterns/execution/hybrid.go`）
   - `ExecutionStrategy == sequential` → **顺序**传递结果
   - 否则 → **并行**（带并发上限等配置）
5. **收尾**：对多 Agent 结果做 **Synthesis**；配置允许时叠加 **Reflection**（反思）提升答案质量。

因此 Shannon 文档中的 **DAG** 有两层含义：  
- **编排层**：分解得到的子任务与 `Dependencies` 构成任务 DAG，由 `DAGWorkflow` + `execution` 包执行。  
- **模板层**：YAML 里 `type: dag` 的节点可在 `metadata.tasks` 内再嵌一套子任务依赖图（`template_workflow.go` 中 `executeDAGTemplateNode`）。

---

## 4. ReAct 型编排

### 4.1 Strategy：`ReactWorkflow`

文件：`strategies/react.go`。

- 配置超时、重试、`GetWorkflowConfig`（如 `ReactMaxIterations`、`ReactObservationWindow`）。
- 组装 `baseContext`（请求 Context + SessionCtx）。
- **记忆**：优先 `FetchHierarchicalMemory`，否则 `FetchSessionMemory`，写入 `baseContext["agent_memory"]`。
- **长历史**：在版本门控下可做 `CheckCompressionNeeded` + `CompressAndStoreContext`，控制上下文窗口。
- 后续调用 **`patterns.ReactLoop`**（及可选反思等，见同文件后半部分）完成 Reason-Act-Observe。

### 4.2 Pattern：`ReactLoop`

文件：`patterns/react.go`。

- **核心循环**：在 `MaxIterations` 内交替 **推理 → 行动（含工具）→ 观察**，维护 `thoughts` / `actions` / `observations` 与 `ObservationWindow`。
- **与研究模式联动**：若 `baseContext` 中 `force_research` 或 `research_strategy` 非空，循环内会走研究相关分支（提示与处理逻辑更偏检索—取证—综合）。

官方文档将 ReAct 定位为：**强依赖工具与环境反馈的迭代解题**（见 `multi-agent-workflow-architecture.md`）。

---

## 5. Research 型编排：`ResearchWorkflow`

文件：`strategies/research.go`（体量很大，除工作流主体外还包含引用实体过滤等工具函数）。

**定位**（源码注释）：组合 **ReAct、并行研究、反思** 等模式，做深研与信息综合。

**与 Router 的关系**：

- 全链路 **`force_research`**：在 `OrchestratorWorkflow` **早于**通用分解即切入 Research，避免.planner 与 Research 内部分解重复耗 token；支持 **研究计划人工审核**（Signal + 超时）。
- 分解结果中 `CognitiveStrategy == research` 或通过 `routeStrategyWorkflow` 映射到 `research` 时，也会进入同一 `ResearchWorkflow`。

**与其它 Strategy 共性**：

- 同样注入 **分层 / 会话记忆**、**上下文压缩**（与 `ReactWorkflow` 类似的版本门控块）。
- 文件前部大量 **Citation / URL / 实体** 相关逻辑，用于搜索结果筛选与可验证性（与 `docs` 中 deep research、citation 说明一致）。

---

## 6. 其它策略（简述）

| 策略 | 文件 | 文档描述的组合思路 |
|------|------|-------------------|
| **Exploratory** | `strategies/exploratory.go` | ToT 探索，低置信度时 Fallback 到 Debate，最后 Reflection |
| **Scientific** | `strategies/scientific.go` | CoT 假设 → Debate 检验 → ToT 展延 → Reflection 综合 |
| **Supervisor** | `supervisor_workflow.go` | 监督式分解与策略记忆；简单任务可 **委托子工作流 `DAGWorkflow`** |

路由表与选型直觉见 `multi-agent-workflow-architecture.md` 中的 mermaid 与「When to Use」表格。

---

## 7. 模板工作流与 Pattern 注册表

- **YAML 模板**：`config/workflows` 下定义 `nodes`（`simple` / `cognitive` / `dag` / `supervisor`）、`strategy: react | chain_of_thought | …`、`depends_on`、每节点 `budget_max` 等（见 `docs/template-workflows.md`）。
- **执行**：`TemplateWorkflow` 按节点类型分发；普通节点从 **`patterns` 注册表** 取 `PatternType` 对应实现，并支持 **`DegradeByBudget`**：预算不足时将策略降级为更省钱的模式（见 `template_workflow.go`）。
- **DAG 子节点**：`type: dag` 时在 `metadata.tasks` 声明子任务及其 `depends_on`，由 `executeDAGTemplateNode` 执行。

这形成文档所述 **System 1（模板零路由 token）+ System 2（AI 分解）** 的双轨。

---

## 8. `routeStrategyWorkflow` 与命名策略

`routeStrategyWorkflow`（`orchestrator_router.go`）将字符串策略映射到子工作流，例如：

- `react` → `ReactWorkflow`
- `research` → `ResearchWorkflow`
- `exploratory` / `scientific` / `browser_use` 等 → 对应命名 Workflow

同一 `case` 下多个别名共享一段子工作流调度逻辑，便于分解器与产品层用统一「策略名」接入。

---

## 9. 与 mw4agent 编排的对比（概念层）

| 维度 | Shannon | mw4agent（当前 Gateway 编排） |
|------|---------|------------------------------|
| 运行时 | Temporal Workflow + Activity，强回放与信号 | 进程内异步 + RPC，轻量状态持久化 |
| 任务图 | LLM 分解 + 显式 DAG；模板内嵌 DAG | 主要 round-robin 串行参与者（见 `Orchestrating.md`） |
| ReAct / Research | 独立 Strategy + 共享 `patterns` 库 | 单 Agent 工具循环为主，编排侧未拆到同粒度 |
| 预算 / 审批 | 中间件、模板 per-node 降级、Research HITL | 可按需逐步对齐 |

本文档可作为阅读 Shannon 源码与 `docs/multi-agent-workflow-architecture.md`、`docs/template-workflows.md`、`docs/pattern-usage-guide.md` 的**索引与实现向导读**。

---

## 10. 参考路径（Shannon 仓库内）

- 路由：`go/orchestrator/internal/workflows/orchestrator_router.go`
- DAG：`go/orchestrator/internal/workflows/strategies/dag.go`
- ReAct：`go/orchestrator/internal/workflows/strategies/react.go`，`go/orchestrator/internal/workflows/patterns/react.go`
- Research：`go/orchestrator/internal/workflows/strategies/research.go`
- Pattern 类型与注册：`go/orchestrator/internal/workflows/patterns/registry.go`
- 模板执行：`go/orchestrator/internal/workflows/template_workflow.go`
- 执行后端（并行/顺序/混合）：`go/orchestrator/internal/workflows/patterns/execution/`
- 官方说明：`docs/multi-agent-workflow-architecture.md`，`docs/template-workflows.md`，`docs/pattern-usage-guide.md`
