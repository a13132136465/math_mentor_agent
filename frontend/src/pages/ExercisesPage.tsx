/**
 * Practice drills — due queue, all sets, quick practice.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  CheckCircle2,
  Clock,
  ListChecks,
} from "lucide-react";

import ExerciseSetRow from "@/components/exercises/ExerciseSetRow";
import QuickPracticeCard from "@/components/exercises/QuickPracticeCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { refreshProfile } from "@/lib/profile";
import { exercisesApi, type ExerciseSet } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "due" | "all";

export default function ExercisesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("due");
  const [dueSets, setDueSets] = useState<ExerciseSet[]>([]);
  const [allSets, setAllSets] = useState<ExerciseSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dueRes, allRes] = await Promise.all([
        exercisesApi.due(),
        exercisesApi.all(),
      ]);
      setDueSets(dueRes.data);
      setAllSets(allRes.data);
      await refreshProfile();
    } catch {
      setError(t("exercises.loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const displayed = tab === "due" ? dueSets : allSets;
  const dueCount = dueSets.reduce(
    (n, s) => n + s.problems.filter((p) => p.status === "pending").length,
    0
  );

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BookOpen className="h-7 w-7 text-violet-600" />
          {t("exercises.title")}
        </h1>
        <p className="mt-1 text-muted-foreground">{t("exercises.subtitle")}</p>
      </div>

      <QuickPracticeCard />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="h-5 w-5 text-violet-600" />
              {t("exercises.exerciseSets")}
            </CardTitle>
            <CardDescription>
              {dueCount > 0
                ? t("exercises.dueNow", { count: dueCount })
                : t("exercises.completeSessionHint")}
            </CardDescription>
          </div>
          <div className="flex rounded-lg border p-0.5">
            <button
              type="button"
              onClick={() => setTab("due")}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                tab === "due" ? "bg-violet-100 text-violet-700" : "text-muted-foreground"
              )}
            >
              {t("exercises.tabDue")}
            </button>
            <button
              type="button"
              onClick={() => setTab("all")}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                tab === "all" ? "bg-violet-100 text-violet-700" : "text-muted-foreground"
              )}
            >
              {t("exercises.tabAll")}
            </button>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {error && <p className="text-sm text-red-600">{error}</p>}

          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))}
            </div>
          ) : displayed.length > 0 ? (
            displayed.map((s) => (
              <ExerciseSetRow
                key={s.id}
                set={s}
                showDueDate={tab === "due"}
                onOpen={(id) => navigate(`/exercises/${id}`)}
              />
            ))
          ) : (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
                {tab === "due" ? (
                  <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                ) : (
                  <Clock className="h-6 w-6 text-muted-foreground" />
                )}
              </div>
              <div>
                <p className="text-sm font-medium">
                  {tab === "due" ? t("exercises.allCaughtUp") : t("exercises.noSets")}
                </p>
                <p className="text-xs text-muted-foreground">
                  {tab === "due" ? t("exercises.noDue") : t("exercises.noSetsHint")}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => navigate("/problem")}>
                {t("exercises.startSession")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
