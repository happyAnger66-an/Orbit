# MW4Agent CLI

Python implementation of CLI mechanism inspired by OpenClaw's extensible command registration system.

## Features

- **Extensible command registration**: Similar to OpenClaw's command-registry.ts
- **Lazy loading**: Commands are loaded on-demand for faster startup
- **Gateway commands**: Initial implementation of gateway command group

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Show help
mw4agent --help

# Gateway commands
mw4agent gateway --help
mw4agent gateway run
mw4agent gateway status
mw4agent gateway call health
mw4agent gateway discover
mw4agent gateway probe
```

## Architecture

The CLI follows OpenClaw's architecture:

1. **Command Registry** (`cli/registry.py`): Manages command registration
2. **Command Entries**: Define commands with descriptors and registration functions
3. **Lazy Loading**: Only loads the primary command initially
4. **Program Context**: Provides context (version, channel options, etc.)

## Adding New Commands

### 1. Create command module

Create a new module in `cli/` directory, e.g., `cli/models/register.py`:

```python
import click
from ..context import ProgramContext

def register_models_cli(program: click.Group, ctx: ProgramContext) -> None:
    @program.group("models", help="Manage models")
    def models():
        pass
    
    @models.command("list", help="List available models")
    def models_list():
        click.echo("Models list")
```

### 2. Register in main.py

Add to `register_core_commands()`:

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

## Project Structure

```
mw4agent/
├── mw4agent/
│   ├── __init__.py
│   ├── __main__.py
│   └── cli/
│       ├── __init__.py
│       ├── main.py          # Main entry point
│       ├── context.py       # Program context
│       ├── registry.py      # Command registry
│       └── gateway/
│           ├── __init__.py
│           └── register.py # Gateway commands
├── setup.py
└── README.md
```

## Design Principles

- **Extensibility**: Easy to add new commands via registry
- **Lazy Loading**: Fast startup by loading commands on-demand
- **Consistency**: Similar API to OpenClaw's CLI system
- **Type Safety**: Uses type hints throughout
