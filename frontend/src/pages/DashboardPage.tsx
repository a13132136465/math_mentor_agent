import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  BookOpen, Flame, Trophy, Target,
  ArrowRight, Plus, CheckCircle2, AlertCircle,
  Lightbulb, ChevronRight, Clock, BarChart3,
} from "lucide-react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import ExerciseSetRow from "@/components/exercises/ExerciseSetRow";
import { useAuthStore } from "@/store/auth";
import { meApi, sessionsApi, exercisesApi } from "@/lib/api";
import type { SessionSummary, ExerciseSet } from "@/lib/api";
import { topicLabel } from "@/lib/utils";

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "text-violet-600",
  bg = "bg-violet-50",
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  bg?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl shrink-0 ${bg}`}>
          <Icon className={`h-5 w-5 ${color}`} />
        </div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function SessionRow({ session }: { session: SessionSummary }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const statusIcon =
    session.status === "completed" ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    ) : session.status === "active" ? (
      <Clock className="h-4 w-4 text-amber-500" />
    ) : (
      <AlertCircle className="h-4 w-4 text-muted-foreground" />
    );

  return (
    <button
      type="button"
      onClick={() => navigate(`/chat/${session.id}`)}
      aria-label={t("dashboard.continueSession", { text: session.problem_text })}
      className="flex w-full min-h-12 items-center gap-3 rounded-lg p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
    >
      {statusIcon}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{session.problem_text}</p>
        <p className="text-xs text-muted-foreground">
          {session.topic ? topicLabel(session.topic) : "—"} · {t("common.turns", { count: session.turn_count })}
        </p>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { profile } = useAuthStore();
  const navigate = useNavigate();

  const [tip, setTip] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [exercises, setExercises] = useState<ExerciseSet[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [analyticsRes, sessionsRes, exercisesRes] = await Promise.allSettled([
          meApi.analytics(),
          sessionsApi.list(),
          exercisesApi.due(),
        ]);
        if (analyticsRes.status === "fulfilled") {
          setTip(analyticsRes.value.data.learning_tip || null);
        }
        if (sessionsRes.status === "fulfilled") {
          setSessions(sessionsRes.value.data.slice(0, 5));
        }
        if (exercisesRes.status === "fulfilled") {
          setExercises(exercisesRes.value.data.slice(0, 3));
        }
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const mastery = profile?.mastery;
  const stats = profile?.stats;

  const radarData = mastery
    ? [
        { subject: topicLabel("limits"),      score: Math.round(mastery.limits.score * 100) },
        { subject: topicLabel("derivatives"), score: Math.round(mastery.derivatives.score * 100) },
        { subject: topicLabel("integrals"),   score: Math.round(mastery.integrals.score * 100) },
      ]
    : [];

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? t("dashboard.greetingMorning") :
    hour < 18 ? t("dashboard.greetingAfternoon") :
    t("dashboard.greetingEvening");

  return (
    <div className="space-y-8 p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {greeting}, {profile?.display_name?.split(" ")[0] ?? t("common.student")} 👋
          </h1>
          <p className="mt-1 text-muted-foreground">{t("dashboard.overview")}</p>
        </div>
        <Button onClick={() => navigate("/problem")} className="gap-2 shrink-0">
          <Plus className="h-4 w-4" />
          {t("dashboard.newProblem")}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={Flame}
          label={t("dashboard.dayStreak")}
          value={stats?.streak_days ?? 0}
          sub={t("dashboard.daysInRow")}
          color="text-orange-500"
          bg="bg-orange-50"
        />
        <StatCard
          icon={BookOpen}
          label={t("dashboard.sessions")}
          value={stats?.total_sessions ?? 0}
          sub={t("dashboard.totalSessions")}
          color="text-blue-500"
          bg="bg-blue-50"
        />
        <StatCard
          icon={Target}
          label={t("dashboard.stepsSolved")}
          value={stats?.total_steps_submitted ?? 0}
          sub={t("dashboard.totalSteps")}
          color="text-violet-600"
          bg="bg-violet-50"
        />
        <StatCard
          icon={Trophy}
          label={t("dashboard.exercisesDone")}
          value={stats?.total_exercises_done ?? 0}
          sub={t("dashboard.completedDrills")}
          color="text-amber-500"
          bg="bg-amber-50"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>{t("dashboard.masterySnapshot")}</CardTitle>
                <CardDescription>{t("dashboard.masterySnapshotDesc")}</CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="gap-1 text-xs text-muted-foreground"
                onClick={() => navigate("/report")}
              >
                <BarChart3 className="h-3.5 w-3.5" />
                {t("dashboard.fullReport")}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {mastery ? (
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#e5e7eb" />
                    <PolarAngleAxis
                      dataKey="subject"
                      tick={{ fontSize: 12, fill: "#6b7280" }}
                    />
                    <PolarRadiusAxis
                      angle={90}
                      domain={[0, 100]}
                      tick={{ fontSize: 10, fill: "#9ca3af" }}
                    />
                    <Radar
                      name={t("common.mastery")}
                      dataKey="score"
                      stroke="#7c3aed"
                      fill="#7c3aed"
                      fillOpacity={0.2}
                      strokeWidth={2}
                    />
                    <Tooltip
                      formatter={(v) => [`${v}%`, t("common.mastery")]}
                      contentStyle={{ fontSize: 12 }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="border-violet-100 bg-gradient-to-br from-violet-50 to-indigo-50">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-violet-600" />
                <CardTitle className="text-sm text-violet-700">{t("dashboard.aiTip")}</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-3/4" />
                </div>
              ) : tip ? (
                <p className="text-sm leading-relaxed text-violet-900 line-clamp-4">{tip}</p>
              ) : (
                <p className="text-sm text-muted-foreground">{t("dashboard.tipPlaceholder")}</p>
              )}
              <Button
                variant="link"
                size="sm"
                className="mt-3 h-auto p-0 text-violet-700"
                onClick={() => navigate("/report")}
              >
                {t("dashboard.viewFullReport")}
                <ArrowRight className="ml-1 h-3.5 w-3.5" />
              </Button>
            </CardContent>
          </Card>

          <Card
            role="button"
            tabIndex={0}
            className="cursor-pointer border-dashed transition-colors hover:border-violet-300 hover:bg-violet-50/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
            onClick={() => navigate("/problem")}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                navigate("/problem");
              }
            }}
            aria-label={t("dashboard.startProblemAria")}
          >
            <CardContent className="flex items-center justify-between p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-100">
                  <Plus className="h-4 w-4 text-violet-600" />
                </div>
                <div>
                  <p className="text-sm font-semibold">{t("dashboard.startProblem")}</p>
                  <p className="text-xs text-muted-foreground">{t("dashboard.startProblemDesc")}</p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle>{t("dashboard.recentSessions")}</CardTitle>
              <CardDescription>{t("dashboard.recentSessionsDesc")}</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground"
              onClick={() => navigate("/chat")}
            >
              {t("common.viewAll")}
            </Button>
          </CardHeader>
          <CardContent className="px-3 pb-3">
            {loading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}
              </div>
            ) : sessions.length > 0 ? (
              <div className="divide-y">
                {sessions.map((s) => <SessionRow key={s.id} session={s} />)}
              </div>
            ) : (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {t("dashboard.noSessions")}{" "}
                <button
                  type="button"
                  onClick={() => navigate("/problem")}
                  className="text-violet-600 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 rounded-sm"
                >
                  {t("dashboard.startFirst")}
                </button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div>
              <CardTitle>{t("dashboard.dueExercises")}</CardTitle>
              <CardDescription>{t("dashboard.dueExercisesDesc")}</CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-muted-foreground gap-1"
              onClick={() => navigate("/exercises")}
            >
              {t("dashboard.allDrills")}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 pb-4">
            {loading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
              </div>
            ) : exercises.length > 0 ? (
              exercises.map((e) => (
                <ExerciseSetRow
                  key={e.id}
                  set={e}
                  onOpen={(id) => navigate(`/exercises/${id}`)}
                />
              ))
            ) : (
              <div className="flex flex-col items-center gap-3 py-8 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
                  <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                </div>
                <div>
                  <p className="text-sm font-medium">{t("dashboard.allCaughtUp")}</p>
                  <p className="text-xs text-muted-foreground">{t("dashboard.noExercisesDue")}</p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
