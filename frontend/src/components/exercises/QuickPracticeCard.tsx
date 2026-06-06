/**
 * On-demand single exercise (POST /exercises/single) — not persisted.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Eye, Loader2, RefreshCw, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import LatexRenderer from "@/components/ui/latex-renderer";
import MixedMathInputField from "@/components/ui/mixed-math-input-field";
import { exercisesApi, type SingleExercise } from "@/lib/api";
import { cn, difficultyColor, difficultyLabel, topicLabel } from "@/lib/utils";

export default function QuickPracticeCard() {
  const { t } = useTranslation();
  const [exercise, setExercise] = useState<SingleExercise | null>(null);
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    setSubmitted(false);
    setShowAnswer(false);
    setAttempt("");
    try {
      const { data } = await exercisesApi.single({ focus_weakness: true });
      setExercise(data);
    } catch {
      setError(t("exercises.generateError"));
      setExercise(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Sparkles className="h-5 w-5 text-violet-600" />
              {t("exercises.quickPractice")}
            </CardTitle>
            <CardDescription>{t("exercises.quickDesc")}</CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-2 shrink-0"
            onClick={() => void generate()}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            {exercise ? t("exercises.newProblem") : t("exercises.generate")}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!exercise && !loading && !error && (
          <p className="text-sm text-muted-foreground">{t("exercises.generateHint")}</p>
        )}

        {exercise && (
          <>
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" className="text-xs">
                {topicLabel(exercise.topic)}
              </Badge>
              <Badge
                variant="outline"
                className={cn("text-xs", difficultyColor(exercise.difficulty))}
              >
                {difficultyLabel(exercise.difficulty)}
              </Badge>
            </div>

            <div className="rounded-lg border bg-white p-4">
              <LatexRenderer className="text-base">{exercise.problem}</LatexRenderer>
            </div>

            {exercise.learning_intention && (
              <p className="text-sm text-muted-foreground">{exercise.learning_intention}</p>
            )}

            {!submitted ? (
              <>
                <MixedMathInputField
                  value={attempt}
                  onChange={setAttempt}
                  variant="chat"
                  placeholder={t("exercises.yourAttemptPlaceholder")}
                  aria-label={t("exercises.quickAnswerAria")}
                />
                <Button
                  onClick={() => setSubmitted(true)}
                  disabled={!attempt.trim()}
                >
                  {t("exercises.doneCheck")}
                </Button>
              </>
            ) : (
              <div className="space-y-3">
                <div className="rounded-lg border bg-white p-3">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">
                    {t("exercises.yourAttempt")}
                  </p>
                  <LatexRenderer className="text-sm">{attempt}</LatexRenderer>
                </div>
                {showAnswer ? (
                  <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
                    <p className="mb-1 text-xs font-medium text-violet-700">
                      {t("exercises.solution")}
                    </p>
                    <LatexRenderer className="text-sm">{exercise.answer}</LatexRenderer>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2"
                    onClick={() => setShowAnswer(true)}
                  >
                    <Eye className="h-4 w-4" />
                    {t("exercises.showSolution")}
                  </Button>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
