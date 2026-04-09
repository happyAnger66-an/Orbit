"""Parse OpenClaw / Codex-style apply_patch text (apply-patch.ts port)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

BEGIN_PATCH_MARKER = "*** Begin Patch"
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "*** Move to: "
EOF_MARKER = "*** End of File"
CHANGE_CONTEXT_MARKER = "@@ "
EMPTY_CHANGE_CONTEXT_MARKER = "@@"

Hunk = Dict[str, Any]


def parse_patch_text(input_text: str) -> Tuple[List[Hunk], str]:
    trimmed = (input_text or "").strip()
    if not trimmed:
        raise ValueError("Invalid patch: input is empty.")
    lines = trimmed.split("\n")
    validated = _check_patch_boundaries_lenient(lines)
    hunks: List[Hunk] = []
    last_line_index = len(validated) - 1
    remaining = validated[1:last_line_index]
    line_number = 2
    while remaining:
        hunk, consumed = _parse_one_hunk(remaining, line_number)
        hunks.append(hunk)
        line_number += consumed
        remaining = remaining[consumed:]
    return hunks, "\n".join(validated)


def _check_patch_boundaries_lenient(lines: List[str]) -> List[str]:
    strict_error = _check_patch_boundaries_strict(lines)
    if strict_error is None:
        return lines
    if len(lines) < 4:
        raise ValueError(strict_error)
    first = lines[0]
    last = lines[-1]
    heredoc_starts = ("<<EOF", "<<'EOF'", "<<\"EOF\"")
    if first in heredoc_starts and last.rstrip().endswith("EOF"):
        inner = lines[1:-1]
        inner_error = _check_patch_boundaries_strict(inner)
        if inner_error is None:
            return inner
        raise ValueError(inner_error)
    raise ValueError(strict_error)


def _check_patch_boundaries_strict(lines: List[str]) -> Optional[str]:
    first_line = (lines[0] or "").strip() if lines else ""
    last_line = (lines[-1] or "").strip() if lines else ""
    if first_line == BEGIN_PATCH_MARKER and last_line == END_PATCH_MARKER:
        return None
    if first_line != BEGIN_PATCH_MARKER:
        return "The first line of the patch must be '*** Begin Patch'"
    return "The last line of the patch must be '*** End Patch'"


def _parse_one_hunk(lines: List[str], line_number: int) -> Tuple[Hunk, int]:
    if not lines:
        raise ValueError(f"Invalid patch hunk at line {line_number}: empty hunk")
    first_line = lines[0].strip()
    if first_line.startswith(ADD_FILE_MARKER):
        target_path = first_line[len(ADD_FILE_MARKER) :]
        contents = ""
        consumed = 1
        for add_line in lines[1:]:
            if add_line.startswith("+"):
                contents += add_line[1:] + "\n"
                consumed += 1
            else:
                break
        return ({"kind": "add", "path": target_path, "contents": contents}, consumed)

    if first_line.startswith(DELETE_FILE_MARKER):
        target_path = first_line[len(DELETE_FILE_MARKER) :]
        return ({"kind": "delete", "path": target_path}, 1)

    if first_line.startswith(UPDATE_FILE_MARKER):
        target_path = first_line[len(UPDATE_FILE_MARKER) :]
        remaining = lines[1:]
        consumed = 1
        move_path: Optional[str] = None
        move_candidate = remaining[0].strip() if remaining else ""
        if move_candidate.startswith(MOVE_TO_MARKER):
            move_path = move_candidate[len(MOVE_TO_MARKER) :]
            remaining = remaining[1:]
            consumed += 1
        chunks: List[Dict[str, Any]] = []
        while remaining:
            if remaining[0].strip() == "":
                remaining = remaining[1:]
                consumed += 1
                continue
            if remaining[0].startswith("***"):
                break
            chunk, chunk_lines = _parse_update_file_chunk(
                remaining,
                line_number + consumed,
                len(chunks) == 0,
            )
            chunks.append(chunk)
            remaining = remaining[chunk_lines:]
            consumed += chunk_lines
        if not chunks:
            raise ValueError(
                f"Invalid patch hunk at line {line_number}: Update file hunk for path "
                f"'{target_path}' is empty"
            )
        return (
            {
                "kind": "update",
                "path": target_path,
                "move_path": move_path,
                "chunks": chunks,
            },
            consumed,
        )

    raise ValueError(
        f"Invalid patch hunk at line {line_number}: '{lines[0]}' is not a valid hunk header. "
        "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', "
        "'*** Update File: {path}'"
    )


def _parse_update_file_chunk(
    lines: List[str],
    line_number: int,
    allow_missing_context: bool,
) -> Tuple[Dict[str, Any], int]:
    if not lines:
        raise ValueError(f"Invalid patch hunk at line {line_number}: Update hunk does not contain any lines")

    change_context: Optional[str] = None
    start_index = 0
    if lines[0] == EMPTY_CHANGE_CONTEXT_MARKER:
        start_index = 1
    elif lines[0].startswith(CHANGE_CONTEXT_MARKER):
        change_context = lines[0][len(CHANGE_CONTEXT_MARKER) :]
        start_index = 1
    elif not allow_missing_context:
        raise ValueError(
            f"Invalid patch hunk at line {line_number}: Expected update hunk to start with "
            f"a @@ context marker, got: '{lines[0]}'"
        )

    if start_index >= len(lines):
        raise ValueError(
            f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines"
        )

    chunk: Dict[str, Any] = {
        "change_context": change_context,
        "old_lines": [],
        "new_lines": [],
        "is_end_of_file": False,
    }
    parsed_lines = 0
    for line in lines[start_index:]:
        if line == EOF_MARKER:
            if parsed_lines == 0:
                raise ValueError(
                    f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines"
                )
            chunk["is_end_of_file"] = True
            parsed_lines += 1
            break
        if not line:
            chunk["old_lines"].append("")
            chunk["new_lines"].append("")
            parsed_lines += 1
            continue
        marker = line[0]
        if marker == " ":
            content = line[1:]
            chunk["old_lines"].append(content)
            chunk["new_lines"].append(content)
            parsed_lines += 1
            continue
        if marker == "+":
            chunk["new_lines"].append(line[1:])
            parsed_lines += 1
            continue
        if marker == "-":
            chunk["old_lines"].append(line[1:])
            parsed_lines += 1
            continue
        if parsed_lines == 0:
            raise ValueError(
                f"Invalid patch hunk at line {line_number + 1}: Unexpected line found in update hunk: "
                f"'{line}'. Every line should start with ' ' (context line), '+' (added line), "
                "or '-' (removed line)"
            )
        break
    return chunk, parsed_lines + start_index
