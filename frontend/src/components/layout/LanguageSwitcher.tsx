import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react";
import { cn } from "@/lib/utils";
import { meApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

interface Props {
  className?: string;
  variant?: "default" | "compact";
}

export default function LanguageSwitcher({ className, variant = "default" }: Props) {
  const { i18n, t } = useTranslation();
  const token = useAuthStore((s) => s.token);
  const setProfile = useAuthStore((s) => s.setProfile);

  async function switchTo(lang: "en" | "zh") {
    if (i18n.language === lang) return;
    await i18n.changeLanguage(lang);
    if (token) {
      try {
        const { data } = await meApi.updatePreferences({ locale: lang });
        setProfile(data);
      } catch {
        /* UI locale still switched locally */
      }
    }
  }

  const current = i18n.language === "zh" ? "zh" : "en";

  if (variant === "compact") {
    return (
      <button
        type="button"
        onClick={() => void switchTo(current === "en" ? "zh" : "en")}
        className={cn(
          "flex min-h-10 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          "text-gray-500 hover:bg-gray-100 hover:text-gray-900",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
          className
        )}
        aria-label={t("language.switch")}
      >
        <Languages className="h-4 w-4 shrink-0" />
        {current === "en" ? "中文" : "EN"}
      </button>
    );
  }

  return (
    <div
      className={cn("flex items-center gap-2", className)}
      role="group"
      aria-label={t("language.switch")}
    >
      <Languages className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex rounded-lg border border-gray-200 bg-gray-50 p-0.5">
        <button
          type="button"
          onClick={() => void switchTo("en")}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
            current === "en"
              ? "bg-white text-violet-700 shadow-sm"
              : "text-gray-500 hover:text-gray-800"
          )}
          aria-pressed={current === "en"}
        >
          English
        </button>
        <button
          type="button"
          onClick={() => void switchTo("zh")}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
            current === "zh"
              ? "bg-white text-violet-700 shadow-sm"
              : "text-gray-500 hover:text-gray-800"
          )}
          aria-pressed={current === "zh"}
        >
          中文
        </button>
      </div>
    </div>
  );
}
