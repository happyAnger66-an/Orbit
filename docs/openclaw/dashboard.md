# OpenClaw Dashboard / Control UI 前端实现框架与原理

本文基于 `openclaw` 仓库源码与官方文档，对 **Gateway Dashboard（Control UI）** 的前端实现做一次整体梳理，方便在 Orbit 中对标实现类似的 Web 控制台。

---

## 1. 整体架构概览

- **定位**：Dashboard 即 Gateway 的 **Control UI**，是一个浏览器单页应用，用于：
  - 查看和控制聊天会话、通道状态、定时任务、技能、节点、日志等；
  - 作为 Gateway 的“管理后台”，暴露各种管理级 RPC。
- **运行位置**：由 Gateway HTTP 服务器直接提供静态资源：
  - 默认地址：`http://<host>:18789/`
  - 可通过 `gateway.controlUi.basePath` 改为子路径（例如 `/openclaw`），静态文件路径为 `dist/control-ui`。
- **技术栈**：
  - 构建：**Vite**
  - UI：**Lit（Web Components）**，而不是 React/Vue
  - 与 Gateway 的通信：浏览器端 **WebSocket**，直接连 Gateway 的 WS 端口
- **典型部署形态**：
  - 本机开发：`openclaw gateway` + 浏览器直接访问 `127.0.0.1:18789`
  - 远程/内网：通过 Tailscale Serve/Tailnet 或 SSH 隧道暴露 Control UI
  - 公网：推荐配合 HTTPS + 严格 auth（token/password + 设备配对）

---

## 2. CLI 到 Dashboard 的链路：`openclaw dashboard`

入口在 `src/commands/dashboard.ts`，CLI 负责：

- 读取配置与 Gateway 监听信息：
  - `readConfigFileSnapshot()`，解析当前 `OpenClawConfig`
  - `resolveGatewayPort(cfg)`，获取 Gateway 监听端口（默认 18789）
  - `cfg.gateway.bind` / `cfg.gateway.customBindHost` / `cfg.gateway.controlUi.basePath`
- 解析 Dashboard 访问 URL：

```ts
// src/commands/dashboard.ts（节选）
const links = resolveControlUiLinks({
  port,
  bind: bind === "lan" ? "loopback" : bind,
  customBindHost,
  basePath,
});
```

- 处理网关认证 token：
  - `gateway.auth.token` 可以配置为明文、环境变量或 SecretRef（外部密钥管理），解析逻辑抽象在：

```ts
// src/commands/dashboard.ts（节选）
const resolved = await resolveConfiguredSecretInputWithFallback({
  config: cfg,
  env,
  value: cfg.gateway?.auth?.token,
  path: "gateway.auth.token",
  readFallback: () => readGatewayTokenEnv(env),
});
```

- URL 中是否带 token 的决策：
  - 如果 token 直接来自配置或环境变量（非 SecretRef），CLI 可以在 URL 的 **fragment** 中添加一次性 token：

```ts
// src/commands/dashboard.ts（节选）
const includeTokenInUrl = token.length > 0 && !resolvedToken.tokenSecretRefConfigured;
const dashboardUrl = includeTokenInUrl
  ? `${links.httpUrl}#token=${encodeURIComponent(token)}`
  : links.httpUrl;
```

  - 若 token 由 SecretRef 管理，则 **不注入 URL**，只打印无 token 的 Dashboard 地址，避免在终端、剪贴板或浏览器启动参数中泄露外部密钥。

- 额外 UX：
  - 自动复制链接到剪贴板：`copyToClipboard(dashboardUrl)`
  - 尝试自动打开浏览器：`openUrl(dashboardUrl)`（使用 `detectBrowserOpenSupport` 检查平台支持）
  - 在无法自动打开时打印 SSH 隧道提示：`formatControlUiSshHint(...)`

> 小结：`openclaw dashboard` 本身不包含前端逻辑，而是负责“拼好 URL + 安全地处理 token + 打开浏览器/打印提示”，前端 SPA 全在 `dist/control-ui` 里，由 Gateway 提供。

---

## 3. Dashboard 前端框架：Vite + Lit SPA

### 3.1 构建与产物

在 `docs/web/control-ui.md` 中，官方说明：

- Gateway 从 `dist/control-ui` 提供静态文件：

```md
The Gateway serves static files from `dist/control-ui`. Build them with:

