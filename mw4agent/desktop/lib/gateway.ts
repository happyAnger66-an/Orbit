/**
 * HTTP JSON-RPC client for mw4agent Gateway (`POST /rpc`).
 * Base URL: `NEXT_PUBLIC_GATEWAY_URL` or http://127.0.0.1:18790
 */

export function getGatewayBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_GATEWAY_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/+$/, "");
  }
  return "http://127.0.0.1:18790";
}

export function getGatewayWsUrl(): string {
  const base = getGatewayBaseUrl();
  try {
    const u = new URL(base);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/ws";
    u.search = "";
    u.hash = "";
    return u.toString().replace(/\/+$/, "");
  } catch {
    return base.replace(/^http/, "ws").replace(/\/+$/, "") + "/ws";
  }
}

export type RpcResult = {
  id?: string;
  ok: boolean;
  payload?: Record<string, unknown>;
  error?: { code?: string; message?: string };
  runId?: string;
};

function newRpcId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `rpc-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

export async function callRpc(
  method: string,
  params: Record<string, unknown>
): Promise<RpcResult> {
  const base = getGatewayBaseUrl();
  const body = JSON.stringify({
    id: newRpcId(),
    method,
    params,
  });
  try {
    const res = await fetch(`${base}/rpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    if (!res.ok) {
      return {
        ok: false,
        error: {
          code: "http_error",
          message: `HTTP ${res.status}: ${res.statusText}`,
        },
      };
    }
    return (await res.json()) as RpcResult;
  } catch (e) {
    const msg =
      e instanceof TypeError && String(e.message).includes("fetch")
        ? "Network error: gateway unreachable (check NEXT_PUBLIC_GATEWAY_URL and that the gateway is running)"
        : e instanceof Error
          ? e.message
          : String(e);
    return {
      ok: false,
      error: { code: "network_error", message: msg },
    };
  }
}

export type AgentWsEvent = {
  run_id: string;
  stream: string;
  data: Record<string, unknown>;
  seq?: number;
  ts?: number;
};

export type ListedAgent = {
  agentId: string;
  configured?: boolean;
  agentDir?: string;
  workspaceDir?: string;
  sessionsFile?: string;
  /** Basename under ``/icons/headers/`` (desktop UI). */
  avatar?: string;
  createdAt?: number;
  updatedAt?: number;
  runStatus?: {
    state?: string;
    activeRuns?: number;
    lastRun?: unknown;
  };
};

export type ListAgentsResult =
  | { ok: true; agents: ListedAgent[] }
  | { ok: false; error?: string };

export async function listAgents(): Promise<ListAgentsResult> {
  const r = await callRpc("agents.list", {});
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.list failed" };
  }
  const agents = (r.payload.agents as ListedAgent[]) ?? [];
  return { ok: true, agents };
}

export type AgentSessionHistoryMessage = {
  role: "user" | "assistant";
  text: string;
};

export type AgentSessionHistoryResult =
  | {
      ok: true;
      sessionId: string | null;
      messages: AgentSessionHistoryMessage[];
    }
  | { ok: false; error?: string };

/** Load latest desktop session transcript for an agent (continue chat from My Agents). */
export async function getAgentSessionHistory(
  agentId: string,
  sessionKey = "desktop-app"
): Promise<AgentSessionHistoryResult> {
  const r = await callRpc("agent.session.history", {
    agentId: (agentId || "").trim() || "main",
    sessionKey: (sessionKey || "").trim() || "desktop-app",
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agent.session.history failed" };
  }
  const sessionId =
    typeof r.payload.sessionId === "string" ? r.payload.sessionId.trim() || null : null;
  const raw = r.payload.messages;
  const messages: AgentSessionHistoryMessage[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!item || typeof item !== "object") continue;
      const role = (item as { role?: string }).role;
      const text = (item as { text?: string }).text;
      if (role !== "user" && role !== "assistant") continue;
      if (typeof text !== "string") continue;
      messages.push({ role, text });
    }
  }
  return { ok: true, sessionId, messages };
}

