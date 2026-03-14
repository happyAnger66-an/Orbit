# Skills 架构与格式说明

本文档说明 MW4Agent 技能文件的格式支持与实现，以及与 OpenClaw 的兼容约定。

---

## 1. 支持的技能文件格式

| 格式 | 路径形式 | 说明 |
|------|----------|------|
| **JSON** | `<name>.json` | 原有格式，支持加密存储；程序写入仍仅使用 JSON。 |
| **Markdown 单文件** | `<name>.md` | 文件首部为 YAML frontmatter（`---` 包围），其后为 Markdown 正文。 |
| **OpenClaw 目录形式** | `<name>/SKILL.md` | 每个技能一个目录，目录内固定文件名为 `SKILL.md`，内容同上。 |

解析优先级：先查找 `<name>.json`，再查找 `<name>.md`，最后查找 `<name>/SKILL.md`。

---

## 2. 实现与修改总结

### 2.1 新增模块 `mw4agent/skills/format_md.py`

- **`parse_skill_markdown(content: str) -> dict`**：解析 SKILL.md 风格内容（YAML frontmatter + Markdown 正文）。
- 支持的 frontmatter 字段：
  - **name** / **description**（或 **desc**）：必选语义，用于快照与 LLM 提示。
  - **metadata**：可选；其中 OpenClaw 约定 `metadata.clawdbot.requires.anyBins` 会映射为内部的 **tools** 列表。
  - **enabled**：可选，默认视为 `True`。
- 正文部分放入返回字典的 **content** 键。
- 依赖 **PyYAML** 解析 YAML；若无 PyYAML，则回退到简易的 key: value 行解析。

### 2.2 修改 `mw4agent/skills/manager.py`

- **`_resolve_skill_path(name)`**：按上述三种形式解析，返回 `(Path, "json"|"md")` 或 `None`。
- **`list_skills()`**：同时列举 `.json`、`.md` 以及包含 `SKILL.md` 的子目录，按技能名去重后排序。
- **`read_skill(name)`**：根据解析结果读取 JSON 或 Markdown；Markdown 通过 `parse_skill_markdown` 转成与 JSON 技能相同的字典结构；若 frontmatter 中无 `name`，则用文件名/目录名补全。
- **`delete_skill(name)`**：删除解析到的那个文件（.json / .md / SKILL.md 之一）。
- **`write_skill(name, data)`**：行为不变，仍只写入 JSON（支持加密）。

### 2.3 依赖

- **setup.py**：新增 `PyYAML>=6.0`。

### 2.4 测试

- **tests/test_skill_format_md.py**：Markdown 解析单测（OpenClaw 风格 frontmatter、最简 frontmatter、无 frontmatter、`desc`/`description`）。
- **tests/e2e/test_skill_manager_e2e.py**：新增 `test_skill_manager_markdown_and_skill_md`，覆盖 JSON、`.md`、`<name>/SKILL.md` 并存时的列举与读取。

---

## 3. 与 OpenClaw 的兼容约定

- **目录布局**：支持 `skills/<skillName>/SKILL.md` 的目录+单文件形式。
- **文件格式**：`---` 包裹的 YAML frontmatter + Markdown 正文。
- **Frontmatter**：至少包含 `name`、`description`；可选 `metadata`（如 `metadata.clawdbot.requires.anyBins` 映射为 `tools`）。
- **读入后的结构**：与现有 JSON 技能一致（`name`、`description`，可选 `tools`、`examples`、`enabled`、`content`），因此 snapshot 与 LLM prompt 注入逻辑无需改动。

---

## 4. 相关代码位置

- 技能管理：`mw4agent/skills/manager.py`
- Markdown 解析：`mw4agent/skills/format_md.py`
- 技能快照（注入 LLM prompt）：`mw4agent/agents/skills/snapshot.py`
- OpenClaw 设计参考：`docs/openclaw/skills.md`
