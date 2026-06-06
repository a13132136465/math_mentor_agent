/**
 * Interactive exercise problem — attempt, submit, reveal answer.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  BookOpen,
  CheckCircle2,
  Eye,
  Loader2,
  SkipForward,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import LatexRenderer from "@/components/ui/latex-renderer";
import MixedMathInputField from "@/components/ui/mixed-math-input-field";
import { exercisesApi, type ExerciseProblem } from "@/lib/api";
import { refreshProfile } from "@/lib/profile";
import { serializeMathliveToApi } from "@/lib/math-problem";
import { cn, difficultyColor, difficultyLabel, formatTag, topicLabel } from "@/lib/utils";

interface Props {
  exerciseSetId: string;
  problem: ExerciseProblem;
  index: number;
  total: number;
  onUpdated: () => void;
}

export default function ExerciseProblemCard({
  exerciseSetId,
  problem,
  index,
  total,
  onUpdated,
}: Props) {
  const { t } = useTranslation();
  const isDone = problem.status === "completed" || problem.status === "skipped";
  const [answerDraft, setAnswerDraft] = useState(problem.student_answer ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [revealedAnswer, setRevealedAnswer] = useState<string | null>(null);
  const [revealLoading, setRevealLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(status: "completed" | "skipped") {
    setSubmitting(true);
    setError(null);
    try {
      const studentAnswer =
        status === "completed" ? serializeMathliveToApi(answerDraft).trim() : undefined;
      await exercisesApi.updateProblem(exerciseSetId, problem.id, {
        status,
        student_answer: studentAnswer || undefined,
      });
      await refreshProfile();
      onUpdated();
    } catch {
      setError(t("exercises.saveError"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevealAnswer() {
    setRevealLoading(true);
    setError(null);
    try {
      const { data } = await exercisesApi.getAnswer(exerciseSetId, problem.id);
      setRevealedAnswer(data.answer);
    } catch {
      setError(t("exercises.answerUnavailable"));
    } finally {
      setRevealLoading(false);
    }
  }

  return (
    <Card className={cn(isDone && "border-emerald-100 bg-emerald-50/30")}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-muted-foreground">
            {t("exercises.problemOf", { current: index + 1, total })}
          </span>
          <Badge variant="secondary" className="text-xs">
            {topicLabel(problem.topic)}
          </Badge>
          <Badge
            variant="outline"
            className={cn("text-xs", difficultyColor(problem.difficulty))}
          >
            {difficultyLabel(problem.difficulty)}
          </Badge>
          {problem.target_skill && (
            <Badge variant="outline" className="text-xs">
              {formatTag(problem.target_skill)}
            </Badge>
          )}
          {isDone && (
            <Badge
              variant="outline"
              className={cn(
                "text-xs",
                problem.status === "completed"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-gray-200 text-gray-600"
              )}
            >
              {problem.status === "completed" ? t("common.completed") : t("common.skipped")}
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="rounded-lg border bg-white p-4">
          <LatexRenderer className="text-base leading-relaxed">
            {problem.prompt}
          </LatexRenderer>
        </div>

        {problem.learning_intention && (
          <p className="flex items-start gap-2 text-sm text-muted-foreground">
            <BookOpen className="mt-0.5 h-4 w-4 shrink-0 text-violet-500" />
            <span>{problem.learning_intention}</span>
          </p>
        )}

        {!isDone ? (
          <>
            <div>
              <label className="mb-2 block text-sm font-medium">{t("exercises.yourWork")}</label>
              <MixedMathInputField
                value={answerDraft}
                onChange={setAnswerDraft}
                variant="chat"
                placeholder={t("exercises.workPlaceholder")}
                aria-label={t("exercises.answerAria", { num: index + 1 })}
                disabled={submitting}
              />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => void handleSubmit("completed")}
                disabled={submitting || !answerDraft.trim()}
                className="gap-2"
              >
                {submitting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                {t("exercises.submitAttempt")}
              </Button>
              <Button
                variant="outline"
                onClick={() => void handleSubmit("skipped")}
                disabled={submitting}
                className="gap-2"
              >
                <SkipForward className="h-4 w-4" />
                {t("exercises.skip")}
              </Button>
            </div>
          </>
        ) : (
          <div className="space-y-3">
            {problem.student_answer && (
              <div className="rounded-lg border bg-white p-3">
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  {t("exercises.yourAttempt")}
                </p>
                <LatexRenderer className="text-sm">{problem.student_answer}</LatexRenderer>
              </div>
            )}

            {revealedAnswer ? (
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
                <p className="mb-1 text-xs font-medium text-violet-700">
                  {t("exercises.officialSolution")}
                </p>
                <LatexRenderer className="text-sm">{revealedAnswer}</LatexRenderer>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => void handleRevealAnswer()}
                disabled={revealLoading}
              >
                {revealLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
                {t("exercises.showOfficial")}
              </Button>
            )}

            {error && <p className="text-sm text-red-600">{error}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
