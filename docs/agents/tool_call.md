# MW4Agent 极简 Tool-Call 协议设计与示例

本文档说明当前在 `AgentRunner` 中实现的极简 tool-call 协议格式，以及如何编写测试示例验证该协议。

## 1. 协议所在位置

- 实现位置：`mw4agent/agents/runner/runner.py` 中的 `_execute_agent_turn(...)`。
- 工具执行复用现有：
  - `ToolRegistry`（`mw4agent/agents/tools/registry.py`）
  - `AgentTool` 抽象（`mw4agent/agents/tools/base.py`）
  - 示例工具：`GatewayLsTool`（`mw4agent/agents/tools/gateway_tool.py`）

当 `AgentRunParams.message` 是特定 JSON 结构时，`_execute_agent_turn` 会先执行工具，再将工具结果拼入新 prompt 调用 LLM；否则按普通单轮 LLM 调用处理。

## 2. Tool-Call 协议格式（message 字段里的 JSON）

当 `AgentRunParams.message` 为如下结构的 JSON 字符串时，`AgentRunner` 会自动识别为一次 tool-call 计划：

```json
{
  "type": "tool_call",
  "tool_name": "gateway_ls",
  "tool_args": {"path": "."},
  "final_user_message": "根据上面的文件列表，用一两句话说明这个目录大致是什么项目。"
}
```

字段说明：

- **type**：
  - 固定为 `"tool_call"`，表示本轮先执行一次工具，再调用 LLM。
- **tool_name**：
  - 要调用的工具名称，必须已在 `ToolRegistry` 中注册，例如 `gateway_ls`。
- **tool_args**：
  - 传递给工具的参数对象，对应 `AgentTool.execute(tool_call_id, params, context)` 中的 `params`。
  - 必须是 `object`/`dict`，否则会被安全地降级为 `{}`。
- **final_user_message**（可选）：
  - 工具执行完之后，要交给 LLM 的“最终用户问题”。
  - 如果缺省，则退回到原始 `params.message` 字符串。
- **tool_call_id**（可选）：
  - 自定义的 tool call ID；如果未提供，`AgentRunner` 会自动生成 UUID。

> 其他任意字段会被忽略，不影响协议执行。

## 3. 运行时行为（_execute_agent_turn 概要）

`_execute_agent_turn(...)` 针对该协议的逻辑要点如下：

1. 先发出一条 `assistant` 流式事件，提示“Processing...”：
   - `stream="assistant"`, `type="delta"`, `data={"run_id": run_id, "text": "Processing..."}`。
2. 尝试对 `params.message` 做 `json.loads`：
   - 若解析成功、为 `dict` 且 `type == "tool_call"` 且存在字符串字段 `tool_name`：
     - 视为 `tool_plan`，进入“工具 + LLM”路径。
   - 否则：视为普通文本，进入“单次 LLM 调用”路径。
3. 在 `tool_plan` 路径中：
   - 从 `tool_plan` 读取：
     - `tool_name`：工具名称。
     - `tool_args`：工具参数字典，非 `dict` 时安全降级为 `{}`。
     - `final_user_message`：不存在时退回 `params.message`。
     - `tool_call_id`：来自 JSON 或自动生成 UUID。
   - 调用共享工具执行逻辑：
     - `tool_result = await self.execute_tool(tool_call_id, tool_name, tool_args, context=...)`
     - 内部会通过 `ToolRegistry` 查找 `AgentTool` 并执行，同时发出 `tool` 流事件（start/end/error）。
   - 根据 `tool_result.success` 组装一段工具结果文本 `tool_text`：
     - 成功：`"Tool <name> succeeded with result:\n<repr(result)>"`；
     - 失败：`"Tool <name> failed with error: <error or result repr>"`。
   - 构造新的 LLM message（传递给 backend）：

     ```text
     <final_user_message>

     [Tool <tool_name> output]
     <tool_text>
     ```

   - 使用 `dataclasses.replace` 创建一个只修改 `message` 的 `AgentRunParams` 副本，并调用 `generate_reply`：

     ```python
     llm_params = replace(params, message=composed_message)
     reply_text, provider, model, usage = generate_reply(llm_params)
     ```

4. 在非 `tool_plan` 路径中：
   - 直接调用 `generate_reply(params)`，行为与引入协议前保持一致。
5. 之后无论是否走过工具，都统一：
   - 发出最终的 `assistant` 事件：`{"run_id": run_id, "text": reply_text, "final": True}`；
   - 更新会话的 `message_count`；
   - 组装 `AgentRunResult` 和 `AgentRunMeta`（含 provider/model/usage/duration_ms 等）。

## 4. 测试示例：直接使用 AgentRunner

以下示例演示如何在本地直接通过 `AgentRunner` 验证极简 tool-call 协议（以 `gateway_ls` 为例）。

### 4.1 准备：注册工具