export type ListedSkill = {
  name: string;
  source?: string;
  description?: string;
  location?: string;
};

export type ListSkillsResult =
  | {
      ok: true;
      skills: ListedSkill[];
      count: number;
      version?: string;
      sources: { name: string; count: number }[];
      filteredOut?: string[];
      promptTruncated?: boolean;
      promptCompact?: boolean;
    }
  | { ok: false; error?: string };

export async function listSkills(
  workspaceDir?: string
): Promise<ListSkillsResult> {
  const params: Record<string, unknown> = {};
  if (workspaceDir?.trim()) {
    params.workspaceDir = workspaceDir.trim();
  }
  const r = await callRpc("skills.list", params);
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "skills.list failed" };
  }
  const p = r.payload;
  return {
    ok: true,
    skills: (p.skills as ListedSkill[]) ?? [],
    count: Number(p.count ?? 0),
    version: typeof p.version === "string" ? p.version : undefined,
    sources: (p.sources as { name: string; count: number }[]) ?? [],
    filteredOut: (p.filteredOut as string[]) ?? [],
    promptTruncated: Boolean(p.promptTruncated),
    promptCompact: Boolean(p.promptCompact),
  };
}

export type ResolveAgentDefaultsResult =
  | { ok: true; agentId: string; agentDir: string; workspaceDir: string }
  | { ok: false; error?: string };

export async function resolveAgentDefaults(
  agentId: string
): Promise<ResolveAgentDefaultsResult> {
  const r = await callRpc("agents.resolve_defaults", {
    agentId: agentId.trim() || "new-agent",
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message };
  }
  const p = r.payload;
  return {
    ok: true,
    agentId: String(p.agentId ?? ""),
    agentDir: String(p.agentDir ?? ""),
    workspaceDir: String(p.workspaceDir ?? ""),
  };
}

export type CreateAgentBody = {
  agentId: string;
  workspaceDir?: string;
  /** Basename only; file must exist under ``public/icons/headers``. */
  avatar?: string;
  llm?: {
    provider?: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    thinking_level?: string;
  };
};

export type CreateAgentResult =
  | { ok: true; agentId: string; agentDir: string; workspaceDir: string }
  | { ok: false; error?: string };

export async function createAgent(body: CreateAgentBody): Promise<CreateAgentResult> {
  const params: Record<string, unknown> = {
    agentId: body.agentId.trim(),
  };
  if (body.workspaceDir?.trim()) {
    params.workspaceDir = body.workspaceDir.trim();
  }
  if (body.llm && Object.keys(body.llm).length > 0) {
    params.llm = body.llm;
  }
  if (body.avatar?.trim()) {
    params.avatar = body.avatar.trim();
  }
  const r = await callRpc("agents.create", params);
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.create failed" };
  }
  const p = r.payload;
  return {
    ok: true,
    agentId: String(p.agentId ?? ""),
    agentDir: String(p.agentDir ?? ""),
    workspaceDir: String(p.workspaceDir ?? ""),
  };
}

export type SetAgentAvatarResult =
  | { ok: true; agentId: string; avatar?: string }
  | { ok: false; error?: string };

/** Set or clear (empty string) per-agent avatar basename. */
export async function setAgentAvatar(
  agentId: string,
  avatar: string
): Promise<SetAgentAvatarResult> {
  const r = await callRpc("agents.set_avatar", {
    agentId: agentId.trim(),
    avatar: avatar ?? "",
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.set_avatar failed" };
  }
  const p = r.payload;
  const av = p.avatar;
  return {
    ok: true,
    agentId: String(p.agentId ?? ""),
    avatar:
      av !== undefined && av !== null && String(av).trim()
        ? String(av).trim()
        : undefined,
  };
}

export type DeleteAgentResult =
  | { ok: true; deleted: boolean }
  | { ok: false; error?: string };

export async function deleteAgent(agentId: string): Promise<DeleteAgentResult> {
  const r = await callRpc("agents.delete", { agentId: agentId.trim() });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.delete failed" };
  }
  return { ok: true, deleted: Boolean(r.payload.deleted) };
}

