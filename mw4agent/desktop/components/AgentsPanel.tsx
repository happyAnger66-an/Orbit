"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  createAgent,
  deleteAgent,
  listAgents,
  listLlmProviders,
  readAgentWorkspaceFile,
  resolveAgentDefaults,
  setAgentAvatar,
  type ListedAgent,
  writeAgentWorkspaceFile,
} from "@/lib/gateway";
import { AGENT_HEADER_FILES, agentHeaderSrc } from "@/lib/agentHeaders";
import { useI18n } from "@/lib/i18n";

function AvatarPickerGrid({
  value,
  onChange,
  title,
  hint,
  noneLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  title: string;
  hint: string;
  noneLabel: string;
}) {
  return (
    <div>
      <span className="text-[var(--muted)] text-xs">{title}</span>
      <p className="text-[10px] text-[var(--muted)] mt-0.5 mb-2">{hint}</p>
      <div className="grid grid-cols-4 gap-2">
        <button
          type="button"
          onClick={() => onChange("")}
          className={`flex flex-col items-center justify-center gap-1 rounded-lg border px-1 py-2 text-[10px] min-h-[64px] ${
            !value
              ? "border-[var(--accent)] ring-1 ring-[var(--accent)]"
              : "border-[var(--border)] bg-[var(--panel)]"
          }`}
        >
          <span className="text-[var(--muted)] text-center leading-tight">{noneLabel}</span>
        </button>
        {AGENT_HEADER_FILES.map((file) => {
          const active = value === file;
          return (
            <button
              key={file}
              type="button"
              title={file}
              onClick={() => onChange(file)}
              className={`rounded-lg border p-1 ${
                active
                  ? "border-[var(--accent)] ring-1 ring-[var(--accent)]"
                  : "border-[var(--border)] bg-[var(--panel)]"
              }`}
            >
              <Image
                src={agentHeaderSrc(file)}
                alt=""
                width={48}
                height={48}
                className="h-12 w-12 mx-auto rounded-md object-cover"
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

type AgentsPanelProps = {
  onOpenChatWithAgent: (agentId: string) => void;
};

export function AgentsPanel({ onOpenChatWithAgent }: AgentsPanelProps) {
  const { t } = useI18n();
  const [agents, setAgents] = useState<ListedAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [draftAgentId, setDraftAgentId] = useState("");
  const [workspaceDir, setWorkspaceDir] = useState("");
  const [defaultWorkspaceHint, setDefaultWorkspaceHint] = useState("");
  const workspaceTouchedRef = useRef(false);
  const [llmProvider, setLlmProvider] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const baseUrlTouchedRef = useRef(false);
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmThinking, setLlmThinking] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [selectedAvatar, setSelectedAvatar] = useState<string>("");

  const [avatarEditOpen, setAvatarEditOpen] = useState(false);
  const [avatarEditAgentId, setAvatarEditAgentId] = useState("");
  const [avatarEditSelection, setAvatarEditSelection] = useState("");
  const [avatarEditError, setAvatarEditError] = useState<string | null>(null);
  const [avatarEditSaving, setAvatarEditSaving] = useState(false);

  const [fileEditorOpen, setFileEditorOpen] = useState(false);
  const [fileEditorAgentId, setFileEditorAgentId] = useState("");
  const [fileEditorPath, setFileEditorPath] = useState<string>("memory.md");
  const [fileEditorText, setFileEditorText] = useState("");
  const [fileEditorLoading, setFileEditorLoading] = useState(false);
  const [fileEditorSaving, setFileEditorSaving] = useState(false);
  const [fileEditorError, setFileEditorError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const res = await listAgents();
    setLoading(false);
    if (!res.ok) {
      setError(res.error || t("agentsError"));
      setAgents([]);
      return;
    }
    setAgents(res.agents);
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreateModal = useCallback(() => {
    setModalError(null);
    setDraftAgentId("");
    setWorkspaceDir("");
    setDefaultWorkspaceHint("");
    workspaceTouchedRef.current = false;
    setLlmProvider("");
    setLlmModel("");
    baseUrlTouchedRef.current = false;
    setLlmBaseUrl("http://127.0.0.1:8000/v1");
    setLlmApiKey("");
    setLlmThinking("");
    setSelectedAvatar("");
    setCreateOpen(true);
  }, []);

  useEffect(() => {
    if (!createOpen) return;
    void listLlmProviders().then((r) => {
      if (r.ok) setProviders(r.providers);
      else setProviders(["echo", "openai", "deepseek", "vllm", "aliyun-bailian"]);
    });
  }, [createOpen]);

  useEffect(() => {
    if (!createOpen) return;
    const id = draftAgentId.trim() || "new-agent";
    const timer = window.setTimeout(() => {
      void resolveAgentDefaults(id).then((r) => {
        if (!r.ok) return;
        setDefaultWorkspaceHint(r.workspaceDir);
        if (!workspaceTouchedRef.current) {
          setWorkspaceDir(r.workspaceDir);
        }
      });
    }, 280);
    return () => window.clearTimeout(timer);
  }, [createOpen, draftAgentId]);

  const closeCreateModal = useCallback(() => {
    setCreateOpen(false);
    setModalError(null);
  }, []);

  const openAvatarEditor = useCallback((a: ListedAgent) => {
    setAvatarEditAgentId(a.agentId);
    setAvatarEditSelection(a.avatar?.trim() || "");
    setAvatarEditError(null);
    setAvatarEditOpen(true);
  }, []);

  const closeAvatarEditor = useCallback(() => {
    setAvatarEditOpen(false);
    setAvatarEditAgentId("");
    setAvatarEditSelection("");
    setAvatarEditError(null);
    setAvatarEditSaving(false);
  }, []);

  const saveAvatarEditor = useCallback(async () => {
    const aid = avatarEditAgentId.trim();
    if (!aid) return;
    setAvatarEditSaving(true);
    setAvatarEditError(null);
    const res = await setAgentAvatar(aid, avatarEditSelection.trim());
    setAvatarEditSaving(false);
    if (!res.ok) {
      setAvatarEditError(res.error || t("agentsError"));
      return;
    }
    closeAvatarEditor();
    await load();
  }, [avatarEditAgentId, avatarEditSelection, closeAvatarEditor, load, t]);

  const closeFileEditor = useCallback(() => {
    setFileEditorOpen(false);
    setFileEditorAgentId("");
    setFileEditorText("");
    setFileEditorError(null);
    setFileEditorLoading(false);
    setFileEditorSaving(false);
  }, []);

  const openFileEditor = useCallback(
    async (agentId: string, path: "memory.md" | "SOUL.md") => {
      setFileEditorError(null);
      setFileEditorAgentId(agentId);
      setFileEditorPath(path);
      setFileEditorOpen(true);
      setFileEditorLoading(true);
      const res = await readAgentWorkspaceFile(agentId, path);
      setFileEditorLoading(false);
      if (!res.ok) {
        setFileEditorError(res.error || t("agentsFileEditorError"));
        setFileEditorText("");
        return;
      }
      setFileEditorPath(res.path || path);
      setFileEditorText(res.text);
    },
    [t]
  );

  const saveFileEditor = useCallback(async () => {
    if (!fileEditorOpen) return;
    const aid = fileEditorAgentId;
    const path = fileEditorPath;
    setFileEditorSaving(true);
    setFileEditorError(null);
    const res = await writeAgentWorkspaceFile(aid, path, fileEditorText);
    setFileEditorSaving(false);
    if (!res.ok) {
      setFileEditorError(res.error || t("agentsFileEditorError"));
      return;
    }
    closeFileEditor();
  }, [closeFileEditor, fileEditorAgentId, fileEditorOpen, fileEditorPath, fileEditorText, t]);

  const confirmAndDelete = useCallback(
    async (agentId: string) => {
      const ok = window.confirm(t("agentsDeleteConfirm", { id: agentId }));
      if (!ok) return;
      setError(null);
      const res = await deleteAgent(agentId);
      if (!res.ok) {
        setError(res.error || "agents.delete failed");
        return;
      }
      await load();
    },
    [load, t]
  );

  const submitCreate = useCallback(async () => {
    const aid = draftAgentId.trim();
    if (!aid) {
      setModalError(t("agentsCreateIdRequired"));
      return;
    }
    setSubmitting(true);
    setModalError(null);
    const llm: Record<string, string> = {};
    if (llmProvider.trim()) llm.provider = llmProvider.trim();
    if (llmModel.trim()) llm.model = llmModel.trim();
    if (llmBaseUrl.trim()) llm.base_url = llmBaseUrl.trim();
    if (llmApiKey.trim()) llm.api_key = llmApiKey.trim();
    if (llmThinking.trim()) llm.thinking_level = llmThinking.trim();

    const res = await createAgent({
      agentId: aid,
      workspaceDir: workspaceDir.trim() || undefined,
      avatar: selectedAvatar.trim() || undefined,
      llm: Object.keys(llm).length ? llm : undefined,
    });
    setSubmitting(false);
    if (!res.ok) {
      setModalError(res.error || "agents.create failed");
      return;
    }
    closeCreateModal();
    await load();
  }, [
    draftAgentId,
    workspaceDir,
    llmProvider,
    llmModel,
    llmBaseUrl,
    llmApiKey,
    llmThinking,
    selectedAvatar,
    closeCreateModal,
    load,
    t,
  ]);

  return (
    <div className="flex flex-col h-full min-h-0 p-4 sm:p-6 max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="text-lg font-semibold">{t("myAgents")}</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            title={t("agentsAddTooltip")}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 shrink-0"
            onClick={openCreateModal}
            aria-label={t("agentsAddTooltip")}
          >
            <Image
              src="/icons/add.png"
              alt=""
              width={20}
              height={20}
              className="h-5 w-5 object-contain"
            />
          </button>
          <button
            type="button"
            className="text-sm px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90"
            onClick={() => void load()}
            disabled={loading}
          >
            {t("agentsRefresh")}
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-[var(--muted)]">{t("agentsLoading")}</p>
      ) : null}
      {!loading && error ? (
        <p className="text-sm text-red-500/90">{error}</p>
      ) : null}
      {!loading && !error && agents.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">{t("agentsEmpty")}</p>
      ) : null}

      {!loading && agents.length > 0 ? (
        <div className="overflow-auto rounded-lg border border-[var(--border)] bg-[var(--panel)]">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-[var(--border)] text-[var(--muted)] text-xs uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 font-medium w-[1%] whitespace-nowrap">
                  {t("agentsCreateAvatar")}
                </th>
                <th className="px-3 py-2 font-medium">{t("agentId")}</th>
                <th className="px-3 py-2 font-medium hidden md:table-cell">
                  {t("workspaceDir")}
                </th>
                <th className="px-3 py-2 font-medium">{t("runStatus")}</th>
                <th className="px-3 py-2 font-medium w-[1%] whitespace-nowrap">
                  {t("actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => {
                const rs = a.runStatus;
                const state = rs?.state ?? "—";
                const n = rs?.activeRuns ?? 0;
                const avSrc = a.avatar?.trim()
                  ? agentHeaderSrc(a.avatar.trim())
                  : "/icons/robot.png";
                return (
                  <tr
                    key={a.agentId}
                    className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--bg)]/50"
                  >
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        title={t("agentsEditAvatarTooltip")}
                        aria-label={t("agentsEditAvatarTooltip")}
                        className="block rounded-lg border border-transparent hover:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] p-0"
                        onClick={() => openAvatarEditor(a)}
                      >
                        <Image
                          src={avSrc}
                          alt=""
                          width={36}
                          height={36}
                          className="h-9 w-9 rounded-lg object-cover border border-[var(--border)]"
                        />
                      </button>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      <div className="flex flex-col gap-0.5">
                        <span>{a.agentId}</span>
                        {a.configured === false ? (
                          <span className="text-[10px] text-amber-500/90">
                            {t("agentNotConfigured")}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--muted)] max-w-xs truncate hidden md:table-cell">
                      {a.workspaceDir || "—"}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className="text-[var(--text)]">{state}</span>
                      {n > 0 ? (
                        <span className="text-[var(--muted)] ml-1">
                          ({t("activeRuns")}: {n})
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          className="text-xs px-2 py-1 rounded border border-[var(--border)] bg-[var(--accent)] text-white"
                          onClick={() => onOpenChatWithAgent(a.agentId)}
                        >
                          {t("useInChat")}
                        </button>
                        <button
                          type="button"
                          title={t("agentsEditMemoryTooltip")}
                          aria-label={t("agentsEditMemoryTooltip")}
                          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 shrink-0"
                          onClick={() => void openFileEditor(a.agentId, "memory.md")}
                        >
                          <Image
                            src="/icons/memory.png"
                            alt=""
                            width={20}
                            height={20}
                            className="h-5 w-5 object-contain"
                          />
                        </button>
                        <button
                          type="button"
                          title={t("agentsEditSoulTooltip")}
                          aria-label={t("agentsEditSoulTooltip")}
                          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 shrink-0"
                          onClick={() => void openFileEditor(a.agentId, "SOUL.md")}
                        >
                          <Image
                            src="/icons/role.png"
                            alt=""
                            width={20}
                            height={20}
                            className="h-5 w-5 object-contain"
                          />
                        </button>
                        <button
                          type="button"
                          title={t("agentsDeleteTooltip")}
                          aria-label={t("agentsDeleteTooltip")}
                          className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:opacity-90 shrink-0"
                          onClick={() => void confirmAndDelete(a.agentId)}
                        >
                          <Image
                            src="/icons/del.png"
                            alt=""
                            width={20}
                            height={20}
                            className="h-5 w-5 object-contain"
                          />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
          <div
            className="w-full max-w-lg max-h-[min(90vh,640px)] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orbit-new-agent-title"
          >
            <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
              <h3 id="orbit-new-agent-title" className="text-sm font-semibold">
                {t("agentsCreateTitle")}
              </h3>
              <button
                type="button"
                className="text-xs text-[var(--muted)] px-2 py-1 rounded hover:bg-[var(--panel)]"
                onClick={closeCreateModal}
              >
                {t("agentsCreateCancel")}
              </button>
            </div>
            <div className="p-4 space-y-4 text-sm">
              {modalError ? (
                <p className="text-red-500/90 text-xs">{modalError}</p>
              ) : null}
              <label className="flex flex-col gap-1">
                <span className="text-[var(--muted)] text-xs">
                  {t("agentsCreateAgentId")}
                </span>
                <input
                  className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] font-mono text-xs"
                  value={draftAgentId}
                  onChange={(e) => setDraftAgentId(e.target.value)}
                  placeholder="my-agent"
                  autoComplete="off"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[var(--muted)] text-xs">
                  {t("agentsCreateWorkspace")}
                </span>
                <input
                  className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                  value={workspaceDir}
                  onChange={(e) => {
                    workspaceTouchedRef.current = true;
                    setWorkspaceDir(e.target.value);
                  }}
                />
                {defaultWorkspaceHint ? (
                  <span className="text-[10px] text-[var(--muted)]">
                    {t("agentsCreateWorkspaceHint")}: {defaultWorkspaceHint}
                  </span>
                ) : null}
                <button
                  type="button"
                  className="self-start text-[10px] text-[var(--accent)] underline"
                  onClick={() => {
                    workspaceTouchedRef.current = false;
                    setWorkspaceDir(defaultWorkspaceHint);
                  }}
                >
                  {t("agentsCreateUseDefaultWorkspace")}
                </button>
              </label>
              <AvatarPickerGrid
                value={selectedAvatar}
                onChange={setSelectedAvatar}
                title={t("agentsCreateAvatar")}
                hint={t("agentsCreateAvatarHint")}
                noneLabel={t("agentsCreateAvatarNone")}
              />
              <div className="border-t border-[var(--border)] pt-3 space-y-3">
                <p className="text-[10px] text-[var(--muted)]">
                  {t("agentsCreateLlmOptional")}
                </p>
                <label className="flex flex-col gap-1">
                  <span className="text-[var(--muted)] text-xs">
                    {t("agentsCreateLlmProvider")}
                  </span>
                  <select
                    className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                    value={llmProvider}
                    onChange={(e) => setLlmProvider(e.target.value)}
                  >
                    <option value="">—</option>
                    {providers.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[var(--muted)] text-xs">
                    {t("agentsCreateLlmModel")}
                  </span>
                  <input
                    className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                    value={llmModel}
                    onChange={(e) => setLlmModel(e.target.value)}
                    placeholder="gpt-4o-mini"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[var(--muted)] text-xs">
                    {t("agentsCreateLlmBaseUrl")}
                  </span>
                  <input
                    className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                    value={llmBaseUrl}
                    onChange={(e) => {
                      baseUrlTouchedRef.current = true;
                      setLlmBaseUrl(e.target.value);
                    }}
                    placeholder="http://127.0.0.1:8000/v1"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[var(--muted)] text-xs">
                    {t("agentsCreateLlmApiKey")}
                  </span>
                  <input
                    type="password"
                    className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                    value={llmApiKey}
                    onChange={(e) => setLlmApiKey(e.target.value)}
                    autoComplete="off"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[var(--muted)] text-xs">
                    {t("agentsCreateLlmThinking")}
                  </span>
                  <input
                    className="px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs"
                    value={llmThinking}
                    onChange={(e) => setLlmThinking(e.target.value)}
                    placeholder="off | low | medium | high"
                  />
                </label>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg border border-[var(--border)] text-xs"
                  onClick={closeCreateModal}
                  disabled={submitting}
                >
                  {t("agentsCreateCancel")}
                </button>
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-medium disabled:opacity-50"
                  disabled={submitting}
                  onClick={() => void submitCreate()}
                >
                  {t("agentsCreateSubmit")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {avatarEditOpen ? (
        <div
          className="fixed inset-0 z-[55] flex items-center justify-center bg-black/55 p-4"
          role="presentation"
          onClick={closeAvatarEditor}
        >
          <div
            className="w-full max-w-lg max-h-[min(90vh,640px)] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orbit-edit-avatar-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
              <h3 id="orbit-edit-avatar-title" className="text-sm font-semibold">
                {t("agentsEditAvatarTitle")}
              </h3>
              <button
                type="button"
                className="text-xs text-[var(--muted)] px-2 py-1 rounded hover:bg-[var(--panel)]"
                onClick={closeAvatarEditor}
                disabled={avatarEditSaving}
              >
                {t("closeDialog")}
              </button>
            </div>
            <div className="p-4 space-y-4 text-sm">
              <p className="text-xs font-mono text-[var(--muted)]">{avatarEditAgentId}</p>
              {avatarEditError ? (
                <p className="text-red-500/90 text-xs">{avatarEditError}</p>
              ) : null}
              <AvatarPickerGrid
                value={avatarEditSelection}
                onChange={setAvatarEditSelection}
                title={t("agentsCreateAvatar")}
                hint={t("agentsCreateAvatarHint")}
                noneLabel={t("agentsCreateAvatarNone")}
              />
              <div className="flex justify-end gap-2 pt-2 border-t border-[var(--border)]">
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg border border-[var(--border)] text-xs"
                  onClick={closeAvatarEditor}
                  disabled={avatarEditSaving}
                >
                  {t("closeDialog")}
                </button>
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-medium disabled:opacity-50"
                  disabled={avatarEditSaving}
                  onClick={() => void saveAvatarEditor()}
                >
                  {t("agentsEditAvatarSave")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {fileEditorOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
          role="presentation"
          onClick={closeFileEditor}
        >
          <div
            className="w-full max-w-3xl max-h-[min(90vh,720px)] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="orbit-agent-file-editor-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--border)] px-4 py-3 flex items-center justify-between">
              <h3 id="orbit-agent-file-editor-title" className="text-sm font-semibold">
                {t("agentsFileEditorTitle", { path: fileEditorPath, id: fileEditorAgentId })}
              </h3>
              <button
                type="button"
                className="text-xs text-[var(--muted)] px-2 py-1 rounded hover:bg-[var(--panel)]"
                onClick={closeFileEditor}
              >
                {t("agentsFileEditorCancel")}
              </button>
            </div>
            <div className="p-4 space-y-3 text-sm">
              {fileEditorError ? (
                <p className="text-red-500/90 text-xs">{fileEditorError}</p>
              ) : null}
              {fileEditorLoading ? (
                <p className="text-xs text-[var(--muted)]">{t("agentsFileEditorLoading")}</p>
              ) : (
                <textarea
                  className="w-full min-h-[420px] px-3 py-2 rounded-lg bg-[var(--panel)] border border-[var(--border)] text-[var(--text)] text-xs font-mono"
                  value={fileEditorText}
                  onChange={(e) => setFileEditorText(e.target.value)}
                  spellCheck={false}
                />
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg border border-[var(--border)] text-xs"
                  onClick={closeFileEditor}
                  disabled={fileEditorSaving}
                >
                  {t("agentsFileEditorCancel")}
                </button>
                <button
                  type="button"
                  className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white text-xs font-medium disabled:opacity-50"
                  onClick={() => void saveFileEditor()}
                  disabled={fileEditorSaving || fileEditorLoading}
                >
                  {t("agentsFileEditorSave")}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
