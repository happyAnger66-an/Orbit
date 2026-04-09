"""Apply update hunks to file contents (OpenClaw apply-patch-update.ts port)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

UpdateFileChunk = Dict[str, Any]  # change_context?, old_lines, new_lines, is_end_of_file


def _normalize_punctuation(value: str) -> str:
    out: List[str] = []
    for char in value:
        o = ord(char)
        if o in (
            0x2010,
            0x2011,
            0x2012,
            0x2013,
            0x2014,
            0x2015,
            0x2212,
        ):
            out.append("-")
        elif o in (0x2018, 0x2019, 0x201A, 0x201B):
            out.append("'")
        elif o in (0x201C, 0x201D, 0x201E, 0x201F):
            out.append('"')
        elif o in (
            0x00A0,
            0x2002,
            0x2003,
            0x2004,
            0x2005,
            0x2006,
            0x2007,
            0x2008,
            0x2009,
            0x200A,
            0x202F,
            0x205F,
            0x3000,
        ):
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def _lines_match(
    lines: List[str],
    pattern: List[str],
    start: int,
    normalize: Callable[[str], str],
) -> bool:
    for idx in range(len(pattern)):
        if normalize(lines[start + idx]) != normalize(pattern[idx]):
            return False
    return True


def _seek_sequence(
    lines: List[str],
    pattern: List[str],
    start: int,
    eof: bool,
) -> Optional[int]:
    if len(pattern) == 0:
        return start
    if len(pattern) > len(lines):
        return None
    max_start = len(lines) - len(pattern)
    search_start = max_start if eof and len(lines) >= len(pattern) else start
    if search_start > max_start:
        return None

    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v):
            return i
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v.rstrip("\r\n").rstrip()):
            return i
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: v.strip()):
            return i
    for i in range(search_start, max_start + 1):
        if _lines_match(lines, pattern, i, lambda v: _normalize_punctuation(v.strip())):
            return i
    return None


def _compute_replacements(
    original_lines: List[str],
    file_path: str,
    chunks: List[UpdateFileChunk],
) -> List[Tuple[int, int, List[str]]]:
    replacements: List[Tuple[int, int, List[str]]] = []
    line_index = 0

    for chunk in chunks:
        ctx = chunk.get("change_context")
        if ctx:
            ctx_index = _seek_sequence(original_lines, [ctx], line_index, False)
            if ctx_index is None:
                raise ValueError(f"Failed to find context '{ctx}' in {file_path}")
            line_index = ctx_index + 1

        old_lines: List[str] = list(chunk["old_lines"])
        new_lines: List[str] = list(chunk["new_lines"])
        is_eof = bool(chunk.get("is_end_of_file"))

        if len(old_lines) == 0:
            if len(original_lines) > 0 and original_lines[-1] == "":
                insertion_index = len(original_lines) - 1
            else:
                insertion_index = len(original_lines)
            replacements.append((insertion_index, 0, new_lines))
            continue

        pattern = old_lines
        new_slice = new_lines
        found = _seek_sequence(original_lines, pattern, line_index, is_eof)

        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = _seek_sequence(original_lines, pattern, line_index, is_eof)

        if found is None:
            raise ValueError(
                f"Failed to find expected lines in {file_path}:\n" + "\n".join(chunk["old_lines"])
            )

        replacements.append((found, len(pattern), new_slice))
        line_index = found + len(pattern)

    replacements.sort(key=lambda x: x[0])
    return replacements


def _apply_replacements(lines: List[str], replacements: List[Tuple[int, int, List[str]]]) -> List[str]:
    result = list(lines)
    for start_index, old_len, new_lines in reversed(replacements):
        for _ in range(old_len):
            if start_index < len(result):
                del result[start_index]
        for i, nl in enumerate(new_lines):
            result.insert(start_index + i, nl)
    return result


def apply_update_hunk(
    file_path: str,
    chunks: List[UpdateFileChunk],
    *,
    read_file: Callable[[str], str],
) -> str:
    try:
        original_contents = read_file(file_path)
    except Exception as err:
        raise ValueError(f"Failed to read file to update {file_path}: {err}") from err

    original_lines = original_contents.split("\n")
    if original_lines and original_lines[-1] == "":
        original_lines.pop()

    replacements = _compute_replacements(original_lines, file_path, chunks)
    new_lines = _apply_replacements(original_lines, replacements)
    if not new_lines or new_lines[-1] != "":
        new_lines = [*new_lines, ""]
    return "\n".join(new_lines)
