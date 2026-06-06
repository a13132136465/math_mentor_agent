/**
 * Single exercise set — work through all problems.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, BookOpen, Loader2 } from "lucide-react";

import ExerciseProblemCard from "@/components/exercises/ExerciseProblemCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { exercisesApi, type ExerciseSet } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function ExerciseSetPage() {
  const { t } = useTranslation();
  const { setId } = useParams<{ setId: string }>();
  const navigate = useNavigate();
  const [set, setSet] = useState<ExerciseSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!setId) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await exercisesApi.get(setId);
      setSet(data);
    } catch {
      setError(t("exercises.notFound"));
      setSet(null);
    } finally {
      setLoading(false);
    }
  }, [setId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!setId) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        {t("exercises.invalidLink")}
      </div>
    );
  }

  const problems = set?.problems ?? [];
  const pending = problems.filter((p) => p.status === "pending").length;
  const total = problems.length;
  const done = total - pending;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" className="gap-1" asChild>
          <Link to="/exercises">
            <ArrowLeft className="h-4 w-4" />
            {t("exercises.allDrills")}
          </Link>
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error || !set ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">{error ?? t("common.notFound")}</p>
            <Button className="mt-4" variant="outline" onClick={() => navigate("/exercises")}>
              {t("exercises.backToDrills")}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-violet-600" />
                    {t("exercises.practiceSet")}
                  </CardTitle>
                  <CardDescription className="mt-1">
                    {set.generation_meta.rationale || t("exercises.personalised")}
                  </CardDescription>
                </div>
                <Badge variant="secondary" className="capitalize shrink-0">
                  {set.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{t("common.progress")}</span>
                <span className="font-medium">
                  {t("exercises.complete", { done, total, pct })}
                </span>
              </div>
              <Progress value={pct} className="h-2" />
              <p className="text-xs text-muted-foreground">
                {t("common.due")} {formatDateTime(set.spaced_repetition.due_at)} · {t("common.source")}:{" "}
                {set.generation_meta.source}
              </p>
            </CardContent>
          </Card>

          <div className="space-y-6">
            {problems.map((problem, index) => (
              <ExerciseProblemCard
                key={problem.id}
                exerciseSetId={set.id}
                problem={problem}
                index={index}
                total={total}
                onUpdated={() => void load()}
              />
            ))}
          </div>

          {pending === 0 && total > 0 && (
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardContent className="py-6 text-center">
                <p className="font-medium text-emerald-800">{t("exercises.setComplete")}</p>
                <Button
                  className="mt-3"
                  variant="outline"
                  onClick={() => navigate("/exercises")}
                >
                  {t("exercises.backToAll")}
                </Button>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
