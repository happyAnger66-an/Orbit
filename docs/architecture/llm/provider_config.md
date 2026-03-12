# LLM Provider 可配置化与加密配置说明

## 1. 总体目标

MW4Agent 参考 OpenClaw 的做法，将 **LLM provider / model 抽象为可配置项**，并且：

- 支持多种来源：运行参数、环境变量、加密配置文件；
- 默认使用本地 `echo` 后端（稳定、无外部依赖）；
- 在显式配置为 `openai` 且有 `OPENAI_API_KEY` 时，调用 OpenAI Chat Completions；
- 所有持久化配置通过统一的 **AES-GCM 加密存储** 读写。

## 2. 生效路径与优先级

核心入口在 `mw4agent/llm/backends.py` 的 `generate_reply()`：

- 函数签名：

```python
def generate_reply(params: AgentRunParams) -> Tuple[str, str, str, LLMUsage]:
    """Returns: reply_text, provider, model, usage"""
```

- provider / model 的解析优先级（高 → 低）：

1. **`AgentRunParams` 显式指定**：`params.provider` / `params.model`
2. **环境变量**：
   - `MW4AGENT_LLM_PROVIDER`
   - `MW4AGENT_LLM_MODEL`
3. **加密配置文件 `llm.json`**：
   - `{"provider": "...", "model": "..."}`（见下文）
4. **内置默认值**：
   - `provider` 默认 `"echo"`
   - `model` 默认 `"gpt-4o-mini"`

对应实现片段（简化版）：

```python
cfg = _load_llm_config()  # 通过 ConfigManager + EncryptedFileStore 读取 llm.json
cfg_provider = str(cfg.get("provider") or "").strip().lower()
cfg_model = str(cfg.get("model") or "").strip()

provider = (
    params.provider
    or os.getenv("MW4AGENT_LLM_PROVIDER")
    or cfg_provider
    or "echo"
).strip().lower()

model = (
    params.model
    or os.getenv("MW4AGENT_LLM_MODEL")
    or cfg_model
    or "gpt-4o-mini"
).strip()
```

## 3. 加密配置文件：`llm.json`

### 3.1 存储位置

由 `ConfigManager` 管理（见 `mw4agent/config/manager.py`）：

- 默认目录：`~/.mw4agent/config/`
- 可通过环境变量覆盖：`MW4AGENT_CONFIG_DIR=/custom/path`
- 文件名：`llm.json`

该文件通过 `EncryptedFileStore` 使用 **AES-256-GCM** 加密（带魔术头 `MW4AGENT_ENC_v1`），密钥来自环境变量：

- `MW4AGENT_SECRET_KEY`：base64 编码的 32 字节随机数

### 3.2 配置格式

明文结构（写入时会被加密）：

```json
{
  "provider": "openai",
  "model": "gpt-4o-mini"
}
```

其中：

- **`provider`**：`"echo"` / `"openai"` / （未来可扩展为其它 provider 标识）
- **`model`**：模型名字符串（由具体 provider 解释）

### 3.3 读写示例（Python）

```python
from mw4agent.config import get_default_config_manager

cfg = get_default_config_manager()

# 写入（自动加密）
cfg.write_config("llm", {
    "provider": "openai",
    "model": "gpt-4o-mini",
})

# 读取（自动解密 + 明文回退）
current = cfg.read_config("llm", default={})
print(current.get("provider"), current.get("model"))
```

## 4. LLM backend 行为

### 4.1 Echo backend（默认）

当解析后的 `provider` 为 `"" | "echo" | "debug"` 时：

- 不做任何外部调用；
- 回显一条固定前缀的文本，方便调试与测试：

```python
if provider in ("", "echo", "debug"):
    reply = f"Agent (echo) reply: {params.message}"
    return reply, "echo", model, LLMUsage()
```

### 4.2 OpenAI backend

当 `provider == "openai"` 时：

1. 从环境变量 `OPENAI_API_KEY` 读取 API 密钥（**密钥不写入配置文件**）；
2. 若缺失 API key，则回退 echo：

```python
if provider == "openai":
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        reply = f"Agent (echo:no-api-key) reply: {params.message}"
        return reply, "echo", model, LLMUsage()
```

3. 拼接 prompt（支持附加 `extra_system_prompt`），调用 `_call_openai_chat(...)`：

```python
prompt = params.message
if params.extra_system_prompt:
    prompt = params.extra_system_prompt.strip() + "\n\n" + prompt
text, usage = _call_openai_chat(prompt, model=model, api_key=api_key)
```

4. 任何调用异常时，**fail closed 到 echo**，保证 agent 仍可工作：

```python
except Exception as e:
    fallback = f"Agent (openai-error) reply: {params.message}\n\n[error: {e}]"
    return fallback, provider, model, LLMUsage()
```

## 5. 与 OpenClaw 的对应关系

- OpenClaw 通过全局配置/命令行参数/环境变量组合决定默认模型与 provider；
- MW4Agent 采用类似思路，但：
  - 把持久化配置（`llm.json`）统一走 **加密存储**；
  - 明确了 **参数 > 环境 > 配置 > 默认值** 的优先级；
  - 默认 `echo` backend，避免无配置时直接访问外部服务。

未来若要扩展其它 provider（如本地 Ollama、Anthropic、Azure OpenAI 等），推荐模式是：

1. 在 `llm/backends.py` 中新增 `provider == "<name>"` 分支，实现具体调用逻辑；
2. 在 `llm.json` 中设置：

```json
{
  "provider": "<name>",
  "model": "<model-id>"
}
```

无需改动 `AgentRunner` 的调用流程。

## 6. 安全注意事项

1. **加密密钥**：
   - 只放在环境变量 `MW4AGENT_SECRET_KEY`，不要写入代码库或配置文件；
   - 使用强随机 32 字节密钥，并妥善保管。

2. **API 密钥**：
   - OpenAI 等 provider 的密钥只通过环境变量传入（例如 `OPENAI_API_KEY`）；
   - 不要写入 `llm.json` 或任何加密文件，避免误传/泄露。

3. **权限控制**：
   - 确保 `~/.mw4agent/config` 目录的权限为 700，配置文件为 600；
   - 在多用户环境下避免共享同一配置目录。

