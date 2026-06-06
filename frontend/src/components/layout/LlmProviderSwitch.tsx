import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { meApi, type LlmProvider, type LlmProviderOption } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const FALLBACK_OPTIONS: LlmProviderOption[] = [
  { id: "gemini", label: "Google Gemini", available: true },
  { id: "deepseek", label: "DeepSeek", available: true },
];

export default function LlmProviderSwitch() {
  const { t } = useTranslation();
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);
  const current = profile?.preferences.llm_provider ?? "gemini";

  const [options, setOptions] = useState<LlmProviderOption[]>(FALLBACK_OPTIONS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    meApi
      .llmProviders()
      .then((res) => setOptions(res.data.providers))
      .catch(() => setOptions(FALLBACK_OPTIONS));
  }, []);

  async function handleChange(next: LlmProvider) {
    if (next === current || saving) return;
    const option = options.find((o) => o.id === next);
    if (option && !option.available) {
      setError(t("llm.apiKeyMissing"));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const { data } = await meApi.updatePreferences({ llm_provider: next });
      setProfile(data);
    } catch {
      setError(t("llm.switchFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-400">
        <Bot className="h-3.5 w-3.5" />
        {t("llm.title")}
        {saving && <Loader2 className="h-3 w-3 animate-spin" />}
      </div>
      <div
        role="radiogroup"
        aria-label={t("llm.selectAria")}
        className="grid grid-cols-2 gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1"
      >
        {options.map((option) => {
          const active = current === option.id;
          const disabled = saving || (!option.available && !active);
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => void handleChange(option.id)}
              className={cn(
                "min-h-12 rounded-md px-2 py-2 text-xs font-medium transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-1",
                active
                  ? "bg-white text-violet-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-800",
                disabled && !active && "cursor-not-allowed opacity-40"
              )}
              title={
                option.available
                  ? option.label
                  : t("llm.notConfigured", { label: option.label })
              }
            >
              {option.id === "gemini" ? "Gemini" : "DeepSeek"}
            </button>
          );
        })}
      </div>
      {error && <p className="mt-1.5 text-[11px] text-red-500">{error}</p>}
    </div>
  );
}
