"use client";

import Image from "next/image";
import { useTheme } from "next-themes";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  callRpc,
  getAgentSessionHistory,
  getGatewayBaseUrl,
  listAgents,
  type AgentWsEvent,
  type ListedAgent,
} from "@/lib/gateway";
import { useGatewayWs } from "@/lib/gateway-ws-context";
import { useI18n } from "@/lib/i18n";
import { isTauri } from "@/lib/tauri";
import { ChatThinkToolCheckbox } from "@/components/ChatThinkToolCheckbox";

export type ToolTraceRow = {
  id: string;
  name: string;
  state: "running" | "done" | "error";
  preview?: string;
  elapsedMs?: number;
};

export type PlannedToolCall = { name: string; arguments_preview?: string };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  reasoning?: string;
  step?: string;
  runId?: string;
  streaming?: boolean;
  /** 网关 tool 流：开始 / 结束 / 错误 的摘要，便于看工具返回与耗时 */
  toolTraces?: ToolTraceRow[];
  /** 网关 llm 流：本轮模型计划调用的工具（预览） */
  plannedToolCalls?: PlannedToolCall[];
};

function formatToolResultPreview(r: unknown): string {
  if (r == null) return "";
  if (typeof r === "string") return r.length > 6000 ? `${r.slice(0, 6000)}…` : r;
  try {
    const s = JSON.stringify(r, null, 0);
    return s.length > 6000 ? `${s.slice(0, 6000)}…` : s;
  } catch {
    return String(r).slice(0, 6000);
  }
}

function upsertToolTrace(
  traces: ToolTraceRow[] | undefined,
  toolCallId: string,
  patch: Partial<ToolTraceRow> & { name?: string }
): ToolTraceRow[] {
  const list = traces ? [...traces] : [];
  const idx = list.findIndex((t) => t.id === toolCallId);
  const base: ToolTraceRow =
    idx >= 0
      ? list[idx]
      : {
          id: toolCallId,
          name: (patch.name || "?").trim() || "?",
          state: "running",
        };
  const next: ToolTraceRow = {
    ...base,
    ...patch,
    name: (patch.name ?? base.name).trim() || base.name,
  };
  if (idx >= 0) list[idx] = next;
  else list.push(next);
  return list;
}

