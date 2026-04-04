# Orbit CLI 架构文档

本文档说明 Orbit CLI 的架构设计，参考 OpenClaw 的可扩展命令注册机制。

## 架构概述

Orbit CLI 采用**命令注册表（Command Registry）**模式，类似于 OpenClaw 的 `command-registry.ts` 设计：

```
┌─────────────────────────────────────────┐
│          CLI Entry Point                │
│         (cli/main.py)                   │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      Command Registry                   │
│      (cli/registry.py)                  │
│  - CommandEntry 管理                    │
│  - 懒加载支持                            │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌──────────────┐  ┌──────────────┐
│ Gateway CLI  │  │ 其他命令... │
│ (gateway/)   │  │              │
└──────────────┘  └──────────────┘
```

## 核心组件

### 1. CommandRegistry (`cli/registry.py`)

命令注册表，管理所有命令的注册和发现：

```python
class CommandRegistry:
    def register_entry(self, entry: CommandEntry) -> None
    def get_entry_by_command_name(self, name: str) -> Optional[CommandEntry]
    def register_commands(self, program, ctx, primary_command=None) -> None
```

**特性：**
- 支持命令描述符（name, description, has_subcommands）
- 懒加载：只加载主命令（primary command）
- 命令发现：可以查询已注册的命令

### 2. CommandEntry

命令条目定义，包含命令描述和注册函数：

```python
CommandEntry(
    commands=[
        {
            "name": "gateway",
            "description": "Run, inspect, and query the WebSocket Gateway",
            "has_subcommands": True,
        }
    ],
    register=register_gateway_cli,
)
```

### 3. ProgramContext (`cli/context.py`)

程序上下文，提供全局信息：

```python
class ProgramContext:
    program_version: str
    channel_options: List[str]
    message_channel_options: str
    agent_channel_options: str
```

## 命令注册流程

### 步骤 1: 定义命令注册函数

在 `cli/gateway/register.py` 中：

```python
def register_gateway_cli(program: click.Group, ctx: ProgramContext) -> None:
    @program.group("gateway", help="...")
    def gateway():
        pass
    
    @gateway.command("run")
    def gateway_run():
        ...
```

### 步骤 2: 创建 CommandEntry

在 `cli/main.py` 中：

```python
gateway_entry = CommandEntry(
    commands=[{
        "name": "gateway",
        "description": "Run, inspect, and query the WebSocket Gateway",
        "has_subcommands": True,
    }],
    register=register_gateway_cli,
)
get_registry().register_entry(gateway_entry)
```

### 步骤 3: 注册到程序

```python
register_commands(program, ctx, primary_command="gateway")
```

## 懒加载机制

类似于 OpenClaw 的懒加载策略：

1. **初始注册**：只注册主命令的占位符
2. **按需加载**：当用户执行命令时，才加载完整的命令实现
3. **性能优化**：减少启动时的模块加载时间

**实现：**

```python
primary = get_primary_command(argv)
register_commands(program, ctx, primary_command=primary)
```

如果指定了 `primary_command`，只注册该命令；否则注册所有命令。

## 添加新命令示例

### 示例：添加 `models` 命令

#### 1. 创建命令模块

`cli/models/__init__.py`:
```python
from .register import register_models_cli
__all__ = ["register_models_cli"]
```

`cli/models/register.py`:
```python
import click
from ..context import ProgramContext

def register_models_cli(program: click.Group, ctx: ProgramContext) -> None:
    @program.group("models", help="Manage models")
    def models():
        pass
    
    @models.command("list", help="List available models")
    def models_list():
        click.echo("Available models:")
        # TODO: Implement
    
    @models.command("add", help="Add a model")
    @click.argument("name")
    def models_add(name: str):
        click.echo(f"Adding model: {name}")
        # TODO: Implement
```

#### 2. 注册命令

在 `cli/main.py` 的 `register_core_commands()` 中添加：

```python
from .models import register_models_cli

models_entry = CommandEntry(
    commands=[{
        "name": "models",
        "description": "Manage models",
        "has_subcommands": True,
    }],
    register=register_models_cli,
)
get_registry().register_entry(models_entry)
```

#### 3. 使用

```bash
orbit models --help
orbit models list
orbit models add gpt-4
```

## 与 OpenClaw 的对比

| 特性 | OpenClaw (TypeScript) | Orbit (Python) |
|------|----------------------|-------------------|
| 命令注册 | `coreEntries` 数组 | `CommandEntry` 类 |
| 注册函数 | `async register()` | `register()` |
| 懒加载 | `registerCoreCliByName()` | `register_commands(primary_command=...)` |
| CLI 框架 | Commander.js | Click |
| 类型系统 | TypeScript | Python type hints |

## 设计原则

1. **可扩展性**：通过注册表轻松添加新命令
2. **一致性**：所有命令遵循相同的注册模式
3. **性能**：懒加载减少启动时间
4. **类型安全**：使用类型提示提高代码质量

## 未来扩展

- **插件系统**：支持外部插件注册命令
- **命令发现**：自动发现并注册命令模块
- **命令别名**：支持命令别名
- **命令组合**：支持命令组合执行
