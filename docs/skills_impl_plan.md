# MW4Agent Skills 实现差异分析与补齐计划

本文对比 `mw4agent` 当前 skills 实现与 OpenClaw 的 skills 体系，给出缺口清单与落地计划。

---

## 1. 当前 MW4Agent 已实现能力（基线）

基于代码现状，`mw4agent` 已具备以下基础能力：

- 技能文件读写管理：`SkillManager` 支持 `json`、`md`、`<name>/SKILL.md` 三种格式读取，写入统一为 JSON。
- 加密支持：JSON 技能通过 `EncryptedFileStore` 做加密读写（未配置密钥时可回退明文）。
- 插件技能合并：`build_skill_snapshot()` 会合并默认技能与插件技能（同名时主技能优先）。
- 会话挂载：`AgentRunner` 会将 `skills_snapshot` 挂到 `session_entry.metadata`。
- Prompt 注入：`build_skill_snapshot()` 产出的 `prompt` 会拼接到 LLM 输入中。

这意味着“技能 -> 快照 -> prompt”最小闭环已经可运行。

---

## 2. 与 OpenClaw 的主要差异

### 2.1 技能发现范围与配置驱动能力不足

OpenClaw 以 workspace 为中心，支持多来源目录（workspace、config、home、extraDirs、plugin dirs）统一加载与过滤。  
当前 `mw4agent` 默认技能目录基本是单点（`~/.mw4agent/skills` + plugin skills_dir），缺少：

- workspace 级技能目录优先策略；
- 配置化 `extraDirs`；
- 统一的来源优先级与冲突决策策略（除了“主技能覆盖插件技能”的最小规则）。

### 2.2 缺少 watcher + snapshot version 机制

OpenClaw 使用 watcher 监听 `SKILL.md` 变化，并维护全局/工作区 `skillsSnapshotVersion`，按版本触发刷新。  
当前 `mw4agent` 每次 run 都重新 `build_skill_snapshot()`，没有：

- 文件变化监听；
- 快照版本号；
- “仅在变化后刷新”的增量逻辑。

### 2.3 Session 上的快照结构较简化

OpenClaw `skillsSnapshot` 通常包含 `prompt`、`skills`、`skillFilter`、`resolvedSkills`、`version` 等字段，并用于跨 turn 复用和审计。  
当前 `mw4agent` 快照结构仅有 `skills/count/prompt`，且挂载字段在 `metadata` 下，缺少：

- `version`；
- `skill_filter`（会话级技能筛选）；
- `resolved` 信息（来源、依赖、资格判断结果）；
- 稳定 schema 约束与向后兼容版本声明。

### 2.4 运行时“技能资格判定”能力缺失

OpenClaw 会在构建 prompt 前做 eligibility 处理（如远程执行场景、环境要求、安装状态）。  
当前 `mw4agent` 主要是“读到就暴露”，缺少：

- required env/binaries 判定；
- 不满足条件时的降级描述或剔除策略；
- 远程/本地运行环境差异化策略。

### 2.5 Skills CLI 运维闭环缺失

OpenClaw 有 `skills` 子命令用于列表、检查、安装/同步、审计。  
当前 `mw4agent` 仅有通用 config 读写入口，没有专门 skills 运维命令，导致：

- 可观测性不足（用户难以看到最终生效技能集）；
- 故障定位困难（技能为何未被加载/不可用不可直观看到）；
- 无标准审计输出（依赖、权限、来源）。

### 2.6 Prompt 组织能力较弱

OpenClaw 在 skills prompt 上有截断策略、提示说明、审计建议。  
当前 `mw4agent` 为简单列表拼接，缺少：

- token/长度限制策略；
- 截断提示；
- 按重要性排序与分组（内建/插件/workspace）。

### 2.7 写入与格式兼容策略仍偏单向

当前读取兼容多格式，但写入仅 JSON。与 OpenClaw 生态协作时，缺少：

- 可选输出为 `SKILL.md`（frontmatter + markdown）；
- 技能格式转换工具（json <-> md）；
- 目录结构规范化命令。

---

## 3. 缺失功能优先级（建议）

按“收益/复杂度”排序，建议优先补齐：

1. **技能来源配置化 + 生效清单可观测**（P0）
2. **Session 快照结构升级（含 version/filter）**（P0）
3. **skills CLI（list/check）**（P0）
4. **prompt 长度控制与截断提示**（P1）
5. **watcher + 增量刷新机制**（P1）
6. **eligibility 判定（env/bin）**（P1）
7. **SKILL.md 写入与格式转换工具**（P2）

---

## 4. 分阶段实现计划

## Phase 1（P0，先补齐可用性与可观测性）

- 扩展 skills 配置模型（如 `skills.load.paths`, `skills.load.extra_dirs`, `skills.filter`）。
- 重构 `build_skill_snapshot()`：
  - 输入 `workspace_dir`、`config`、`skill_filter`；
  - 输出统一结构：`skills/prompt/count/version/skill_filter/sources`。
- 在 session 中固定挂载字段结构（建议 `session.metadata.skills_snapshot` 标准化）。
- 新增 CLI：
  - `mw4agent skills list`：列出生效技能、来源、描述；
  - `mw4agent skills check`：检查格式、冲突、缺失字段。

交付标准：用户可明确看到“有哪些技能被加载、来自哪里、为何被过滤”。

## Phase 2（P1，补齐运行时质量）

- 增加 prompt 限制策略（最大技能数/最大字符数），并加入截断提示。
- 引入 eligibility 规则：
  - `required_env`、`required_bins` 检查；
  - 不可用技能可选择“隐藏”或“标记不可用”。
- 将 snapshot 版本化（先无 watcher，可用内容哈希/version counter）。

交付标准：模型看到的 skills 信息可控、稳定，且能解释“为什么某技能不可用”。

## Phase 3（P1/P2，补齐动态刷新与生态兼容）

- 实现 watcher（先监听 workspace + configured dirs 下 `SKILL.md/.json`）。
- 变更触发 version bump，run 时按版本决定是否刷新快照。
- 增加格式工具与写入模式：
  - `mw4agent skills export --format skill-md|json`
  - `mw4agent skills convert <name>`

交付标准：skills 维护成本低，长会话中快照可自动刷新且无明显性能浪费。

---

## 5. 关键设计建议（避免后续返工）

- **统一数据模型先行**：先定义 `SkillEntry` 与 `SkillSnapshot` schema，再改读取/CLI/runner。
- **来源优先级显式化**：例如 `workspace > config-extra > home > plugin`，并在 CLI 中展示。
- **过滤与判定可解释**：每个被排除技能应记录 reason（filter/缺 env/缺 bin/冲突）。
- **保持兼容**：`AgentRunner` 读取 snapshot 时兼容旧字段，平滑升级。
- **测试分层**：解析单测、快照构建单测、runner 集成测试、CLI e2e 测试分离。

---

## 6. 最小目标定义（对齐 OpenClaw 的“可用形态”）

若以“接近 OpenClaw 但不过度复杂”为目标，建议最小完成标准：

- 多来源 skills 加载 + 可配置目录；
- `SkillSnapshot` 含 `prompt + skills + version + filter + sources`；
- session 内可复用快照，并在版本变化时刷新；
- `mw4agent skills list/check` 可用于诊断；
- prompt 有基本截断与告警信息。

达到以上后，MW4Agent 的 skills 子系统将从“可运行”升级为“可运维、可扩展、可解释”。