export type ReadAgentWorkspaceFileResult =
  | { ok: true; path: string; text: string; missing: boolean }
  | { ok: false; error?: string };

export async function readAgentWorkspaceFile(
  agentId: string,
  path: string
): Promise<ReadAgentWorkspaceFileResult> {
  const r = await callRpc("agents.workspace_file.read", {
    agentId: agentId.trim(),
    path: path.trim(),
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.workspace_file.read failed" };
  }
  return {
    ok: true,
    path: String(r.payload.path ?? path),
    text: String(r.payload.text ?? ""),
    missing: Boolean(r.payload.missing),
  };
}

export type WriteAgentWorkspaceFileResult =
  | { ok: true; path: string; saved: boolean }
  | { ok: false; error?: string };

export async function writeAgentWorkspaceFile(
  agentId: string,
  path: string,
  text: string
): Promise<WriteAgentWorkspaceFileResult> {
  const r = await callRpc("agents.workspace_file.write", {
    agentId: agentId.trim(),
    path: path.trim(),
    text,
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "agents.workspace_file.write failed" };
  }
  return {
    ok: true,
    path: String(r.payload.path ?? path),
    saved: Boolean(r.payload.saved),
  };
}

export type ListLlmProvidersResult =
  | { ok: true; providers: string[] }
  | { ok: false; error?: string };

export async function listLlmProviders(): Promise<ListLlmProvidersResult> {
  const r = await callRpc("llm.providers.list", {});
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message };
  }
  return { ok: true, providers: (r.payload.providers as string[]) ?? [] };
}

export type OrchMessage = {
  id: string;
  ts: number;
  round: number;
  speaker: string;
  role: "user" | "assistant";
  text: string;
};

export type OrchestrateRunBody = {
  sessionKey: string;
  name?: string;
  message: string;
  participants: string[];
  maxRounds?: number;
  strategy?: string;
  routerLlm?: {
    provider?: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    thinking_level?: string;
  };
  idempotencyKey: string;
};

export type OrchestrateRunResult =
  | { ok: true; orchId: string; status: string; sessionKey: string }
  | { ok: false; error?: string };

export async function orchestrateRun(
  body: OrchestrateRunBody
): Promise<OrchestrateRunResult> {
  const r = await callRpc("orchestrate.run", {
    sessionKey: body.sessionKey,
    name: body.name,
    message: body.message,
    participants: body.participants,
    maxRounds: body.maxRounds,
    strategy: body.strategy,
    routerLlm: body.routerLlm,
    idempotencyKey: body.idempotencyKey,
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.run failed" };
  }
  return {
    ok: true,
    orchId: String(r.payload.orchId ?? ""),
    status: String(r.payload.status ?? ""),
    sessionKey: String(r.payload.sessionKey ?? body.sessionKey),
  };
}

export type OrchestrateCreateBody = {
  sessionKey: string;
  name?: string;
  participants: string[];
  maxRounds?: number;
  strategy?: string;
  routerLlm?: {
    provider?: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    thinking_level?: string;
  };
  idempotencyKey: string;
};

export type OrchestrateCreateResult =
  | { ok: true; orchId: string; status: string; sessionKey: string }
  | { ok: false; error?: string };

export async function orchestrateCreate(
  body: OrchestrateCreateBody
): Promise<OrchestrateCreateResult> {
  const r = await callRpc("orchestrate.create", {
    sessionKey: body.sessionKey,
    name: body.name,
    participants: body.participants,
    maxRounds: body.maxRounds,
    strategy: body.strategy,
    routerLlm: body.routerLlm,
    idempotencyKey: body.idempotencyKey,
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.create failed" };
  }
  return {
    ok: true,
    orchId: String(r.payload.orchId ?? ""),
    status: String(r.payload.status ?? ""),
    sessionKey: String(r.payload.sessionKey ?? body.sessionKey),
  };
}

export type OrchestrateListItem = {
  orchId: string;
  name?: string;
  status: string;
  sessionKey: string;
  strategy?: string;
  maxRounds?: number;
  participants?: string[];
  currentRound?: number;
  createdAt?: number;
  updatedAt?: number;
  error?: string;
};

export type OrchestrateListResult =
  | { ok: true; orchestrations: OrchestrateListItem[] }
  | { ok: false; error?: string };

export async function orchestrateList(): Promise<OrchestrateListResult> {
  const r = await callRpc("orchestrate.list", {});
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.list failed" };
  }
  return {
    ok: true,
    orchestrations: (r.payload.orchestrations as OrchestrateListItem[]) ?? [],
  };
}

export type OrchestrateDeleteResult =
  | { ok: true; deleted: boolean }
  | { ok: false; error?: string };

export async function orchestrateDelete(orchId: string): Promise<OrchestrateDeleteResult> {
  const r = await callRpc("orchestrate.delete", { orchId: orchId.trim() });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.delete failed" };
  }
  return { ok: true, deleted: Boolean(r.payload.deleted) };
}