```python
from mw4agent.agents.tools import get_tool_registry, GatewayLsTool

reg = get_tool_registry()
reg.register(GatewayLsTool())
```

> 说明：  
> `GatewayLsTool` 内部会调用 Gateway 的 `ls` RPC，要么需要事先启动一个包含 `ls` 方法的 Gateway，要么可以接受失败返回（依然会被拼到 prompt 中）。

### 4.2 完整测试脚本示例

```python
import asyncio
import json

from mw4agent.agents.runner.runner import AgentRunner
from mw4agent.agents.session.manager import SessionManager
from mw4agent.agents.types import AgentRunParams
from mw4agent.agents.tools import get_tool_registry, GatewayLsTool

# 1. 注册工具
reg = get_tool_registry()
reg.register(GatewayLsTool())


async def main() -> None:
    # 2. 创建 SessionManager 和 AgentRunner
    session_manager = SessionManager("/tmp/mw4agent.toolcall.sessions.json")
    runner = AgentRunner(session_manager)

    # 3. 构造 tool-call 协议的 message JSON
    msg = json.dumps(
        {
            "type": "tool_call",
            "tool_name": "gateway_ls",
            "tool_args": {"path": "."},
            "final_user_message": "根据上面的文件列表，用一两句话说明这个目录大致是什么项目。",
        },
        ensure_ascii=False,
    )

    # 4. 运行一轮 agent
    result = await runner.run(AgentRunParams(message=msg))

    # 5. 打印结果
    print("provider:", result.meta.provider, "model:", result.meta.model)
    print("text:", result.payloads[0].text)


asyncio.run(main())
```

在默认 echo LLM 后端下，输出大致类似：

```text
provider: echo model: gpt-4o-mini
text: Agent (echo) reply: 根据上面的文件列表，用一两句话说明这个目录大致是什么项目。

[Tool gateway_ls output]
Tool gateway_ls failed with error: 'HTTP Error 404: Not Found'
```

如果对应的 Gateway 已启动并正确实现了 `ls` RPC，则上述最后一段会包含真实目录的列表结果，方便验证“工具 → LLM”这一极简链路是否按预期工作。

## 5. 后续扩展思路（可选）

当前协议是“调用方主动写 JSON 决定调用哪个工具”，后续可以在此基础上扩展：

- 由 LLM 根据自然语言自行生成上述 JSON（作为 planning 步骤），再交给 `_execute_agent_turn` 执行；
- 支持一次消息中多次 tool calls 的简单序列；
- 将工具 schema（`ToolRegistry.get_tool_definitions()`）注入到系统 prompt 中，进一步对齐 OpenClaw 的工具调用体验。 

# MW4Agent 极简 Tool-Call 协议说明

本文档记录当前在 `AgentRunner` 中实现的极简 tool-call 协议格式，以及一个直接使用 `AgentRunner` 的测试示例，方便对照 OpenClaw 的 `runEmbeddedAttempt` / 工具循环逻辑进行演进。

---

## 1. 协议格式：`AgentRunParams.message` 中的 JSON

当一次运行的 `AgentRunParams.message` 是如下结构的 JSON 字符串时，`AgentRunner._execute_agent_turn` 会按“先工具、后 LLM”的顺序执行：

```json
{
  "type": "tool_call",
  "tool_name": "gateway_ls",
  "tool_args": {"path": "."},
  "final_user_message": "根据上面的文件列表，用一两句话说明这个目录大致是什么项目。"
}
```

字段约定：

- **type**：
  - 必须为 `"tool_call"`，表示这是一次“先工具后 LLM”的调用计划。
- **tool_name**：
  - 要调用的工具名称，例如 `gateway_ls`，必须存在于全局 `ToolRegistry` 中。
- **tool_args**：
  - 传给工具的参数对象（`dict`），会被原样作为 `AgentTool.execute(tool_call_id, params, context)` 的 `params`。
- **final_user_message**（可选）：
  - 工具执行结束后要交给 LLM 的“最终用户问题”。
  - 若未提供，则默认回退为原始的 `params.message` 字符串。
- **tool_call_id**（可选）：
  - 若提供，将作为此次工具调用的 `tool_call_id`，否则由 `AgentRunner` 自动生成 UUID。

当 `message` 不是上述格式（例如是普通自然语言文本，或不是合法 JSON），`AgentRunner` 会退化为单次 LLM 调用（保持兼容）。

---

## 2. 执行流程（Runner 视角）

协议由 `mw4agent/agents/runner/runner.py` 中的 `_execute_agent_turn` 解释执行，关键步骤如下：

1. **解析 message 是否为 tool-call 计划**

   - `json.loads(params.message)` 成功且为 `dict` 且 `type == "tool_call"` 且有 `tool_name` → 认定为 `tool_plan`。
   - 否则 `tool_plan = None`，直接调用 LLM（走单轮对话）。

