/**
 * If the cursor is inside an ``@token`` segment (token = ``[a-zA-Z0-9._-]*``), return its span.
 * ``@`` must be at string start or after whitespace.
 */
export function getMentionQueryAtCursor(
  value: string,
  cursor: number
): { start: number; query: string; end: number } | null {
  if (cursor < 0) return null;
  const before = value.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  if (at > 0 && !/\s/.test(before.charAt(at - 1))) return null;
  const after = before.slice(at + 1);
  if (!/^[a-zA-Z0-9._-]*$/.test(after)) return null;
  return { start: at, query: after, end: cursor };
}

/** Replace ``@[partial]`` up to ``end`` with ``@participantId `` (trailing space). */
export function insertMentionParticipant(
  value: string,
  range: { start: number; end: number },
  participantId: string
): { value: string; caret: number } {
  const before = value.slice(0, range.start);
  const after = value.slice(range.end);
  const insert = `@${participantId} `;
  const next = before + insert + after;
  return { value: next, caret: (before + insert).length };
}

/**
 * Parse `@agentId` in orchestration chat: first token that matches a participant (case-insensitive).
 * Returns the canonical id from the participants list.
 */
export function parseOrchestrateTargetAgent(
  text: string,
  participants: string[]
): string | undefined {
  const re = /@([a-zA-Z0-9._-]+)/g;
  const set = new Set(participants.map((p) => p.toLowerCase()));
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const token = m[1];
    const lower = token.toLowerCase();
    if (set.has(lower)) {
      const hit = participants.find((p) => p.toLowerCase() === lower);
      if (hit) return hit;
    }
  }
  return undefined;
}
