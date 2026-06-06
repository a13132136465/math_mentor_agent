import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  CheckCircle2,
  Clock,
  Lightbulb,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
  ThumbsUp,
  TrendingUp,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import ExerciseSetRow from "@/components/exercises/ExerciseSetRow";
import TopicProgress from "@/components/mastery/TopicProgress";
import { refreshProfile } from "@/lib/profile";
import { useAuthStore } from "@/store/auth";
import { meApi, exercisesApi } from "@/lib/api";
import type {
  LearningAnalytics,
  MasteryHistoryResponse,
  ExerciseSet,
  ErrorFrequency,
} from "@/lib/api";
import {
  cn,
  formatDateTime,
  formatPct,
  formatTag,
  topicLabel,
} from "@/lib/utils";

const TOPICS = ["limits", "derivatives", "integrals"] as const;
type TopicKey = (typeof TOPICS)[number];

const TOPIC_COLORS: Record<TopicKey, string> = {
  limits: "#3b82f6",
  derivatives: "#7c3aed",
  integrals: "#f59e0b",
};

function severityStyle(severity: ErrorFrequency["severity"]) {
  if (severity === "high") return "border-red-200 bg-red-50 text-red-700";
  if (severity === "medium") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-gray-200 bg-gray-50 text-gray-600";
}

function buildChartData(history: MasteryHistoryResponse | null) {
  if (!history) return [];

  const byTime = new Map<string, Record<string, number | string>>();

  for (const topic of TOPICS) {
    for (const point of history[topic]) {
      const key = point.created_at;
      const row = byTime.get(key) ?? { time: formatDateTime(key) };
      row[topic] = Math.round(point.score_after * 100);
      byTime.set(key, row);
    }
  }

  return Array.from(byTime.entries())
    .sort(([a], [b]) => new Date(a).getTime() - new Date(b).getTime())
    .map(([, row]) => row);
}