function newId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `m-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

type ChatPanelProps = {
  /** Bump to reset session + messages when opening a fresh task dialog */
  sessionResetKey?: number;
  /** Pre-fill target agent (from My Agents) */
  initialAgentId?: string;
  /** Optional title row (e.g. dialog header lives outside) */
  showTopBar?: boolean;
  onClose?: () => void;
};

export function ChatPanel({
  sessionResetKey = 0,
  initialAgentId,
  showTopBar = true,
  onClose,
}: ChatPanelProps) {
  const { t, locale, setLocale } = useI18n();
  const { theme, setTheme } = useTheme();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const { subscribe, connectionState } = useGatewayWs();
  const [agentId, setAgentId] = useState(initialAgentId?.trim() || "main");
  const [sessionKey, setSessionKey] = useState("desktop-app");
  const [sessionId, setSessionId] = useState("");
  const [sessionReady, setSessionReady] = useState(true);
  /** 与网关 AgentRunParams.reasoning_level 对齐：stream 时才会 WS 推送 think/推理块 */
  const [streamReasoning, setStreamReasoning] = useState(true);
  const [assistantAvatarSrc, setAssistantAvatarSrc] = useState("/icons/robot.png");
  const [listedAgents, setListedAgents] = useState<ListedAgent[]>([]);
  const [agentsListLoading, setAgentsListLoading] = useState(false);
  const messagesWrapRef = useRef<HTMLElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  /** After opening chat / switching agent, pin to bottom once history is loaded. */
  const forceChatScrollBottomRef = useRef(false);

  const reloadSessionForAgent = useCallback(
    (nextAgentId: string) => {
      const id = nextAgentId.trim() || "main";
      setMessages([]);
      setBusy(false);
      setSessionReady(false);
      setSessionId("");
      const key = sessionKey.trim() || "desktop-app";
      void getAgentSessionHistory(id, key).then((r) => {
        if (!r.ok) {
          setSessionId(newId());
          setSessionReady(true);
          return;
        }
        const sid = r.sessionId?.trim();
        if (sid) {
          setSessionId(sid);
          setMessages(
            r.messages.map((m) => ({
              id: newId(),
              role: m.role,
              text: m.text,
            }))
          );
        } else {
          setSessionId(newId());
        }
        setSessionReady(true);
      });
    },
    [sessionKey]
  );

  useEffect(() => {
    forceChatScrollBottomRef.current = true;
  }, [sessionResetKey, initialAgentId]);

  useEffect(() => {
    setInput("");
    setBusy(false);
    const aid = initialAgentId?.trim() || "main";
    setAgentId(aid);
    const fromAgentsPanel = Boolean(initialAgentId?.trim());
    setMessages([]);
    if (fromAgentsPanel) {
      setSessionReady(false);
      setSessionId("");
    } else {
      setSessionReady(true);
      setSessionId(newId());
    }
  }, [sessionResetKey, initialAgentId]);

  useEffect(() => {
    let cancelled = false;
    setListedAgents([]);
    setAgentsListLoading(true);
    void listAgents().then((r) => {
      if (cancelled) return;
      setAgentsListLoading(false);
      if (r.ok) {
        const sorted = [...r.agents].sort((a, b) => a.agentId.localeCompare(b.agentId));
        setListedAgents(sorted);
      } else {
        setListedAgents([]);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [sessionResetKey]);

  useEffect(() => {
    if (!listedAgents.length) return;
    const ids = new Set(listedAgents.map((x) => x.agentId));
    const pref = initialAgentId?.trim();
    const nextId =
      pref && ids.has(pref) ? pref : ids.has(agentId) ? agentId : listedAgents[0].agentId;
    if (nextId !== agentId) {
      setAgentId(nextId);
      reloadSessionForAgent(nextId);
    }
  }, [listedAgents, sessionResetKey, initialAgentId, agentId, reloadSessionForAgent]);

  useEffect(() => {
    const aid = initialAgentId?.trim();
    if (!aid) return;

    let cancelled = false;
    setSessionReady(false);
    const key = sessionKey.trim() || "desktop-app";
    void getAgentSessionHistory(aid, key).then((r) => {
      if (cancelled) return;
      if (!r.ok) {
        setSessionId(newId());
        setSessionReady(true);
        return;
      }
      const sid = r.sessionId?.trim();
      if (sid) {
        setSessionId(sid);
        setMessages(
          r.messages.map((m) => ({
            id: newId(),
            role: m.role,
            text: m.text,
          }))
        );
      } else {
        setSessionId(newId());
      }
      setSessionReady(true);
    });

    return () => {
      cancelled = true;
    };
  }, [sessionResetKey, initialAgentId, sessionKey]);

  const handleAgentSelectChange = useCallback(
    (nextId: string) => {
      const id = nextId.trim();
      if (!id || id === agentId) return;
      setAgentId(id);
      reloadSessionForAgent(id);
    },
    [agentId, reloadSessionForAgent]
  );

  const agentSelectOptions: ListedAgent[] = useMemo(() => {
    const cur = (agentId || "").trim() || "main";
    if (listedAgents.length === 0) return [{ agentId: cur, configured: true }];
    const ids = new Set(listedAgents.map((a) => a.agentId));
    if (ids.has(cur)) return listedAgents;
    return [...listedAgents, { agentId: cur, configured: true }].sort((a, b) =>
      a.agentId.localeCompare(b.agentId)
    );
  }, [listedAgents, agentId]);

  useEffect(() => {
    let cancelled = false;
    const aid = (agentId || "").trim() || "main";
    void listAgents().then((r) => {
      if (!r.ok || cancelled) return;
      const row = r.agents.find((x) => x.agentId === aid);
      const av = row?.avatar?.trim();
      setAssistantAvatarSrc(
        av ? `/icons/headers/${encodeURIComponent(av)}` : "/icons/robot.png"
      );
    });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  useLayoutEffect(() => {
    if (!sessionReady || messages.length === 0) return;
    const el = messagesWrapRef.current;
    const end = messagesEndRef.current;
    if (!el || !end) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const nearBottom = distance < 160;
    if (forceChatScrollBottomRef.current || nearBottom) {
      requestAnimationFrame(() => {
        end.scrollIntoView({ block: "end" });
      });
    }
    forceChatScrollBottomRef.current = false;
  }, [messages, sessionReady]);

  /**
   * Apply an update to the assistant row for this run_id.
   * WS events often arrive before React applies runId from the RPC response; in that case
   * attach to the latest streaming assistant row that has no runId yet.
   */
  const updateAssistantForRun = useCallback(
    (runId: string, fn: (m: ChatMessage) => ChatMessage) => {
      if (!runId) return;
      setMessages((prev) => {
        const withIndex = [...prev].map((m, i) => ({ m, i }));
        const rev = [...withIndex].reverse();
        const byRun = rev.find(
          (x) => x.m.role === "assistant" && x.m.runId === runId
        );
        const pending = rev.find(
          (x) =>
            x.m.role === "assistant" &&
            x.m.streaming === true &&
            !String(x.m.runId || "").trim()
        );
        const hit = byRun ?? pending;
        if (!hit) return prev;
        const idx = hit.i;
        const next = [...prev];
        const merged: ChatMessage = { ...next[idx], runId };
        next[idx] = fn(merged);
        return next;
      });
    },
    []
  );

  useEffect(() => {
    return subscribe((payload: AgentWsEvent) => {
      const runId = payload.run_id || (payload.data?.run_id as string) || "";
      const stream = payload.stream;
      const data = payload.data || {};

      if (stream === "lifecycle" && runId) {
        const phase = data.phase as string;
        if (phase === "start") {
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("stepThinking"),
            text: "",
            streaming: true,
          }));
        }
        if (phase === "end" || phase === "error") {
          updateAssistantForRun(runId, (m) => ({
            ...m,
            streaming: false,
            step: undefined,
          }));
          setBusy(false);
        }
        return;
      }

      if (stream === "tool" && runId) {
        const typ = data.type as string;
        const name = String(data.tool_name || "?");
        const tcid = String(data.tool_call_id || data.toolCallId || name || newId());
        if (typ === "start") {
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("stepCallingTool", { name }),
            toolTraces: upsertToolTrace(m.toolTraces, tcid, {
              name,
              state: "running",
            }),
          }));
        } else if (typ === "processing") {
          const elapsed = data.elapsed_ms ?? data.elapsedMs;
          const sec =
            typeof elapsed === "number" && Number.isFinite(elapsed)
              ? Math.max(0, Math.round(elapsed / 1000))
              : 0;
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("chatToolRunning", { name, seconds: sec }),
            toolTraces: upsertToolTrace(m.toolTraces, tcid, {
              name,
              state: "running",
              elapsedMs: typeof elapsed === "number" ? elapsed : undefined,
            }),
          }));
        } else if (typ === "end") {
          const ok = data.success !== false;
          const preview = formatToolResultPreview(data.result);
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("stepToolDone", { name }),
            toolTraces: upsertToolTrace(m.toolTraces, tcid, {
              name,
              state: ok ? "done" : "error",
              preview: preview || undefined,
            }),
          }));
        } else if (typ === "error") {
          const err = String(data.error || "error");
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("stepToolDone", { name }),
            toolTraces: upsertToolTrace(m.toolTraces, tcid, {
              name,
              state: "error",
              preview: err,
            }),
          }));
        }
        return;
      }

      if (stream === "assistant" && runId) {
        if (data.reasoning != null) {
          const chunk = String(data.reasoning).trim();
          if (chunk) {
            updateAssistantForRun(runId, (m) => ({
              ...m,
              reasoning: (m.reasoning ? `${m.reasoning}\n\n` : "") + chunk,
            }));
          }
        }
        const text =
          data.text != null
            ? String(data.text)
            : data.delta != null
              ? String(data.delta)
              : "";
        const textTrimmed = text.trim();
        const isFinal = data.final === true;
        if (!textTrimmed) {
          if (isFinal) {
            updateAssistantForRun(runId, (m) => ({
              ...m,
              step: undefined,
              streaming: false,
            }));
          }
          return;
        }
        if (textTrimmed === "Processing..." || textTrimmed === "思考中…") {
          updateAssistantForRun(runId, (m) => ({
            ...m,
            step: t("stepThinking"),
          }));
          return;
        }
        updateAssistantForRun(runId, (m) => ({
          ...m,
          step: undefined,
          text: isFinal ? textTrimmed : (m.text || "") + textTrimmed,
        }));
      }

      if (stream === "llm" && runId) {
        const rawCalls = data.tool_calls ?? data.toolCalls;
        if (Array.isArray(rawCalls) && rawCalls.length) {
          const planned: PlannedToolCall[] = [];
          for (const c of rawCalls) {
            if (!c || typeof c !== "object") continue;
            const o = c as Record<string, unknown>;
            planned.push({
              name: String(o.name ?? "?"),
              arguments_preview:
                typeof o.arguments_preview === "string"
                  ? o.arguments_preview
                  : typeof o.argumentsPreview === "string"
                    ? o.argumentsPreview
                    : undefined,
            });
          }
          if (planned.length) {
            updateAssistantForRun(runId, (m) => ({
              ...m,
              plannedToolCalls: planned,
            }));
          }
        }
        if (data.thinking != null && String(data.thinking).trim()) {
          const chunk = String(data.thinking).trim();
          updateAssistantForRun(runId, (m) => ({
            ...m,
            reasoning: (m.reasoning ? `${m.reasoning}\n\n` : "") + chunk,
          }));
        }
        const content =
          data.content != null
            ? String(data.content)
            : data.text != null
              ? String(data.text)
              : "";
        const c = content.trim();
        if (c) {
          updateAssistantForRun(runId, (m) => {
            const hasText = Boolean((m.text || "").trim());
            return {
              ...m,
              step: undefined,
              text: hasText ? m.text : c,
            };
          });
        }
      }
    });
  }, [subscribe, t, updateAssistantForRun]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || busy || !sessionReady) return;
    setInput("");
    setBusy(true);
    setMessages((prev) => [
      ...prev,
      { id: newId(), role: "user", text, runId: undefined },
    ]);

    const idem = `desktop-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;

    const params: Record<string, unknown> = {
      message: text,
      sessionKey: sessionKey.trim() || "desktop-app",
      agentId: agentId.trim() || "main",
      idempotencyKey: idem,
      channel: "desktop",
      reasoningLevel: streamReasoning ? "stream" : "off",
    };
    if (sessionId.trim()) {
      params.sessionId = sessionId.trim();
    }

    setMessages((prev) => [
      ...prev,
      {
        id: newId(),
        role: "assistant",
        text: "",
        runId: undefined,
        streaming: true,
        step: t("stepThinking"),
      },
    ]);

    try {
      const json = await callRpc("agent", params);

      const runId =
        (json.runId as string) ||
        (json.payload && (json.payload.runId as string)) ||
        "";
      if (!json.ok || !runId) {
        const err = json.error?.message || t("errorRpc");
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            next[next.length - 1] = {
              ...last,
              text: err,
              streaming: false,
              step: undefined,
            };
          }
          return next;
        });
        setBusy(false);
        return;
      }

      const sidBack = json.payload?.sessionId;
      if (typeof sidBack === "string" && sidBack.trim()) {
        setSessionId(sidBack.trim());
      }

      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          next[next.length - 1] = { ...last, runId };
        }
        return next;
      });

      // Fallback: if the UI missed WS events (late mount / reconnect), block until run completes.
      void (async () => {
        const rid = runId;
        try {
          const w = await callRpc("agent.wait", {
            runId: rid,
            timeoutMs: 180_000,
          });
          if (!w.ok || !w.payload) {
            setBusy(false);
            return;
          }
          const reply = w.payload.replyText;
          if (typeof reply === "string" && reply.trim()) {
            setMessages((prev) => {
              const withIndex = [...prev].map((m, i) => ({ m, i }));
              const rev = [...withIndex].reverse();
              const hit = rev.find(
                (x) => x.m.role === "assistant" && x.m.runId === rid
              );
              if (!hit) return prev;
              const cur = hit.m;
              if ((cur.text || "").trim() && cur.streaming === false) {
                return prev;
              }
              const next = [...prev];
              next[hit.i] = {
                ...cur,
                text: reply.trim(),
                streaming: false,
                step: undefined,
              };
              return next;
            });
          }
          const st = String(w.payload.status || "");
          if (st === "ok" || st === "error" || st === "timeout") {
            setBusy(false);
            if (st === "error" && w.payload.error != null) {
              const er = w.payload.error;
              const errMsg =
                typeof er === "string"
                  ? er
                  : typeof er === "object" &&
                      er !== null &&
                      "message" in er
                    ? String((er as { message?: unknown }).message || "")
                    : t("errorRpc");
              if (errMsg) {
                setMessages((prev) => {
                  const withIndex = [...prev].map((m, i) => ({ m, i }));
                  const rev = [...withIndex].reverse();
                  const hit = rev.find(
                    (x) => x.m.role === "assistant" && x.m.runId === rid
                  );
                  if (!hit) return prev;
                  const cur = hit.m;
                  if ((cur.text || "").trim()) return prev;
                  const next = [...prev];
                  next[hit.i] = {
                    ...cur,
                    text: errMsg,
                    streaming: false,
                    step: undefined,
                  };
                  return next;
                });
              }
            }
          }
        } catch {
          setBusy(false);
        }
      })();
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          next[next.length - 1] = {
            ...last,
            text: String(e),
            streaming: false,
            step: undefined,
          };
        }
        return next;
      });
      setBusy(false);
    }
  };

  const newSession = () => {
    setSessionId(newId());
    setMessages([]);
    setSessionReady(true);
  };

  const base = getGatewayBaseUrl();
  const inputBlocked = busy || !sessionReady;
  const connLabel =
    connectionState === "connected"
      ? t("connected")
      : connectionState === "reconnecting"
        ? t("reconnecting")
        : connectionState === "connecting"
          ? t("reconnecting")
          : t("disconnected");

  return (
    <div className="flex flex-col h-full min-h-0 w-full max-w-3xl mx-auto px-4 sm:px-6">
      {showTopBar ? (
        <header className="flex flex-wrap items-center gap-2 py-3 border-b border-[var(--border)] shrink-0">
          <div className="flex flex-col min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight truncate">
              {t("newTask")}
            </h2>
            <p className="text-xs text-[var(--muted)] truncate">{t("subtitle")}</p>
          </div>
          <span
            className={`text-xs px-2 py-0.5 rounded-full border border-[var(--border)] ${
              connectionState === "connected"
                ? "text-emerald-500"
                : "text-[var(--muted)]"
            }`}
            title={base}
          >
            {connLabel}
          </span>
          {isTauri() && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--panel)] border border-[var(--border)] text-[var(--muted)]">
              Native
            </span>
          )}
          <div className="flex items-center gap-1">
            <span className="text-xs text-[var(--muted)]">{t("language")}</span>
            <button
              type="button"
              className={`text-xs px-2 py-1 rounded border border-[var(--border)] ${
                locale === "en" ? "bg-[var(--accent)] text-white" : ""
              }`}
              onClick={() => setLocale("en")}
            >
              EN
            </button>
            <button
              type="button"
              className={`text-xs px-2 py-1 rounded border border-[var(--border)] ${
                locale === "zh-CN" ? "bg-[var(--accent)] text-white" : ""
              }`}
              onClick={() => setLocale("zh-CN")}
            >
              中文
            </button>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className={`text-xs px-2 py-1 rounded border border-[var(--border)] ${
                theme === "light" ? "bg-[var(--accent)] text-white" : ""
              }`}
              onClick={() => setTheme("light")}
            >
              {t("themeLight")}
            </button>
            <button
              type="button"
              className={`text-xs px-2 py-1 rounded border border-[var(--border)] ${
                theme === "dark" ? "bg-[var(--accent)] text-white" : ""
              }`}
              onClick={() => setTheme("dark")}
            >
              {t("themeDark")}
            </button>
          </div>
          <button
            type="button"
            className="text-xs px-2 py-1 rounded border border-[var(--border)] text-[var(--muted)]"
            onClick={newSession}
          >
            {t("newChat")}
          </button>
          {onClose ? (
            <button
              type="button"
              className="text-xs px-2 py-1 rounded border border-[var(--border)] text-[var(--muted)]"
              onClick={onClose}
            >
              {t("closeDialog")}
            </button>
          ) : null}
        </header>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 py-2 text-xs shrink-0">
        <label className="flex flex-col gap-0.5 sm:col-span-1">
          <span className="text-[var(--muted)]">{t("gatewayUrl")}</span>
          <code className="truncate px-2 py-1 rounded bg-[var(--panel)] border border-[var(--border)]">
            {base}
          </code>
        </label>
        <label className="flex flex-col gap-0.5">
          <span
            className="text-[var(--muted)]"
            title={agentsListLoading ? t("agentsLoading") : undefined}
          >
            {t("agentId")}
          </span>
          <select
            className="px-2 py-1 rounded bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] min-w-0 max-w-full"
            value={
              agentSelectOptions.some((a) => a.agentId === agentId)
                ? agentId
                : (agentSelectOptions[0]?.agentId ?? "main")
            }
            onChange={(e) => handleAgentSelectChange(e.target.value)}
            disabled={busy || agentsListLoading}
          >
            {agentSelectOptions.map((a) => (
              <option key={a.agentId} value={a.agentId}>
                {a.agentId}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[var(--muted)]">{t("sessionKey")}</span>
          <input
            className="px-2 py-1 rounded bg-[var(--panel)] border border-[var(--border)] text-[var(--text)]"
            value={sessionKey}
            onChange={(e) => setSessionKey(e.target.value)}
            disabled={busy}
          />
        </label>
      </div>

      {messages.length === 0 ? (
        <div className="flex flex-1 flex-col min-h-0 items-center justify-center px-2 py-8 gap-6">
          <div className="flex flex-row flex-wrap items-center justify-center gap-3 px-2">
            <Image
              src="/icons/planet.png"
              alt=""
              width={48}
              height={48}
              className="h-12 w-12 shrink-0 rounded-xl object-contain opacity-95"
            />
            <p className="text-base sm:text-lg font-medium text-[var(--text)] tracking-tight">
              {t("chatWorkPrompt")}
            </p>
          </div>
          <div className="flex w-full max-w-xl mx-auto gap-2 items-stretch justify-center">
            <textarea
              className="flex-1 min-h-[48px] max-h-40 min-w-0 px-3 py-2.5 rounded-xl bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-sm resize-y shadow-sm"
              placeholder={t("placeholder")}
              value={input}
              disabled={inputBlocked}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
                }
              }}
              rows={3}
            />
            <div className="flex flex-col justify-end gap-2 shrink-0">
              <ChatThinkToolCheckbox
                checked={streamReasoning}
                onChange={setStreamReasoning}
                disabled={busy}
                t={t}
              />
              <button
                type="button"
                className="shrink-0 px-4 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-50 min-h-[44px]"
                disabled={inputBlocked || !input.trim()}
                onClick={() => void sendMessage()}
              >
                {t("send")}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <>
          <main
            ref={messagesWrapRef}
            className="flex-1 overflow-y-auto py-3 space-y-3 min-h-0 w-full"
          >
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex gap-2 max-w-[min(100%,42rem)] items-start ${
                  m.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                }`}
              >
                <div className="shrink-0 pt-1">
                  <Image
                    src={
                      m.role === "user" ? "/icons/planet.png" : assistantAvatarSrc
                    }
                    alt=""
                    width={32}
                    height={32}
                    className="h-8 w-8 rounded-lg object-cover border border-[var(--border)]"
                  />
                </div>
                <div
                  className={`min-w-0 flex-1 rounded-lg px-3 py-2 ${
                    m.role === "user"
                      ? "bg-[var(--user-bg)] text-[var(--text)]"
                      : "bg-[var(--assistant-bg)] border border-[var(--border)]"
                  }`}
                >
                  <div className="text-[10px] uppercase tracking-wide text-[var(--muted)] mb-1">
                    {m.role === "user" ? t("metaYou") : t("metaAssistant")}
                    {m.runId ? ` · ${m.runId.slice(0, 8)}…` : ""}
                  </div>
                  {m.step ? (
                    <div className="text-xs text-[var(--muted)] mb-1">{m.step}</div>
                  ) : null}
                  {m.plannedToolCalls && m.plannedToolCalls.length ? (
                    <div className="text-[10px] text-[var(--muted)] border border-[var(--border)] rounded-md p-2 mb-2 space-y-1 bg-[var(--panel)]/40">
                      <div className="font-semibold text-[var(--text)]">{t("chatToolPlanned")}</div>
                      <ul className="list-disc pl-4 space-y-0.5 font-mono break-all">
                        {m.plannedToolCalls.map((p, i) => (
                          <li key={`${p.name}-${i}`}>
                            {p.name}
                            {p.arguments_preview
                              ? ` — ${p.arguments_preview.length > 200 ? `${p.arguments_preview.slice(0, 200)}…` : p.arguments_preview}`
                              : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {m.reasoning ? (
                    <div className="text-xs text-[var(--muted)] border-l-2 border-[var(--accent)] pl-2 mb-2 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      <span className="font-medium">{t("reasoning")}: </span>
                      {m.reasoning}
                    </div>
                  ) : null}
                  {m.toolTraces && m.toolTraces.length ? (
                    <div className="text-[10px] border border-[var(--border)] rounded-md p-2 mb-2 bg-[var(--panel)]/50 max-h-52 overflow-y-auto">
                      <div className="font-semibold text-[var(--muted)] mb-1">{t("chatToolActivity")}</div>
                      <div className="space-y-2">
                        {m.toolTraces.map((tr) => (
                          <div key={tr.id} className="border-b border-[var(--border)]/60 last:border-0 pb-2 last:pb-0">
                            <div className="flex flex-wrap gap-2 items-baseline font-mono text-[10px]">
                              <span
                                className={
                                  tr.state === "error"
                                    ? "text-red-400"
                                    : tr.state === "done"
                                      ? "text-emerald-400"
                                      : "text-amber-400"
                                }
                              >
                                {tr.state === "running" ? "…" : tr.state === "done" ? "✓" : "✗"}{" "}
                                {tr.name}
                              </span>
                              {tr.elapsedMs != null ? (
                                <span className="text-[var(--muted)]">
                                  {(tr.elapsedMs / 1000).toFixed(1)}s
                                </span>
                              ) : null}
                            </div>
                            {tr.preview ? (
                              <pre className="mt-1 whitespace-pre-wrap break-words text-[9px] leading-relaxed text-[var(--text)] opacity-90">
                                {tr.preview}
                              </pre>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="text-sm whitespace-pre-wrap">{m.text}</div>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} className="h-px shrink-0" aria-hidden />
          </main>

          <footer className="py-3 border-t border-[var(--border)] shrink-0 w-full">
            <div className="flex w-full max-w-xl mx-auto gap-2 items-stretch">
              <textarea
                className="flex-1 min-h-[44px] max-h-40 min-w-0 px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-sm resize-y"
                placeholder={t("placeholder")}
                value={input}
                disabled={inputBlocked}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
              />
              <div className="flex flex-col justify-end gap-2 shrink-0">
                <ChatThinkToolCheckbox
                  checked={streamReasoning}
                  onChange={setStreamReasoning}
                  disabled={busy}
                  t={t}
                />
                <button
                  type="button"
                  className="shrink-0 px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-50 min-h-[40px]"
                  disabled={inputBlocked || !input.trim()}
                  onClick={() => void sendMessage()}
                >
                  {t("send")}
                </button>
              </div>
            </div>
          </footer>
        </>
      )}
    </div>
  );
}
