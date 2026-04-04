# Orbit MemoryIndex / 混合检索 / 多后端 / 会话增量同步 实现计划

本文用于跟踪 “对齐 OpenClaw Memory 短期记忆能力”的落地计划，主要围绕：

- 统一 MemoryIndex（长/短期统一索引）
- 混合检索（向量 + FTS）+ MMR + 时间衰减
- 多后端（本地 SQLite + 远端 QMD 风格）与 fallback
- 会话增量同步（短期记忆自动入索引）

## 总体分期

- **Phase 0**：底座与配置打通（只加骨架，不改变现有行为）
- **Phase 1**：本地 MemoryIndexManager（仅 FTS + 文件源）
- **Phase 2**：会话增量同步 + sessions 纳入索引
- **Phase 3**：Embedding Provider + 混合检索 + MMR/时间衰减
- **Phase 4（可选）**：多后端 + 远端 Memory（QMD-like）+ fallback
- **Phase 5**：CLI / Dashboard / 文档收尾

---

## Phase 0：底座与配置打通（准备阶段）

**目标**：只铺结构，不真正连外部 embedding/memory 服务，保持当前行为不变。

- **0.1 定义 Memory 配置段**
  - 在 root config 中增加一个专门的 Memory 段（命名待定，推荐）：
    - `memory` 或 `agents.memorySearch`，示例：
      ```json
      {
        "memory": {
          "enabled": false,
          "sources": ["memory", "sessions"],
          "extraPaths": [],
          "provider": "openai",
          "model": "text-embedding-3-small",
          "remote": {
            "baseUrl": "",
            "apiKey": ""
          },
          "store": {
            "path": "~/.orbit/agents/{agentId}/memory/index.sqlite"
          },
          "chunking": {
            "tokens": 512,
            "overlap": 64
          },
          "sync": {
            "onSessionStart": false,
            "onSearch": false,
            "intervalMinutes": 0,
            "sessions": {
              "deltaBytes": 16384,
              "deltaMessages": 32
            }
          },
          "query": {
            "maxResults": 16,
            "minScore": 0.2,
            "hybrid": {
              "enabled": false,
              "vectorWeight": 0.7,
              "textWeight": 0.3,
              "mmr": {
                "enabled": false,
                "lambda": 0.5
              },
              "temporalDecay": {
                "enabled": false,
                "halfLifeDays": 7
              }
            }
          }
        }
      }
      ```
  - 文档：
    - 更新 `docs/architecture/agents/memory.md`，新增一小节 “Memory 配置骨架（未完全实现部分）”。
    - 在 `docs/manuals/configuration.md` 里增加 `memory` 段的配置说明（标注：目前大部分能力为预留，将逐步启用）。

- **0.2 抽象 Memory 后端接口（不改变现有 search 行为）**
  - 新建 `orbit/memory/backend.py`：
    - 定义接口/抽象类 `MemoryBackend`：
      - `search(query: str, *, session_id: Optional[str], agent_id: Optional[str], max_results: int, **opts) -> List[Dict]`
      - `read_file(path_or_id: str) -> str`
      - `sync(reason: str) -> None`
      - `note_session_delta(session_id: str, *, bytes_delta: int, messages_delta: int) -> None`（Phase 2 使用）
      - `status() -> Dict[str, Any]`
    - 提供一个 **StubBackend**：
      - 内部直接调用现有 `orbit/memory/search.py` 的实现：
        - `search(...)`：关键字+workspace/sessions 搜索（当前逻辑）
        - `read_file(...)`：现有 read_file 逻辑
      - `sync`/`note_session_delta`/`status` 先实现成空或简单统计。
  - 将 `MemorySearchTool` / `MemoryGetTool` 调用路径改成：优先通过 `get_memory_backend()` → StubBackend → 现有实现：
    - 配置 `memory.enabled == false` 时，行为与现在完全一致。

---

## Phase 1：本地 MemoryIndexManager（仅 FTS + 文件源）

**目标**：在不引入 embedding provider 的前提下，先把“统一索引 + 文件源”这层做起来，验证索引生命周期与 API 形状。

- **1.1 SQLite 索引结构设计**
  - 新建 `orbit/memory/index.py`：
    - 创建/管理每 agent 的 index：`~/.orbit/agents/<agentId>/memory/index.sqlite`。
    - 表结构（初版）：
      - `chunks`：
        - `id`（PK）
        - `source`（`memory` / `sessions`）
        - `path`（文件 path 或虚拟 path）
        - `session_id`（可空）
        - `content`（chunk 文本）
        - `created_at` / `updated_at`（ms）
      - `chunks_fts`（FTS5 或等价）：
        - `content` 字段建立全文索引。
    - 提供 API：
      - `index_files(agent_id, workspace_dir, sources, extra_paths)`：全量扫描与切 chunk。
      - `fts_search(query, max_results) -> List[Row]`。