export default function ReportPage() {
  const { t } = useTranslation();
  const { profile } = useAuthStore();
  const navigate = useNavigate();

  const [analytics, setAnalytics] = useState<LearningAnalytics | null>(null);
  const [history, setHistory] = useState<MasteryHistoryResponse | null>(null);
  const [exercises, setExercises] = useState<ExerciseSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [analyticsRes, historyRes, exercisesRes] = await Promise.allSettled([
        meApi.analytics(),
        meApi.masteryHistory(),
        exercisesApi.all(),
      ]);

      if (analyticsRes.status === "fulfilled") {
        setAnalytics(analyticsRes.value.data);
      } else {
        throw new Error("Failed to load analytics");
      }

      if (historyRes.status === "fulfilled") {
        setHistory(historyRes.value.data);
      }

      if (exercisesRes.status === "fulfilled") {
        setExercises(exercisesRes.value.data);
      }

      await refreshProfile();
    } catch {
      setError(t("report.loadError"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const mastery = profile?.mastery;
  const chartData = useMemo(() => buildChartData(history), [history]);
  const hasHistory = chartData.length > 0;

  const pendingExercises = exercises.filter((e) =>
    e.problems.some((p) => p.status === "pending")
  );

  return (
    <div className="space-y-8 p-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-violet-600" />
            <h1 className="text-2xl font-bold">{t("report.title")}</h1>
          </div>
          <p className="mt-1 text-muted-foreground">{t("report.subtitle")}</p>
          {analytics && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("report.lastUpdated", { date: formatDateTime(analytics.computed_at) })}
              {analytics.deterministic_only && t("report.ruleBasedOnly")}
            </p>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={refreshing}
            onClick={() => void load(true)}
          >
            {refreshing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {t("common.refresh")}
          </Button>
          <Button size="sm" className="gap-2" onClick={() => navigate("/problem")}>
            <Target className="h-4 w-4" />
            {t("common.practice")}
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="flex items-center gap-3 p-4 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </CardContent>
        </Card>
      )}

      {/* Mastery + Timeline */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("report.masteryByTopic")}</CardTitle>
            <CardDescription>{t("report.masteryByTopicDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {loading ? (
              <div className="space-y-4">
                {TOPICS.map((topic) => <Skeleton key={topic} className="h-10 w-full" />)}
              </div>
            ) : mastery ? (
              TOPICS.map((topic) => (
                <TopicProgress
                  key={topic}
                  topic={topic}
                  score={analytics?.mastery_scores[topic] ?? mastery[topic].score}
                  attempts={mastery[topic].attempts}
                />
              ))
            ) : (
              <p className="text-sm text-muted-foreground">{t("report.noMastery")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>{t("report.masteryOverTime")}</CardTitle>
                <CardDescription>{t("report.masteryOverTimeDesc")}</CardDescription>
              </div>
              <TrendingUp className="h-5 w-5 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-56 w-full" />
            ) : hasHistory ? (
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 10, fill: "#6b7280" }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fontSize: 10, fill: "#9ca3af" }}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip
                      formatter={(v) => [`${v}%`, t("common.mastery")]}
                      contentStyle={{ fontSize: 12 }}
                    />
                    <Legend />
                    {TOPICS.map((topic) => (
                      <Line
                        key={topic}
                        type="monotone"
                        dataKey={topic}
                        name={topicLabel(topic)}
                        stroke={TOPIC_COLORS[topic]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-56 flex-col items-center justify-center gap-2 text-center">
                <Clock className="h-8 w-8 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">{t("report.noHistory")}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2 border-violet-100 bg-gradient-to-br from-violet-50 to-indigo-50">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-violet-600" />
                <CardTitle className="text-sm text-violet-700">{t("report.aiTip")}</CardTitle>
              </div>
              {analytics && (
                <Badge variant="outline" className="border-violet-200 bg-white text-violet-600 text-xs">
                  {t("report.confidence", { pct: Math.round(analytics.confidence * 100) })}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            ) : analytics?.learning_tip ? (
              <p className="text-sm leading-relaxed text-violet-900">
                {analytics.learning_tip}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">{t("report.tipPlaceholder")}</p>
            )}

            {analytics && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-violet-700">
                  {t("report.focusNext")}
                </span>
                <Badge variant="outline" className="border-violet-300 bg-white text-violet-700">
                  {topicLabel(analytics.recommended_next_topic)}
                </Badge>
                {analytics.recommended_subtopic && (
                  <Badge variant="outline" className="border-violet-200 bg-white text-violet-600 text-xs">
                    {formatTag(analytics.recommended_subtopic)}
                  </Badge>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-emerald-600" />
              <CardTitle className="text-sm">{t("report.strengths")}</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-24" />
                <Skeleton className="h-6 w-32" />
              </div>
            ) : analytics && analytics.strengths.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {analytics.strengths.map((s) => (
                  <Badge
                    key={s}
                    variant="outline"
                    className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs capitalize"
                  >
                    <ThumbsUp className="mr-1 h-3 w-3" />
                    {formatTag(s)}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("report.strengthsPlaceholder")}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Weaknesses + Errors */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Target className="h-4 w-4 text-red-500" />
              <CardTitle className="text-sm">{t("report.areasToImprove")}</CardTitle>
            </div>
            <CardDescription>{t("report.areasDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                <Skeleton className="h-6 w-28" />
                <Skeleton className="h-6 w-36" />
              </div>
            ) : analytics && analytics.weaknesses.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {analytics.weaknesses.map((w) => (
                  <Badge
                    key={w}
                    variant="outline"
                    className="border-red-200 bg-red-50 text-red-600 text-xs capitalize"
                  >
                    {formatTag(w)}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("report.noWeaknesses")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <CardTitle className="text-sm">{t("report.errorPatterns")}</CardTitle>
            </div>
            <CardDescription>{t("report.errorDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            ) : analytics && analytics.error_summary.length > 0 ? (
              <div className="space-y-2">
                {analytics.error_summary.map((err) => (
                  <div
                    key={err.tag}
                    className="flex items-center justify-between rounded-lg border px-3 py-2"
                  >
                    <span className="text-sm capitalize">{formatTag(err.tag)}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">×{err.count}</span>
                      <Badge
                        variant="outline"
                        className={cn("text-xs capitalize", severityStyle(err.severity))}
                      >
                        {t(`severity.${err.severity}`)}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("report.noErrors")}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Separator />

      {/* Exercises */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <div className="flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-violet-600" />
              <CardTitle>{t("report.practiceDrills")}</CardTitle>
            </div>
            <CardDescription>
              {pendingExercises.length > 0
                ? t("report.pendingSets", { count: pendingExercises.length })
                : t("report.allSetsDesc")}
            </CardDescription>
          </div>
          {exercises.length > 0 && (
            <Badge variant="secondary">
              {t("report.total", { count: exercises.length })}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
            </div>
          ) : exercises.length > 0 ? (
            exercises.map((e) => (
              <ExerciseSetRow
                key={e.id}
                set={e}
                showRationale
                onOpen={(id) => navigate(`/exercises/${id}`)}
              />
            ))
          ) : (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
                <CheckCircle2 className="h-6 w-6 text-emerald-500" />
              </div>
              <div>
                <p className="text-sm font-medium">{t("report.noDrills")}</p>
                <p className="text-xs text-muted-foreground">{t("report.noDrillsHint")}</p>
              </div>
              <Button size="sm" variant="outline" onClick={() => navigate("/problem")}>
                {t("report.startSession")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
