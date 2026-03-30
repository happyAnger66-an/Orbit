"use client";

type TFn = (key: string, params?: Record<string, string | number | undefined>) => string;

export function ChatThinkToolCheckbox(props: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  t: TFn;
}) {
  const { checked, onChange, disabled, t } = props;
  return (
    <label
      className="flex items-center gap-1.5 text-[10px] text-[var(--muted)] cursor-pointer select-none"
      title={t("chatShowReasoning")}
    >
      <input
        type="checkbox"
        className="rounded border-[var(--border)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span className="whitespace-nowrap">{t("chatThinkTool")}</span>
    </label>
  );
}
