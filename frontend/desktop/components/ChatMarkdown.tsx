"use client";

import type { Components } from "react-markdown";
import { useTheme } from "next-themes";
import { useMemo } from "react";
import { MarkdownHooks } from "react-markdown";
import rehypeShiki from "@shikijs/rehype";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import type { Schema } from "hast-util-sanitize";
import type { PluggableList } from "unified";

/** Subset of Shiki grammars for chat-sized bundles; unknown langs fall back. */
const CHAT_SHIKI_LANGS = [
  "bash",
  "c",
  "cpp",
  "csharp",
  "css",
  "diff",
  "go",
  "html",
  "java",
  "javascript",
  "json",
  "kotlin",
  "markdown",
  "mdx",
  "php",
  "python",
  "ruby",
  "rust",
  "shell",
  "sql",
  "swift",
  "toml",
  "tsx",
  "typescript",
  "vue",
  "xml",
  "yaml",
  "text",
  "plaintext",
] as const;

const chatSanitizeSchema: Schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [
      ...(defaultSchema.attributes?.code ?? []),
      ["className", /^shiki/],
      ["className", /^language-/],
    ],
    pre: [...(defaultSchema.attributes?.pre ?? []), "className", "style", "tabIndex"],
    span: [...(defaultSchema.attributes?.span ?? []), "className", "style"],
  },
};

function chatMarkdownComponents(compact: boolean): Components {
  const linkClass =
    "text-[var(--accent)] underline underline-offset-2 decoration-[var(--accent)]/70 hover:opacity-90 break-all";
  const h1 = compact ? "mt-3 mb-1.5 text-base font-semibold leading-snug first:mt-0" : "mt-4 mb-2 text-lg font-semibold leading-snug first:mt-0";
  const h2 = compact ? "mt-2 mb-1.5 text-sm font-semibold leading-snug first:mt-0" : "mt-3 mb-2 text-base font-semibold leading-snug first:mt-0";
  const h3 = compact ? "mt-2 mb-1 text-xs font-semibold leading-snug first:mt-0" : "mt-3 mb-1.5 text-sm font-semibold leading-snug first:mt-0";
  const h4 = compact ? "mt-1.5 mb-0.5 text-xs font-medium leading-snug first:mt-0" : "mt-2 mb-1 text-sm font-medium leading-snug first:mt-0";
  const tableText = compact ? "text-[11px]" : "text-[13px]";
  const preText = compact ? "my-1.5 p-2 text-[11px]" : "my-2 p-3 text-[13px]";
  return {
    h1: ({ children }) => <h1 className={h1}>{children}</h1>,
    h2: ({ children }) => <h2 className={h2}>{children}</h2>,
    h3: ({ children }) => <h3 className={h3}>{children}</h3>,
    h4: ({ children }) => <h4 className={h4}>{children}</h4>,
    p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0 leading-relaxed">{children}</p>,
    ul: ({ children }) => (
      <ul className="my-2 list-disc pl-5 space-y-1 first:mt-0 last:mb-0">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="my-2 list-decimal pl-5 space-y-1 first:mt-0 last:mb-0">{children}</ol>
    ),
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-[3px] border-[var(--accent)]/50 pl-3 text-[var(--muted)] italic">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-4 border-[var(--border)]" />,
    a: ({ href, children, ...props }) => (
      <a
        href={href}
        className={linkClass}
        target="_blank"
        rel="noopener noreferrer"
        {...props}
      >
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="my-2 overflow-x-auto rounded-md border border-[var(--border)] first:mt-0 last:mb-0">
        <table className={`w-full border-collapse text-left ${tableText}`}>{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-[var(--panel)]">{children}</thead>,
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => <tr className="border-b border-[var(--border)] last:border-0">{children}</tr>,
    th: ({ children }) => (
      <th className="border border-[var(--border)] px-2 py-1.5 font-semibold">{children}</th>
    ),
    td: ({ children }) => <td className="border border-[var(--border)] px-2 py-1.5">{children}</td>,
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    em: ({ children }) => <em className="italic">{children}</em>,
    del: ({ children }) => <del className="line-through opacity-80">{children}</del>,
    code: ({ className, children, ...props }) => {
      const isBlock =
        Boolean(className?.includes("language-")) || Boolean(className?.includes("shiki"));
      if (isBlock) {
        return (
          <code className={className} {...props}>
            {children}
          </code>
        );
      }
      return (
        <code
          className="rounded bg-[var(--panel)] px-1.5 py-0.5 text-[0.9em] font-mono border border-[var(--border)]/60"
          {...props}
        >
          {children}
        </code>
      );
    },
    pre: ({ children, ...props }) => (
      <pre
        className={`overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--panel)] leading-relaxed first:mt-0 last:mb-0 ${preText}`}
        {...props}
      >
        {children}
      </pre>
    ),
    img: ({ src, alt, ...props }) => (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={typeof src === "string" ? src : undefined}
        alt={alt ?? ""}
        className="my-2 max-h-64 max-w-full rounded-md border border-[var(--border)] object-contain"
        {...props}
      />
    ),
  };
}

export type ChatMarkdownProps = {
  text: string;
  role: "user" | "assistant";
  /** Smaller base type (e.g. orchestration transcript). */
  compact?: boolean;
};

/**
 * GFM markdown + Shiki highlighting (async pipeline via MarkdownHooks).
 */
export function ChatMarkdown({ text, role, compact }: ChatMarkdownProps) {
  const { resolvedTheme } = useTheme();
  const shikiTheme = resolvedTheme === "dark" ? "github-dark" : "github-light";

  const rehypePlugins = useMemo((): PluggableList => {
    return [
      [
        rehypeShiki,
        {
          theme: shikiTheme,
          langs: [...CHAT_SHIKI_LANGS],
          fallbackLanguage: "text",
          defaultLanguage: "text",
          addLanguageClass: true,
        },
      ],
      [rehypeSanitize, chatSanitizeSchema],
    ];
  }, [shikiTheme]);

  const remarkPlugins = useMemo(() => [remarkGfm], []);
  const components = useMemo(() => chatMarkdownComponents(!!compact), [compact]);

  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  return (
    <div
      className={`chat-md ${compact ? "text-xs" : "text-sm"} leading-relaxed text-[var(--text)] [word-break:break-word] ${
        role === "user" ? "chat-md-user" : "chat-md-assistant"
      }`}
    >
      <MarkdownHooks
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
        fallback={
          <div className="text-[var(--muted)] text-xs animate-pulse" aria-hidden>
            …
          </div>
        }
      >
        {trimmed}
      </MarkdownHooks>
    </div>
  );
}
