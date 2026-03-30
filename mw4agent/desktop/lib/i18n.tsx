"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DesktopLocale = "en" | "zh-CN";

const STORAGE_KEY = "mw4agent-desktop-locale";

type Params = Record<string, string | number | undefined>;

function interpolate(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const v = params[key];
    return v !== undefined && v !== null ? String(v) : `{${key}}`;
  });
}

const en: Record<string, string> = {
  brandOrbit: "Orbit",
  newTask: "New task",
  myAgents: "My Agents",
  skillsNav: "Skills",
  gatewayUrl: "Gateway URL",
  themeLight: "Light",
  themeDark: "Dark",
  homeBlurb:
    "Start a task, manage agents, or inspect skills discovered from your workspace.",
  closeDialog: "Close",

  stepThinking: "Thinking…",
  stepCallingTool: "Calling tool: {name}",
  stepToolDone: "Tool finished: {name}",
  errorRpc: "Request failed",

  connected: "Connected",
  reconnecting: "Reconnecting…",
  disconnected: "Disconnected",

  subtitle: "Chat with your agent via Gateway",
  language: "Language",
  newChat: "New chat",
  agentId: "Agent ID",
  sessionKey: "Session key",
  placeholder: "Message…",
  metaYou: "You",
  metaAssistant: "Assistant",
  reasoning: "Reasoning",
  send: "Send",

  skillsTitle: "Skills",
  skillsSummary: "{count} skill(s) loaded",
  skillsVersion: "Version",
  skillsPromptCompact: "Prompt compact",
  skillsPromptTruncated: "Prompt truncated",
  skillsRefresh: "Refresh",
  skillsFilteredOut: "{n} filtered out",
  skillsLoading: "Loading skills…",
  skillsEmpty: "No skills found.",
  skillsError: "Could not load skills.",
  skillName: "Name",
  skillSource: "Source",
  skillDescription: "Description",
  skillLocation: "Location",

  agentsError: "Could not load agents.",
  agentsRefresh: "Refresh",
  agentsLoading: "Loading agents…",
  agentsEmpty: "No agents yet.",
  workspaceDir: "Workspace",
  runStatus: "Run status",
  actions: "Actions",
  agentNotConfigured: "Not configured",
  activeRuns: "Active runs",
  useInChat: "Use in chat",
};

const zhCN: Record<string, string> = {
  brandOrbit: "Orbit",
  newTask: "新任务",
  myAgents: "我的智能体",
  skillsNav: "技能",
  gatewayUrl: "网关地址",
  themeLight: "浅色",
  themeDark: "深色",
  homeBlurb: "发起任务、管理智能体，或查看工作区发现的技能。",
  closeDialog: "关闭",

  stepThinking: "思考中…",
  stepCallingTool: "正在调用工具：{name}",
  stepToolDone: "工具已完成：{name}",
  errorRpc: "请求失败",

  connected: "已连接",
  reconnecting: "正在重连…",
  disconnected: "未连接",

  subtitle: "通过网关与智能体对话",
  language: "语言",
  newChat: "新会话",
  agentId: "智能体 ID",
  sessionKey: "会话键",
  placeholder: "输入消息…",
  metaYou: "你",
  metaAssistant: "助手",
  reasoning: "推理",
  send: "发送",

  skillsTitle: "技能",
  skillsSummary: "已加载 {count} 个技能",
  skillsVersion: "版本",
  skillsPromptCompact: "提示已压缩",
  skillsPromptTruncated: "提示已截断",
  skillsRefresh: "刷新",
  skillsFilteredOut: "已过滤 {n} 项",
  skillsLoading: "正在加载技能…",
  skillsEmpty: "暂无技能。",
  skillsError: "无法加载技能。",
  skillName: "名称",
  skillSource: "来源",
  skillDescription: "说明",
  skillLocation: "路径",

  agentsError: "无法加载智能体列表。",
  agentsRefresh: "刷新",
  agentsLoading: "正在加载智能体…",
  agentsEmpty: "暂无智能体。",
  workspaceDir: "工作区",
  runStatus: "运行状态",
  actions: "操作",
  agentNotConfigured: "未配置",
  activeRuns: "进行中",
  useInChat: "在聊天中使用",
};

const MESSAGES: Record<DesktopLocale, Record<string, string>> = {
  en,
  "zh-CN": zhCN,
};

function detectInitialLocale(): DesktopLocale {
  if (typeof window === "undefined") return "en";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)?.trim();
    if (stored === "zh-CN" || stored === "en") return stored;
  } catch {
    /* ignore */
  }
  const nav = (navigator.language || "").toLowerCase();
  if (nav.startsWith("zh")) return "zh-CN";
  return "en";
}

type I18nContextValue = {
  locale: DesktopLocale;
  setLocale: (loc: DesktopLocale) => void;
  t: (key: keyof typeof en | string, params?: Params) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<DesktopLocale>("en");

  useEffect(() => {
    setLocaleState(detectInitialLocale());
  }, []);

  const setLocale = useCallback((loc: DesktopLocale) => {
    setLocaleState(loc);
    try {
      window.localStorage.setItem(STORAGE_KEY, loc);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: string, params?: Params) => {
      const table = MESSAGES[locale];
      const raw = table[key] ?? MESSAGES.en[key] ?? key;
      return interpolate(raw, params);
    },
    [locale]
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t]
  );

  return (
    <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return ctx;
}
