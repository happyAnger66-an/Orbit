"""apply_patch tool — multi-file edits in OpenClaw patch format."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ...config.root import read_root_section
from .base import AgentTool, ToolResult
from .apply_patch_impl import run_apply_patch


def _read_apply_patch_config() -> Dict[str, Any]:
    tools = read_root_section("tools", default={})
    if not isinstance(tools, dict):
        return {}
    ap = tools.get("apply_patch")
    return ap if isinstance(ap, dict) else {}


def is_apply_patch_enabled() -> bool:
    """Whether apply_patch should be exposed to the LLM (default off)."""
    cfg = _read_apply_patch_config()
    return cfg.get("enabled") is True


class ApplyPatchTool(AgentTool):
    """Apply structured multi-file patches (*** Begin Patch ... *** End Patch)."""

    def __init__(self) -> None:
        super().__init__(
            name="apply_patch",
            description=(
                "Apply a patch to one or more files using the apply_patch format. "
                "The input must include '*** Begin Patch' and '*** End Patch' markers. "
                "Supports *** Add File, *** Update File (with @@ context and +/- lines), "
                "*** Delete File, and optional *** Move to for renames. "
                "Paths are relative to the workspace unless absolute within the workspace."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "Full patch text including *** Begin Patch and *** End Patch.",
                    },
                },
                "required": ["input"],
            },
            owner_only=False,
        )

    async def execute(
        self,
        tool_call_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        import os

        ctx = context or {}
        workspace_dir = (ctx.get("workspace_dir") or os.getcwd()).strip()
        workspace_only = bool(ctx.get("tools_fs_workspace_only") is True)

        if not is_apply_patch_enabled():
            return ToolResult(
                success=False,
                result={"error": "disabled"},
                error="apply_patch is disabled; set tools.apply_patch.enabled=true in config",
            )

        raw = params.get("input")
        if raw is None or not str(raw).strip():
            return ToolResult(success=False, result={}, error="apply_patch: input is required")

        try:
            summary, text = run_apply_patch(
                str(raw),
                workspace_dir=workspace_dir,
                workspace_only=workspace_only,
            )
        except (ValueError, PermissionError, OSError) as e:
            return ToolResult(success=False, result={"error": str(e)}, error=str(e))

        return ToolResult(
            success=True,
            result={
                "text": text,
                "summary": {
                    "added": summary.added,
                    "modified": summary.modified,
                    "deleted": summary.deleted,
                },
            },
            metadata={"tool": "apply_patch"},
        )
