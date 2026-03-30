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
  const res = await fetch(`${base}/rpc`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
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