- **1.2 MemoryBackend 的 LocalIndex 实现**
  - 新建 `LocalIndexBackend(MemoryBackend)`：
    - `search(...)`：
      - 若 `memory.enabled == false`：直接 delegate 到 StubBackend（Phase 0 的逻辑）。
      - 若启用：优先通过 FTS 查询 index.sqlite；
    - `read_file(...)`：优先用存储的 path/source，从文件或 transcript 读取原文。
    - `sync(reason)`：
      - `reason in {"startup", "manual"}` 时做一次 `index_files(...)`（仅 `"memory"` 源，即文件）。
    - 暂时不接入 sessions（Phase 2 做）。
  - `get_memory_backend()`：
    - 若 `memory.enabled=true` 且 `provider` 未设置或指定为 `"fts-only"`：返回 `LocalIndexBackend`。
    - 否则仍返回 StubBackend（后续 Phase 3 再引入 embedding backend）。

- **1.3 与现有 memory_search 的过渡**
  - `MemorySearchTool`：
    - 调用 `get_memory_backend().search(...)`。
    - 返回结果 shape 尽量保持与当前 `memory.search` 一致（`path/content/snippet/source` 等）。

> 里程碑：本地有一个 index.sqlite，可以手动触发一次构建，`memory_search` 在开启 memory 配置后走 FTS 索引而不是逐文件 scan。默认 `enabled=false`，对老用户透明。

---

## Phase 2：会话增量同步 + sessions 纳入索引

**目标**：把现有 session transcript 的“短期记忆”增量写入 MemoryIndex，使其在统一索引里可查，并按时间字段为后续时间衰减做准备。

- **2.1 Transcript → MemoryIndex 的 Delta 通路**
  - 在 `orbit/agents/session/transcript.py` 中：
    - 在 `append_messages(...)`、`append_compaction(...)`、`append_custom(...)` 末尾调用一个 hook：
      - 如：`note_transcript_delta(agent_id, session_id, messages=[...])`。
  - 在 Memory 层增加全局/单例 Router：
    - `from orbit.memory.backend import get_memory_backend`
    - `note_transcript_delta(...)` 内部调用 `get_memory_backend().note_session_delta(...)`。

- **2.2 sessions chunking 策略**
  - 在 `LocalIndexBackend` 或 IndexManager 内：
    - 基于 transcript 文件，将会话按 turn 切成 chunk：
      - 一个 user+assistant pair（或 small window）作为一个 chunk；
      - `source="sessions"`，`session_id` 记入；
      - `created_at` 使用 transcript 中的 `timestamp` 或当前时间。
    - 触发条件来自配置：
      - `memory.sync.sessions.deltaBytes`
      - `memory.sync.sessions.deltaMessages`
    - `note_session_delta(...)` 聚合 delta，超过阈值时执行：
      - `sync_sessions(session_id)`：只 re-index 该 session 的新部分。

- **2.3 search 返回中标注来源与时间**
  - `search(...)` 返回结果中包含：
    - `source: "memory" | "sessions"`
    - `session_id`（如有）
    - `path`
    - `updated_at` 或 `created_at`
  - 为 Phase 3 的 Temporal Decay 做基础。

> 里程碑：开启 memory 配置后，短期会话内容会逐步入索引，`memory_search` 能从统一索引里找出 session 片段，而不仅依赖 transcript JSONL / 关键字 scan。

---

## Phase 3：Embedding Provider + 混合检索 + MMR/时间衰减

**目标**：实现 OpenClaw 风格的“向量 + FTS 混合检索 + MMR + Temporal Decay”，在本地单机上先打通一条 embedding pipeline。

- **3.1 Embedding Provider 抽象**
  - 新建 `orbit/memory/embedding.py`：
    - 接口：
      - `embed_texts(texts: list[str]) -> list[list[float]]`
    - 配置来源：`memory.provider/model/remote.*`：
      - 初版可只支持一个 HTTP OpenAI-compatible embedding API，或重用现有 LLM backends 某个 provider。
    - 错误处理：超时/错误时返回全零向量或抛出受控异常。

- **3.2 SQLite 向量表与检索**
  - 在 index.sqlite 中增加：
    - `chunks_vec(chunk_id INTEGER PRIMARY KEY, vector BLOB)`。
  - 索引更新流程：
    - 在同步/增量写入 chunk 时：
      - 调用 `embed_texts` 对新 chunk 生成向量；
      - 存入 `chunks_vec`。
  - 检索实现：
    - 初期可以 brute-force：
      - 取所有相关 chunk 的向量，计算余弦相似度或 dot product，按分数排序；
      - 后续如有需要再考虑专用向量索引或外部库。

