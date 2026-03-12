# MW4Agent 使用手册（Manuals）框架

本目录用于沉淀 **MW4Agent** 的使用手册，结构参考 OpenClaw 的 `docs/` 体系（CLI、Gateway、Channels、Agents、安装与运维等），但内容专注于 MW4Agent 本身。

> 当前仅搭建文档骨架，后续可逐步填充细节章节。

## 目录结构规划（建议）

- `getting-started.md`：快速开始
  - 安装 / 运行环境
  - 启动 Gateway
  - 启动 console channel 并与 Agent 交互

- `cli.md`：CLI 使用手册
  - 顶级命令概览：`gateway` / `agent` / `channels` / `config`
  - 常用命令示例（诊断、发送消息、查看状态）

- `gateway.md`：Gateway 使用手册
  - HTTP RPC（`agent` / `agent.wait` 等）
  - WebSocket 事件流
  - 与外部系统集成的典型场景

- `agents.md`：AgentRunner 与 Session 手册
  - Agent 运行模型
  - Session 管理与会话持久化
  - LLM 调用与 tool-call 协议

- `channels.md`：Channels 使用手册
  - console 通道
  - Feishu 等其它通道的使用与配置
  - Mention gating 与多通道策略

- `config-and-secrets.md`：配置与加密手册
  - 加密配置（`ConfigManager`）
  - skills 管理（`SkillManager`）
  - LLM provider 配置（`llm.json`）

- `troubleshooting.md`：故障排查
  - 常见错误与解决方案
  - 日志与调试技巧

## 后续写作建议

1. **优先填充 getting-started**：提供从零到能跑通“console + gateway + echo LLM”的最小例子。
2. **CLI 手册与现有 docs/cli 对齐**：将当前 CLI 分析文档（`docs/cli/README.md` 等）中的关键信息整理成用户视角的操作指南。
3. **引用现有模块文档**：
   - LLM 配置可引用 `../llm/provider_config.md`
   - 加密与配置读写可引用 `../crypto/README.md` / `../crypto/encryption-framework.md`
   - Gateway 行为可引用 `../gateway/README.md`
4. **保持与 OpenClaw 文档风格相近**：章节命名和内容组织上可参考 OpenClaw 的 `docs/start/`、`docs/cli/`、`docs/gateway/` 等现有结构，但避免照搬与 MW4Agent 不相关的内容。