2. **有 `tool_plan` 的路径**

   - 从 `tool_plan` 中提取：
     - `tool_name`：工具名。
     - `tool_args`：工具参数（非 `dict` 时退为 `{}`）。
     - `final_user_message`：最终用户问题（缺省则回退为原始 `params.message`）。
     - `tool_call_id`：给工具的调用 ID（缺省用 UUID）。
   - 调用共享工具执行入口：

     ```python
     tool_result = await self.execute_tool(
         tool_call_id=tool_call_id,
         tool_name=tool_name,
         params=tool_args,
         context={"run_id": run_id, "session_key": params.session_key, "agent_id": params.agent_id},
     )
     ```

     - 内部通过 `ToolRegistry` 找到对应的 `AgentTool` 实例。
     - 发送 `tool` 流事件：`start` / `end` / `error`。

   - 将工具执行结果转成一段可读文本 `tool_text`：
     - 成功：`"Tool <name> succeeded with result:\n<repr(result)>"`。
     - 失败：`"Tool <name> failed with error: <error or result repr>"`。

   - 拼装新的 LLM message：

     ```text
     <final_user_message>

     [Tool <tool_name> output]
     <tool_text>
     ```

   - 使用 `dataclasses.replace(params, message=composed_message)` 构造新的 `AgentRunParams`，再调用 `generate_reply(...)` 完成本轮 LLM 调用。

3. **无 `tool_plan` 的路径**

   - 直接调用：

     ```python
     reply_text, provider, model, usage = generate_reply(params)
     ```

   - 行为与之前“单轮 LLM 调用”完全一致。

4. **其余部分**

   - 无论是否走工具分支，结尾都会：
     - 发出最终 `assistant` 流事件（`final=True`）。
     - 更新 `SessionManager` 中的会话统计（如 `message_count`）。
     - 组装 `AgentRunResult`（`payloads` + `AgentRunMeta`）。

---

## 3. 测试示例：直接通过 AgentRunner 触发 Tool-Call

下面是一个直接使用 `AgentRunner` 的极简测试脚本，用于验证 JSON 协议驱动下的“先 `gateway_ls` 工具，再 LLM 回答”的完整流程。

> 注意：要确保在全局工具注册表中已经注册了 `GatewayLsTool`，否则会提示工具不存在。

```python
import asyncio
import json

from mw4agent.agents.runner.runner import AgentRunner
from mw4agent.agents.session.manager import SessionManager
from mw4agent.agents.types import AgentRunParams
from mw4agent.agents.tools import get_tool_registry, GatewayLsTool

# 1. 在全局 ToolRegistry 注册 gateway_ls 工具
reg = get_tool_registry()
reg.register(GatewayLsTool())


async def main() -> None:
    # 2. 构造 AgentRunner 与 SessionManager
    session_manager = SessionManager("/tmp/mw4agent.toolcall.sessions.json")
    runner = AgentRunner(session_manager)

    # 3. 构造 tool-call 协议的 message
    msg = json.dumps(
        {
            "type": "tool_call",
            "tool_name": "gateway_ls",
            "tool_args": {"path": "."},
            "final_user_message": "根据上面的文件列表，用一两句话说明这个目录大致是什么项目。",
        },
        ensure_ascii=False,
    )

    # 4. 运行一轮 agent
    result = await runner.run(AgentRunParams(message=msg))

    print("provider:", result.meta.provider, "model:", result.meta.model)
    print("text:", result.payloads[0].text)


asyncio.run(main())
```

在默认 echo LLM 后端配置下（`MW4AGENT_LLM_PROVIDER` 未设置或为 `echo`）：

- 工具调用部分会真实执行 `gateway_ls`（通过 Gateway RPC 的 `ls` 方法）；
- LLM 部分会对拼接后的 prompt 做简单 echo，便于观察最终组合后的文本结构。

当启用真实 OpenAI 后端（`MW4AGENT_LLM_PROVIDER=openai` 且设置了 `OPENAI_API_KEY`）时，第二阶段的回答将由 OpenAI Chat API 生成，但工具调用协议本身保持不变。

---

## 4. 后续演进方向（参考 OpenClaw）

当前协议是“调用方显式给出工具计划”的极简版本，与 OpenClaw 完整的工具循环相比还缺少：

- LLM 自主选择是否调用工具、调用哪个工具（由模型输出 tool-call JSON 计划）。
- 多轮工具调用循环（工具结果 → 再让 LLM 决策下一步）。
- 对工具调用和结果的更细粒度流式事件与权限校验。

MW4Agent 后续可以在本协议基础上迭代：

- 在 LLM 前增加一个“planner”步骤，让 LLM 输出上述 JSON 结构，然后复用当前执行分支；
- 引入多轮 attempt 与工具循环，逐步向 OpenClaw 的 `runEmbeddedAttempt` 靠拢。 

