"""Register `skills` CLI commands."""

from __future__ import annotations

import json
from typing import Optional

import click

from ...agents.skills.snapshot import build_skill_snapshot


def register_skills_cli(program: click.Group, _ctx) -> None:
    @program.group(name="skills", help="Inspect loaded skills and snapshot state")
    def skills_group() -> None:
        pass

    @skills_group.command(name="list", help="List effective skills in the current snapshot")
    @click.option("--workspace-dir", default="", help="Workspace directory used for skills discovery")
    @click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON")
    def skills_list(workspace_dir: str, as_json: bool) -> None:
        snapshot = build_skill_snapshot(workspace_dir=workspace_dir.strip() or None)
        if as_json:
            click.echo(json.dumps(snapshot, ensure_ascii=False, indent=2))
            return

        click.echo(f"Skills count: {snapshot.get('count', 0)}")
        click.echo(f"Version: {snapshot.get('version') or '-'}")
        sources = snapshot.get("sources") or []
        if sources:
            click.echo("Sources:")
            for source in sources:
                click.echo(f"  - {source.get('name')}: {source.get('count')}")
        skills = snapshot.get("skills") or []
        if not skills:
            click.echo("No skills found.")
            return
        click.echo("Skills:")
        for item in skills:
            name = item.get("name") or ""
            desc = item.get("description") or ""
            source = item.get("source") or "unknown"
            suffix = f": {desc}" if desc else ""
            click.echo(f"  - {name} [{source}]{suffix}")

    @skills_group.command(name="check", help="Check skills snapshot health (schema/conflicts/filter)")
    @click.option("--workspace-dir", default="", help="Workspace directory used for skills discovery")
    @click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON")
    def skills_check(workspace_dir: str, as_json: bool) -> None:
        snapshot = build_skill_snapshot(workspace_dir=workspace_dir.strip() or None)
        skills = snapshot.get("skills") or []

        errors = []
        warnings = []
        names = set()
        for item in skills:
            name = str(item.get("name") or "").strip()
            if not name:
                errors.append("Found skill with empty name")
                continue
            if name in names:
                errors.append(f"Duplicate skill name in effective snapshot: {name}")
            names.add(name)
            if not str(item.get("description") or "").strip():
                warnings.append(f"Skill '{name}' has empty description")
            if not str(item.get("source") or "").strip():
                warnings.append(f"Skill '{name}' has empty source")

        filtered_out = snapshot.get("filtered_out") or []
        if filtered_out:
            warnings.append(f"{len(filtered_out)} skill(s) filtered out by skill_filter")

        ok = len(errors) == 0
        payload = {
            "ok": ok,
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "count": snapshot.get("count", 0),
                "version": snapshot.get("version"),
                "filteredOutCount": len(filtered_out),
            },
        }
        if as_json:
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            click.echo(f"OK: {ok}")
            click.echo(f"Skills count: {payload['summary']['count']}")
            click.echo(f"Version: {payload['summary']['version']}")
            if errors:
                click.echo("Errors:")
                for err in errors:
                    click.echo(f"  - {err}")
            if warnings:
                click.echo("Warnings:")
                for warning in warnings:
                    click.echo(f"  - {warning}")

        if not ok:
            raise SystemExit(1)