```bash
pnpm ui:build # auto-installs UI deps on first run
```
```

- 开发模式通过 Vite dev server：

```bash
pnpm ui:dev # auto-installs UI deps on first run
```

- 可选的绝对 basePath（构建时注入）：

```bash
OPENCLAW_CONTROL_UI_BASE_PATH=/openclaw/ pnpm ui:build
```

因此：

- Dashboard 是一个典型的 **Vite SPA**：
  - 使用 Vite 的 dev server（默认 5173 端口）进行开发；
  - 编译后的静态资源（HTML/JS/CSS/静态资源）放入 `dist/control-ui`，由 Gateway HTTP 服务托管。
- UI 组件使用 **Lit** 构建：
  - 每个模块（聊天、会话、通道、Cron、配置等）对应一个或多个 Lit Web Components；
  - 通过自定义元素 + Shadow DOM 组合出完整控制台。

### 3.2 Browser → Gateway WebSocket 通道

Dashboard 本身不通过 REST API，而是直接通过 WebSocket 与 Gateway 通信：

- WebSocket 地址与 HTTP 同端口，基于 Gateway 配置 / 控制台设置推导；
- 所有前端动作（发送消息、查看状态、修改配置等）都封装为 **RPC 事件** 发送给 Gateway：
  - 如 `chat.send` / `chat.history` / `config.get` / `config.set` / `skills.*` / `cron.*` 等；
  - Gateway 回发事件流，前端根据事件类型和 payload 更新 UI 状态。

这部分逻辑对应于 `src/web/*` 下的一系列 TypeScript 模块（更偏内部协议层，而非 UI 组件本身）：

- `src/web/inbound.*`：处理 WebSocket 入站事件；
- `src/web/outbound.ts`：将前端操作转为发送给 Gateway 的消息格式；
- `src/web/session.ts` / `src/web/auth-store.ts`：负责连接生命周期管理与认证处理；
- `src/web/auto-reply/**`：为 Web 自动回复场景复用同一套事件/会话抽象。

> 从架构角度看：Dashboard UI = Vite + Lit 组件层；`src/web/**` = WebSocket 协议与会话管理层，两者通过浏览器端 JS 共享同一运行环境。

---

## 4. 认证与安全模型（前端视角）

### 4.1 WebSocket 握手认证

在 `docs/web/control-ui.md` 中，认证是通过 WebSocket 握手参数完成的：

- 控制 UI 在建立连接时发送：
  - `connect.params.auth.token`
  - 或 `connect.params.auth.password`
- Gateway 会在握手时校验：
  - token/password 是否匹配 `gateway.auth.*` 配置；
  - 设备是否已完成配对（Device pairing 系统）；
  - 是否允许 Tailscale 身份作为认证来源（`gateway.auth.allowTailscale`）。

前端这边的核心原则：

- **不在 URL query 中传 token**（避免日志泄漏、Referer 泄漏）；
- 首次打开可从 URL fragment / 页面设置中注入 token，然后：
  - `token` 存在于 **sessionStorage**（当前标签页 + 当前 Gateway URL）；
  - `password` 仅保存在内存，不落盘；
  - 部分网关 URL 配置（`gatewayUrl`）可以保存在 localStorage 中，以方便 dev server + 远程 Gateway 开发模式。

### 4.2 URL 参数与本地存储策略

`docs/web/control-ui.md` 对 dev server + remote Gateway 场景有示例：

```text
http://localhost:5173/?gatewayUrl=ws://<gateway-host>:18789
http://localhost:5173/?gatewayUrl=wss://<gateway-host>:18789#token=<gateway-token>
```

行为总结：

- `gatewayUrl`（WS 地址）：
  - 从 URL query 读取；
  - 读取后写入 localStorage，随后从 URL 移除；
  - 允许指定远程 Gateway 主机（配合 Tailscale / SSH 转发）。
- `token`（认证 token）：
  - 从 URL fragment（`#token=...`）读取；
  - 存入 sessionStorage，仅对当前浏览器标签页 + 当前 `gatewayUrl` 生效；
  - 随后从 URL 中剥离，以减少泄漏面。
- `password`：
  - 不落盘，只驻留在内存状态机中，由用户在 UI 中手动输入。

Dashboard 的前端状态管理大致遵循：

- 初始化阶段：
  - 解析 URL → gatewayUrl + token；
  - 根据 URL / 存储的 gatewayUrl 决定连接目标；
  - 若无显式凭证，则报错提示用户补充认证信息。
- 运行时：
  - UI 内的“设置面板”允许用户修改 `gatewayUrl`、token、语言、主题等；
  - 改动会反映到本地存储与当前 WebSocket 连接。

---

## 5. 功能模块与 WebSocket 协议映射

Control UI 在文档中列举了当前支持的主要模块，它们都通过统一的 Gateway WS RPC 协议实现：

- **聊天（Chat）**：
  - 调用：`chat.send` / `chat.history` / `chat.inject` / `chat.abort`
  - UI 显示：消息列表、实时流式输出、工具卡片/事件流。
- **通道（Channels）**：
  - WhatsApp / Telegram / Discord / Slack 等渠道的状态、登录 QR、配置表单；
  - 使用 `channels.status` / `web.login.*` / `config.patch` 等 RPC。
- **会话（Sessions）**：
  - `sessions.list` / `sessions.patch`，支持 per-session 的思考/verbose 开关；
- **定时任务（Cron）**：
  - `cron.*` 一整套 RPC：列表、创建、编辑、运行、启停、历史查看等；
- **技能（Skills）**：
  - `skills.*`：查看/启用/禁用/安装/更新 Skill；
- **配置（Config）**：
  - `config.get` / `config.set` / `config.apply` / `config.schema` 等：
    - 支持 JSON 表单渲染 + 原始 JSON 编辑；
    - 写入时使用 base-hash 防止覆盖并发修改；
- **节点、日志、更新等模块**：
  - `node.list`、`logs.tail`、`update.run`、`status`、`health`、`models.list` 等。

从前端实现角度：

- Lit 组件只负责渲染与事件触发；
- RPC 发送 / 事件流订阅统一封装在某个“GatewayClient / Session” 抽象里（对应 `src/web/session.ts` / `src/web/outbound.ts` 等）；
- UI 和 WebSocket 层松耦合：替换 Gateway 后端时，只要 RPC 协议保持兼容，Control UI 可以复用。

---

## 6. 调试与远程开发模式

Dashboard 支持使用 Vite dev server 连接远程 Gateway，便于：

- 在本机上开发前端；
- 将 Gateway 部署在本地 Docker / 远程服务器 / Tailscale 节点上。

典型流程（见 `docs/web/control-ui.md`）：

1. 本地起 UI dev server：

   ```bash
   pnpm ui:dev
   ```

2. 用 `gatewayUrl` 指向远程 Gateway：

   ```text
   http://localhost:5173/?gatewayUrl=ws://<gateway-host>:18789
   ```

3. 如需带 token，一次性通过 URL fragment 传入：

   ```text
   http://localhost:5173/?gatewayUrl=wss://<gateway-host>:18789#token=<gateway-token>
   ```

4. Control UI 会：
   - 将 `gatewayUrl` 存入 localStorage；
   - 将 `token` 存入 sessionStorage（当前标签页），并从 URL 移除；
   - 建立到 Gateway 的 WebSocket 连接，并在失败时展示详细错误与重连提示。

安全注意：

- 远程 Gateway 部署时，必须配置 `gateway.controlUi.allowedOrigins` 以白名单方式允许 dev server 源（如 `http://localhost:5173`），否则 Gateway 拒绝启动；
- 可以通过 `gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback` 暂时放宽 Host header 检查，但这是“救火模式”，应尽快恢复安全配置。

---

## 7. 对 Orbit 的设计启示

从 OpenClaw Dashboard 的实现可以提炼出一些对 Orbit 有参考价值的点：

- **前后端边界清晰**：
  - 所有管理能力都通过统一的 WebSocket RPC 暴露；
  - 前端只是 Vite + Lit SPA，专注 UI 和状态管理。
- **认证与 token 处理安全**：
  - token 使用 URL fragment + sessionStorage，一次性导入后即从 URL 剥离；
  - 密钥管理支持 SecretRef / 环境变量，CLI 明确避免在非必要场景下打印或拼接敏感值。
- **绑定模式与 Origin 安全**：
  - 通过 `bind` + `controlUi.basePath` + `allowedOrigins` 管理 Control UI 暴露面；
  - Tailscale Serve / Tailnet 与 JWT/token/password 结合，形成多层防护。
- **模块化的 WebSocket 协议**：
  - 所有功能面板都基于一套统一的事件/命令总线（`chat.*`、`config.*`、`skills.*` 等）；
  - 为未来扩展新模块（如 Memory 可视化、LLM 监控）提供良好基础。

在 Orbit 中实现 Dashboard 时，可以对标：

- 使用 Vite +（React/Lit/Vue 任一）构建一个轻量 SPA；
- 由 Python Gateway 提供：
  - 静态文件目录（例如 `dist/orbit-dashboard`）；
  - 单一 WebSocket 端点（统一 RPC 协议）；
- 前端复用 OpenClaw 思路：
  - URL fragment 注入 token；
  - sessionStorage/localStorage 管理网关 URL / 会话偏好；
  - 各模块通过统一 RPC 协议读写状态。

