import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bell, Loader2, Settings, Sparkles } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { meApi, type StudentPreferences } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

type HintStyle = StudentPreferences["hint_style"];

const HINT_STYLES: HintStyle[] = ["gentle", "balanced", "challenging"];

export default function SettingsPage() {
  const { t } = useTranslation();
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);
  const prefs = profile?.preferences;

  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function savePreference(patch: Partial<StudentPreferences>, key: string) {
    setSaving(key);
    setError(null);
    setSuccess(null);
    try {
      const { data } = await meApi.updatePreferences(patch);
      setProfile(data);
      setSuccess(t("settings.saved"));
    } catch {
      setError(t("settings.saveError"));
    } finally {
      setSaving(null);
    }
  }

  if (!prefs) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        {t("common.loading")}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-8">
      <div>
        <div className="flex items-center gap-2">
          <Settings className="h-7 w-7 text-violet-600" />
          <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
        </div>
        <p className="mt-1 text-muted-foreground">{t("settings.subtitle")}</p>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </p>
      )}
      {success && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {success}
        </p>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-violet-600" />
            <CardTitle className="text-base">{t("settings.hintStyle")}</CardTitle>
          </div>
          <CardDescription>{t("settings.hintStyleDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            role="radiogroup"
            aria-label={t("settings.hintStyle")}
            className="grid gap-2 sm:grid-cols-3"
          >
            {HINT_STYLES.map((style) => {
              const active = prefs.hint_style === style;
              const busy = saving === "hint_style";
              return (
                <button
                  key={style}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={busy}
                  onClick={() => void savePreference({ hint_style: style }, "hint_style")}
                  className={cn(
                    "rounded-lg border p-4 text-left transition-colors",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
                    active
                      ? "border-violet-300 bg-violet-50"
                      : "border-gray-200 hover:border-gray-300 hover:bg-muted/30"
                  )}
                >
                  <p className="text-sm font-semibold capitalize">
                    {t(`settings.hintStyles.${style}`)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t(`settings.hintStyles.${style}Desc`)}
                  </p>
                </button>
              );
            })}
          </div>
          {saving === "hint_style" && (
            <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t("settings.saving")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("settings.display")}</CardTitle>
          <CardDescription>{t("settings.displayDesc")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex items-center justify-between gap-4 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">{t("settings.latexEnabled")}</p>
              <p className="text-xs text-muted-foreground">{t("settings.latexEnabledDesc")}</p>
            </div>
            <Button
              variant={prefs.latex_enabled ? "default" : "outline"}
              size="sm"
              disabled={saving === "latex_enabled"}
              onClick={() =>
                void savePreference({ latex_enabled: !prefs.latex_enabled }, "latex_enabled")
              }
            >
              {prefs.latex_enabled ? t("common.on") : t("common.off")}
            </Button>
          </label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-violet-600" />
            <CardTitle className="text-base">{t("settings.notifications")}</CardTitle>
          </div>
          <CardDescription>{t("settings.notificationsDesc")}</CardDescription>
        </CardHeader>
        <CardContent>
          <label className="flex items-center justify-between gap-4 rounded-lg border p-4">
            <div>
              <p className="text-sm font-medium">{t("settings.notifyExercises")}</p>
              <p className="text-xs text-muted-foreground">{t("settings.notifyExercisesDesc")}</p>
            </div>
            <Button
              variant={prefs.notify_exercises ? "default" : "outline"}
              size="sm"
              disabled={saving === "notify_exercises"}
              onClick={() =>
                void savePreference(
                  { notify_exercises: !prefs.notify_exercises },
                  "notify_exercises"
                )
              }
            >
              {prefs.notify_exercises ? t("common.on") : t("common.off")}
            </Button>
          </label>
        </CardContent>
      </Card>
    </div>
  );
}
