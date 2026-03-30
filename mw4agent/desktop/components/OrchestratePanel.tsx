"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listAgents,
  listLlmProviders,
  orchestrateCreate,
  orchestrateDelete,
  orchestrateGet,
  orchestrateList,
  orchestrateSend,
  type ListedAgent,
  type OrchMessage,
  type OrchestrateListItem,
} from "@/lib/gateway";
import { useI18n } from "@/lib/i18n";

function fmtTs(ts?: number): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return String(ts);
  }
}

function speakerColorClass(speaker: string): string {
  const s = (speaker || "").trim() || "unknown";
  // Stable hash -> pick a tailwind text color.
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  const palette = [
    "text-sky-400",
    "text-emerald-400",
    "text-amber-400",
    "text-fuchsia-400",
    "text-rose-400",
    "text-indigo-400",
    "text-cyan-400",
    "text-lime-400",
    "text-orange-400",
    "text-violet-400",
  ];
  return palette[h % palette.length];
}

function speakerCardClass(speaker: string): string {
  const s = (speaker || "").trim() || "unknown";
  if (s.toLowerCase() === "user") {
    return "bg-[var(--bg)]";
  }
  // Stable hash -> pick a subtle tinted background.
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  const palette = [
    "bg-sky-500/10",
    "bg-emerald-500/10",
    "bg-amber-500/10",
    "bg-fuchsia-500/10",
    "bg-rose-500/10",
    "bg-indigo-500/10",
    "bg-cyan-500/10",
    "bg-lime-500/10",
    "bg-orange-500/10",
    "bg-violet-500/10",
  ];
  return palette[h % palette.length];
}

