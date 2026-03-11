"""Command registry - extensible command registration mechanism"""

from typing import Callable, Dict, List, Optional, Protocol, Any
import click
from .context import ProgramContext


class CommandDescriptor(Protocol):
    """Command descriptor protocol"""
    name: str
    description: str
    has_subcommands: bool


class CommandEntry:
    """Command entry definition"""

    def __init__(
        self,
        commands: List[Dict[str, Any]],
        register: Callable[[click.Group, ProgramContext], None],
    ):
        """
        Args:
            commands: List of command descriptors with 'name', 'description', 'has_subcommands'
            register: Registration function that adds commands to the CLI group
        """
        self.commands = commands
        self.register = register


class CommandRegistry:
    """Command registry - manages command registration similar to OpenClaw's command-registry.ts"""

    def __init__(self):
        self._entries: List[CommandEntry] = []
        self._registered_commands: Dict[str, bool] = {}

    def register_entry(self, entry: CommandEntry) -> None:
        """Register a command entry"""
        self._entries.append(entry)
        for cmd in entry.commands:
            self._registered_commands[cmd["name"]] = True

    def get_entry_by_command_name(self, name: str) -> Optional[CommandEntry]:
        """Find entry by command name"""
        for entry in self._entries:
            for cmd in entry.commands:
                if cmd["name"] == name:
                    return entry
        return None

    def get_command_names(self) -> List[str]:
        """Get all registered command names"""
        names: List[str] = []
        seen = set()
        for entry in self._entries:
            for cmd in entry.commands:
                if cmd["name"] not in seen:
                    seen.add(cmd["name"])
                    names.append(cmd["name"])
        return names

    def get_commands_with_subcommands(self) -> List[str]:
        """Get commands that have subcommands"""
        names: List[str] = []
        seen = set()
        for entry in self._entries:
            for cmd in entry.commands:
                if cmd.get("has_subcommands", False) and cmd["name"] not in seen:
                    seen.add(cmd["name"])
                    names.append(cmd["name"])
        return names

    def register_commands(
        self,
        program: click.Group,
        ctx: ProgramContext,
        primary_command: Optional[str] = None,
    ) -> None:
        """
        Register commands to the CLI program
        
        Args:
            program: Click group to register commands to
            ctx: Program context
            primary_command: If provided, only register this command (lazy loading)
        """
        if primary_command:
            # Lazy loading: only register the primary command
            entry = self.get_entry_by_command_name(primary_command)
            if entry:
                entry.register(program, ctx)
            return

        # Register all commands
        for entry in self._entries:
            entry.register(program, ctx)


# Global registry instance
_registry = CommandRegistry()


def get_registry() -> CommandRegistry:
    """Get the global command registry"""
    return _registry


def register_entry(entry: CommandEntry) -> None:
    """Register a command entry in the global registry"""
    _registry.register_entry(entry)