export type OrchestrateGetResult =
  | {
      ok: true;
      orchId: string;
      sessionKey: string;
      status: string;
      currentRound: number;
      maxRounds: number;
      participants: string[];
      messages: OrchMessage[];
      name?: string;
      strategy?: string;
      error?: string;
      createdAt?: number;
      updatedAt?: number;
    }
  | { ok: false; error?: string };

export async function orchestrateGet(orchId: string): Promise<OrchestrateGetResult> {
  const r = await callRpc("orchestrate.get", { orchId: orchId.trim() });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.get failed" };
  }
  const p = r.payload;
  return {
    ok: true,
    orchId: String(p.orchId ?? ""),
    sessionKey: String(p.sessionKey ?? ""),
    status: String(p.status ?? ""),
    currentRound: Number(p.currentRound ?? 0),
    maxRounds: Number(p.maxRounds ?? 0),
    participants: (p.participants as string[]) ?? [],
    messages: (p.messages as OrchMessage[]) ?? [],
    name: typeof p.name === "string" ? p.name : undefined,
    strategy: typeof p.strategy === "string" ? p.strategy : undefined,
    error: typeof p.error === "string" ? p.error : undefined,
    createdAt: typeof p.createdAt === "number" ? p.createdAt : undefined,
    updatedAt: typeof p.updatedAt === "number" ? p.updatedAt : undefined,
  };
}

export type OrchestrateSendResult =
  | { ok: true; orchId: string; status: string; currentRound: number }
  | { ok: false; error?: string };

export async function orchestrateSend(
  orchId: string,
  message: string,
  idempotencyKey: string
): Promise<OrchestrateSendResult> {
  const r = await callRpc("orchestrate.send", {
    orchId: orchId.trim(),
    message,
    idempotencyKey,
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.send failed" };
  }
  return {
    ok: true,
    orchId: String(r.payload.orchId ?? ""),
    status: String(r.payload.status ?? ""),
    currentRound: Number(r.payload.currentRound ?? 0),
  };
}

export type OrchestrateWaitResult =
  | { ok: true; orchId: string; status: string; currentRound: number }
  | { ok: false; error?: string };

export async function orchestrateWait(
  orchId: string,
  timeoutMs = 15_000
): Promise<OrchestrateWaitResult> {
  const r = await callRpc("orchestrate.wait", {
    orchId: orchId.trim(),
    timeoutMs,
  });
  if (!r.ok || !r.payload) {
    return { ok: false, error: r.error?.message || "orchestrate.wait failed" };
  }
  return {
    ok: true,
    orchId: String(r.payload.orchId ?? ""),
    status: String(r.payload.status ?? ""),
    currentRound: Number(r.payload.currentRound ?? 0),
  };
}