- **3.3 Hybrid 搜索与 MMR/Temporal Decay**
  - 搜索流程：
    1. 清洗 query，若为空则返回空。
    2. 若 embedding provider 可用：
       - 嵌入 query → `q_vec`。
       - 对 `chunks_vec` 做向量相似度 top-K。
    3. 若 FTS 可用：
       - 做 FTS 关键字搜索 → top-K。
    4. 合并结果为候选集：
       - 为每个候选计算：
         - `vectorScore`（0~1）
         - `textScore`（FTS 分数归一化）
         - `timeScore`（基于 `updated_at` 和 `halfLifeDays` 计算的时间衰减因子，可选）
    5. 总分：
       - `score = (alpha * vectorScore + beta * textScore) * timeScore`
    6. 如果配置 `mmr.enabled=true`：
       - 在得分排序基础上使用 MMR 控制多样性。
    7. 过滤：`score >= minScore`，再截断 `maxResults`。
  - 对应配置字段：
    - `memory.query.hybrid.enabled/vectorWeight/textWeight`
    - `memory.query.hybrid.mmr.enabled/lambda`
    - `memory.query.hybrid.temporalDecay.enabled/halfLifeDays`
    - `memory.query.maxResults/minScore`

> 里程碑：开启 embedding provider 后，`memory_search` 能利用“向量 + 关键字 + 时间衰减”综合排序，让短期会话/最近改动的文件自然排在前面。

---

## Phase 4（可选）：多后端 & 远端 Memory（QMD-like）

**目标**：在本地 MemoryIndexManager 之外，增加远端 Memory 后端，支持远程 QMD 或其他向量引擎，并实现 fallback。

- **4.1 MemorySearchManager & fallback**
  - 新建 `orbit/memory/search_manager.py`：
    - `get_memory_backend(config, agent_id)`：
      - 若 `memory.remote.backend == "qmd"`：
        - 构造 `RemoteMemoryBackend`，调用远端：
          - `/search` / `/readFile` 等；
        - 使用 `FallbackMemoryBackend(primary=remote, fallback=LocalIndexBackend)` 进行包装。
      - 否则：直接返回本地 `LocalIndexBackend`。
  - 错误处理：
    - primary 出错 → 记录错误 → 标记冷却一段时间 → 临时只用 fallback。

- **4.2 远端协议与配置（简化版）**
  - 配置：
    - `memory.remote.baseUrl`
    - `memory.remote.apiKey`
    - `memory.remote.timeoutSeconds`
  - 协议（可参考 OpenClaw QMD，但先缩小范围）：
    - `POST /search`：`{ query, maxResults, sessionId?, agentId? }`
    - `GET /file?id=...`：读取 chunk 对应原文。

> 这一阶段取决于是否有实际远端 Memory 服务需求，如果没有，可暂缓或只做接口预留。

---

## Phase 5：CLI / Dashboard / 文档收尾

- **5.1 CLI 支持**
  - 新增 `orbit memory` 子命令（类似 OpenClaw memory-cli）：
    - `orbit memory sync`：手动触发全量索引构建/更新。
    - `orbit memory status`：展示当前 MemoryIndex 状态（文档数、sessions 数、最后同步时间等）。
    - `orbit memory search --query ...`：从命令行验证 MemoryBackend.search 行为（方便调试）。

- **5.2 Dashboard 集成**
  - Dashboard 右侧增加 “Memory” 或在 Config 里增加 Memory section：
    - 展示当前 memory 配置；
    - 显示索引统计信息；
    - 提供一个按钮触发后台 `sync`（通过 Gateway RPC 调用）。

- **5.3 文档更新**
  - `docs/architecture/agents/memory.md`：
    - 增加 MemoryIndex / MemoryBackend / Session sync 的架构图与代码路径。
  - `docs/manuals/configuration.md`：
    - 完成 `memory` 段的配置文档，标明每个字段的默认值与推荐用法。
  - 若实现远端 Memory，则增加一篇 `docs/architecture/memory/remote_backend.md` 说明远端协议与部署方式。

---

## 实施建议

- **优先级建议**：
  - 必做：Phase 0 → Phase 1 → Phase 2 → Phase 3
  - 视需求：Phase 4
  - 收尾：Phase 5
- **上线策略**：
  - 所有新能力在配置上默认为关闭（`memory.enabled=false`），逐步灰度开启。
  - 对 `memory_search` 的行为变更只在 `memory.enabled=true` 时生效，避免破坏现有工作流和测试。