export function OrchestratePanel({ autoOpenKey = 0 }: { autoOpenKey?: number }) {
  const { t } = useI18n();
  const [listedAgents, setListedAgents] = useState<ListedAgent[]>([]);
  const [orches, setOrches] = useState<OrchestrateListItem[]>([]);
  const [selectedOrchId, setSelectedOrchId] = useState<string>("");
  const [selected, setSelected] = useState<{
    orchId: string;
    name?: string;
    status: string;
    participants: string[];
    messages: OrchMessage[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createMaxRounds, setCreateMaxRounds] = useState("8");
  const [createStrategy, setCreateStrategy] = useState<"round_robin" | "router_llm">(
    "round_robin"
  );
  const [createParticipants, setCreateParticipants] = useState<string[]>(["main"]);
  const [addOpen, setAddOpen] = useState(false);
  const [providers, setProviders] = useState<string[]>([]);
  const [routerProvider, setRouterProvider] = useState("");
  const [routerModel, setRouterModel] = useState("");
  const [routerBaseUrl, setRouterBaseUrl] = useState("");
  const [routerApiKey, setRouterApiKey] = useState("");
  const [routerThinking, setRouterThinking] = useState("");

  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const messagesWrapRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const loadAgents = useCallback(async () => {
    const r = await listAgents();
    if (!r.ok) return;
    setListedAgents(r.agents);
  }, []);

  const avatarUrlForSpeaker = useCallback(
    (speaker: string) => {
      const s = (speaker || "").trim();
      if (!s || s.toLowerCase() === "user") return null;
      const row = listedAgents.find((x) => x.agentId === s);
      const av = row?.avatar?.trim();
      return av ? `/icons/headers/${encodeURIComponent(av)}` : null;
    },
    [listedAgents]
  );

  const loadOrches = useCallback(async () => {
    const r = await orchestrateList();
    if (!r.ok) return;
    setOrches(r.orchestrations);
  }, []);

  useEffect(() => {
    void loadAgents();
    void loadOrches();
  }, [loadAgents, loadOrches]);

  useEffect(() => {
    if (!createOpen) return;
    void listLlmProviders().then((r) => {
      if (r.ok) setProviders(r.providers);
      else setProviders(["echo", "openai", "deepseek", "vllm", "aliyun-bailian"]);
    });
  }, [createOpen]);

  const canSend = useMemo(() => input.trim().length > 0 && Boolean(selectedOrchId), [input, selectedOrchId]);

  const lastListRefreshRef = useRef(0);

  useEffect(() => {
    const orchId = selectedOrchId.trim();
    if (!orchId) return;
    lastListRefreshRef.current = 0;
    let cancelled = false;
    const tick = async () => {
      const r = await orchestrateGet(orchId);
      if (cancelled) return;
      if (!r.ok) {
        setBusy(false);
        const msg = r.error || t("orchestrateError");
        const isNet =
          msg.toLowerCase().includes("network error") ||
          msg.toLowerCase().includes("gateway unreachable") ||
          msg.toLowerCase().includes("failed to fetch");
        setError(isNet ? t("orchestrateNetworkError") : msg);
        return;
      }
      setError(null);
      setSelected({
        orchId: r.orchId,
        name: r.name,
        status: r.status,
        participants: r.participants,
        messages: r.messages || [],
      });
      const now = Date.now();
      if (now - lastListRefreshRef.current > 8000) {
        lastListRefreshRef.current = now;
        void loadOrches();
      }
      if (r.status && r.status !== "accepted" && r.status !== "running") {
        setBusy(false);
      }
    };
    void tick();
    const timer = window.setInterval(tick, 900);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadOrches, selectedOrchId, t]);

  const addParticipant = useCallback((aid: string) => {
    const v = (aid || "").trim();
    if (!v) return;
    setCreateParticipants((prev) => (prev.includes(v) ? prev : [...prev, v]));
  }, []);

  const removeParticipant = useCallback((aid: string) => {
    setCreateParticipants((prev) => prev.filter((x) => x !== aid));
  }, []);

  const send = useCallback(async () => {
    if (!canSend || busy) return;
    setBusy(true);
    setError(null);
    const msgText = input.trim();
    const localUserMsg: OrchMessage = {
      id: `local-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      ts: Date.now(),
      round: selected?.messages?.length ? (selected.messages[selected.messages.length - 1]?.round ?? 0) : 0,
      speaker: "user",
      role: "user",
      text: msgText,
    };
    setSelected((prev) => {
      if (!prev) return prev;
      return { ...prev, messages: [...(prev.messages || []), localUserMsg] };
    });
    const idem = `orch-send-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const r = await orchestrateSend(selectedOrchId, msgText, idem);
    if (!r.ok) {
      setBusy(false);
      setError(r.error || t("orchestrateError"));
      return;
    }
    setInput("");
    // Pull latest state immediately (don't wait for polling tick).
    const g = await orchestrateGet(selectedOrchId);
    if (g.ok) {
      setSelected({
        orchId: g.orchId,
        name: g.name,
        status: g.status,
        participants: g.participants,
        messages: g.messages || [],
      });
    }
  }, [busy, canSend, input, selected?.messages, selectedOrchId, t]);

  const openCreate = useCallback(() => {
    setCreateName("");
    setCreateMaxRounds("8");
    setCreateStrategy("round_robin");
    setCreateParticipants(["main"]);
    setRouterProvider("");
    setRouterModel("");
    setRouterBaseUrl("http://127.0.0.1:8000/v1");
    setRouterApiKey("");
    setRouterThinking("");
    setCreateOpen(true);
  }, []);

  useEffect(() => {
    // When user enters Orchestrate view, refresh data (do not auto-open create dialog).
    void loadAgents();
    void loadOrches();
  }, [autoOpenKey]);

  useEffect(() => {
    if (!selectedOrchId) return;
    // Auto-follow latest message.
    const el = messagesWrapRef.current;
    const end = messagesEndRef.current;
    if (!el || !end) return;
    // If user is near bottom, keep following; otherwise don't hijack manual scroll.
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const shouldFollow = distanceToBottom < 160;
    if (!shouldFollow) return;
    requestAnimationFrame(() => {
      end.scrollIntoView({ block: "end" });
    });
  }, [selectedOrchId, selected?.messages?.length]);

  const doCreate = useCallback(async () => {
    setError(null);
    const idem = `orch-create-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
    const mr = Number(createMaxRounds || "8");
    const res = await orchestrateCreate({
      sessionKey: "desktop-orchestrator",
      name: createName.trim() || undefined,
      participants: createParticipants,
      maxRounds: Number.isFinite(mr) && mr > 0 ? mr : 8,
      strategy: createStrategy,
      routerLlm:
        createStrategy === "router_llm"
          ? {
              provider: routerProvider || undefined,
              model: routerModel || undefined,
              base_url: routerBaseUrl || undefined,
              api_key: routerApiKey || undefined,
              thinking_level: routerThinking || undefined,
            }
          : undefined,
      idempotencyKey: idem,
    });
    if (!res.ok) {
      setError(res.error || t("orchestrateError"));
      return;
    }
    setCreateOpen(false);
    await loadOrches();
    setSelectedOrchId(res.orchId);
  }, [
    createMaxRounds,
    createName,
    createParticipants,
    createStrategy,
    loadOrches,
    routerApiKey,
    routerBaseUrl,
    routerModel,
    routerProvider,
    routerThinking,
    t,
  ]);

  const doDelete = useCallback(
    async (o: OrchestrateListItem) => {
      const name = (o.name || "").trim() || o.orchId.slice(0, 8);
      const ok = window.confirm(t("orchestrateDeleteConfirm", { name }));
      if (!ok) return;
      setError(null);
      const r = await orchestrateDelete(o.orchId);
      if (!r.ok) {
        setError(r.error || t("orchestrateError"));
        return;
      }
      if (selectedOrchId === o.orchId) {
        setSelectedOrchId("");
        setSelected(null);
      }
      await loadOrches();
    },
    [loadOrches, selectedOrchId, t]
  );

  return (
    <div className="flex h-full min-h-0 w-full">
      <div className="w-64 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] p-3 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">{t("orchestrateTitle")}</div>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 shrink-0"
            title={t("orchestrateCreate")}
            aria-label={t("orchestrateCreate")}
            onClick={openCreate}
          >
            <Image src="/icons/add.png" alt="" width={20} height={20} className="h-5 w-5 object-contain" />
          </button>
        </div>

        <div className="space-y-2 min-h-0 flex-1">
          <div className="text-[10px] text-[var(--muted)]">{t("orchestrateAll")}</div>
          <div className="min-h-0 flex-1 overflow-auto space-y-1">
            {orches.length === 0 ? (
              <div className="text-xs text-[var(--muted)]">{t("orchestrateEmptyList")}</div>
            ) : (
              orches.map((o) => {
                const active = o.orchId === selectedOrchId;
                const title = (o.name || "").trim() || o.orchId.slice(0, 8);
                return (
                  <div
                    key={o.orchId}
                    className={`w-full rounded-lg border border-[var(--border)] px-3 py-2 hover:opacity-90 ${
                      active ? "bg-[var(--accent)] text-white" : "bg-[var(--panel)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setSelectedOrchId(o.orchId)}
                      >
                        <div className="text-xs font-medium truncate">{title}</div>
                        <div
                          className={`text-[10px] ${
                            active ? "text-white/85" : "text-[var(--muted)]"
                          } truncate`}
                        >
                          {o.status} · {((o.participants || []).join(", ") || "—").slice(0, 60)}
                        </div>
                      </button>
                      <button
                        type="button"
                        title={t("orchestrateDelete")}
                        aria-label={t("orchestrateDelete")}
                        className={`flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border)] hover:opacity-90 shrink-0 ${
                          active ? "bg-white/10" : "bg-[var(--bg)]"
                        }`}
                        onClick={() => void doDelete(o)}
                      >
                        <Image
                          src="/icons/del.png"
                          alt=""
                          width={18}
                          height={18}
                          className="h-[18px] w-[18px] object-contain"
                        />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="mt-auto space-y-1">
          {selectedOrchId ? (
            <div className="text-[10px] text-[var(--muted)] font-mono truncate" title={selectedOrchId}>
              orch: {selectedOrchId}
            </div>
          ) : null}
          {selected?.status ? (
            <div className="text-[10px] text-[var(--muted)]">
              {t("orchestrateStatus")}: {selected.status}
            </div>
          ) : null}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
          {error ? <p className="text-xs text-red-500/90 mb-2">{error}</p> : null}
          <div
            ref={messagesWrapRef}
            className="min-h-0 flex-1 overflow-auto rounded-lg border border-[var(--border)] bg-[var(--panel)] p-3 space-y-2"
          >
            {!selectedOrchId ? (
              <div className="text-xs text-[var(--muted)]">{t("orchestratePickOne")}</div>
            ) : (selected?.messages?.length || 0) === 0 ? (
              <div className="text-xs text-[var(--muted)]">{t("orchestrateEmpty")}</div>
            ) : (
              (selected?.messages || []).map((m) => {
                const avUrl = avatarUrlForSpeaker(m.speaker);
                const fallback = "/icons/planet.png";
                const imgSrc =
                  (m.speaker || "").trim().toLowerCase() === "user" ? fallback : avUrl || "/icons/robot.png";
                return (
                  <div key={m.id} className="flex gap-2 items-start">
                    <Image
                      src={imgSrc}
                      alt=""
                      width={32}
                      height={32}
                      className="h-8 w-8 shrink-0 rounded-lg object-cover mt-0.5"
                      unoptimized
                    />
                    <div
                      className={`min-w-0 flex-1 flex flex-col gap-1 rounded-lg border border-[var(--border)] px-3 py-2 ${speakerCardClass(
                        m.speaker
                      )}`}
                    >
                      <div className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--muted)]">
                        <span className={`font-mono font-semibold ${speakerColorClass(m.speaker)}`}>
                          {m.speaker}
                        </span>
                        <span>·</span>
                        <span>{m.role}</span>
                        <span>·</span>
                        <span>r{m.round}</span>
                        {m.ts ? (
                          <>
                            <span>·</span>
                            <span className="font-mono">{fmtTs(m.ts)}</span>
                          </>
                        ) : null}
                      </div>
                      <div className="text-xs whitespace-pre-wrap break-words leading-relaxed">
                        {m.text}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="mt-3 flex gap-2">
            <input
              className="flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("orchestratePrompt")}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              disabled={busy}
            />
            <button
              type="button"
              className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              onClick={() => void send()}
              disabled={!canSend || busy}
            >
              {t("send")}
            </button>
          </div>
        </div>
      </div>

      {createOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
          role="presentation"
        >
          <div
            className="w-full max-w-lg max-h-[min(90vh,720px)] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orbit-create-orch-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
              <h3 id="orbit-create-orch-title" className="text-sm font-semibold">
                {t("orchestrateCreate")}
              </h3>
              <button
                type="button"
                className="text-xs text-[var(--muted)] px-2 py-1 rounded hover:bg-[var(--panel)]"
                onClick={() => setCreateOpen(false)}
              >
                {t("closeDialog")}
              </button>
            </div>
            <div className="p-4 space-y-4 text-sm">
              <label className="flex flex-col gap-1">
                <span className="text-[var(--muted)] text-xs">{t("orchestrateName")}</span>
                <input
                  className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="team-1"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[var(--muted)] text-xs">{t("orchestrateMaxRounds")}</span>
                <input
                  className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                  value={createMaxRounds}
                  onChange={(e) => setCreateMaxRounds(e.target.value)}
                  inputMode="numeric"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[var(--muted)] text-xs">{t("orchestrateStrategy")}</span>
                <select
                  className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                  value={createStrategy}
                  onChange={(e) => setCreateStrategy(e.target.value as "round_robin" | "router_llm")}
                >
                  <option value="round_robin">{t("orchestrateStrategyRoundRobin")}</option>
                  <option value="router_llm">{t("orchestrateStrategyRouter")}</option>
                </select>
              </label>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[var(--muted)] text-xs">{t("orchestrateParticipants")}</span>
                  <button
                    type="button"
                    className="text-xs px-2 py-1 rounded border border-[var(--border)] bg-[var(--panel)] hover:opacity-90"
                    onClick={() => setAddOpen(true)}
                  >
                    {t("orchestrateAddAgent")}
                  </button>
                </div>
                <div className="flex flex-wrap gap-1">
                  {createParticipants.map((p) => (
                    <span
                      key={p}
                      className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--bg)] px-2 py-1 text-[10px] font-mono"
                    >
                      {p}
                      {createParticipants.length > 1 ? (
                        <button
                          type="button"
                          className="text-[var(--muted)] hover:text-[var(--text)]"
                          onClick={() => removeParticipant(p)}
                        >
                          ×
                        </button>
                      ) : null}
                    </span>
                  ))}
                </div>
              </div>

              {createStrategy === "router_llm" ? (
                <div className="border-t border-[var(--border)] pt-3 space-y-3">
                  <div className="text-[10px] text-[var(--muted)]">
                    {t("orchestrateRouterHint")}
                  </div>
                  <label className="flex flex-col gap-1">
                    <span className="text-[var(--muted)] text-xs">{t("agentsCreateLlmProvider")}</span>
                    <select
                      className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                      value={routerProvider}
                      onChange={(e) => setRouterProvider(e.target.value)}
                    >
                      <option value="">openai</option>
                      {providers.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[var(--muted)] text-xs">{t("agentsCreateLlmModel")}</span>
                    <input
                      className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                      value={routerModel}
                      onChange={(e) => setRouterModel(e.target.value)}
                      placeholder="gpt-4o-mini"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[var(--muted)] text-xs">{t("agentsCreateLlmBaseUrl")}</span>
                    <input
                      className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                      value={routerBaseUrl}
                      onChange={(e) => setRouterBaseUrl(e.target.value)}
                      placeholder="http://127.0.0.1:8000/v1"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[var(--muted)] text-xs">{t("agentsCreateLlmApiKey")}</span>
                    <input
                      type="password"
                      className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                      value={routerApiKey}
                      onChange={(e) => setRouterApiKey(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[var(--muted)] text-xs">{t("agentsCreateLlmThinking")}</span>
                    <input
                      className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                      value={routerThinking}
                      onChange={(e) => setRouterThinking(e.target.value)}
                      placeholder="off | low | medium | high"
                    />
                  </label>
                </div>
              ) : null}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg border border-[var(--border)] text-xs"
                  onClick={() => setCreateOpen(false)}
                >
                  {t("orchestrateCancel")}
                </button>
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-medium"
                  onClick={() => void doCreate()}
                >
                  {t("orchestrateCreate")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {addOpen ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4"
          role="presentation"
        >
          <div
            className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orbit-add-orch-agent-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
              <h3 id="orbit-add-orch-agent-title" className="text-sm font-semibold">
                {t("orchestrateAddAgent")}
              </h3>
              <button
                type="button"
                className="text-xs text-[var(--muted)] px-2 py-1 rounded hover:bg-[var(--panel)]"
                onClick={() => setAddOpen(false)}
              >
                {t("closeDialog")}
              </button>
            </div>
            <div className="p-4 space-y-2">
              {listedAgents.length === 0 ? (
                <p className="text-xs text-[var(--muted)]">{t("agentsLoading")}</p>
              ) : (
                <div className="max-h-72 overflow-auto space-y-1">
                  {listedAgents.map((row) => {
                    const av = row.avatar?.trim();
                    const src = av ? `/icons/headers/${encodeURIComponent(av)}` : "/icons/robot.png";
                    return (
                      <button
                        key={row.agentId}
                        type="button"
                        className="w-full flex items-center gap-2 text-left text-xs px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 font-mono"
                        onClick={() => {
                          addParticipant(row.agentId);
                          setAddOpen(false);
                        }}
                      >
                        <Image
                          src={src}
                          alt=""
                          width={28}
                          height={28}
                          className="h-7 w-7 shrink-0 rounded-md object-cover"
                          unoptimized
                        />
                        {row.agentId}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

