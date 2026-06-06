/**
 * Problem Input page
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Send, Lightbulb, ChevronRight, RotateCcw,
  BookOpen, Calculator, Infinity, FlaskConical, MessageSquare,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import LatexRenderer from "@/components/ui/latex-renderer";
import MixedMathInputField from "@/components/ui/mixed-math-input-field";
import { analyzeApi, sessionsApi } from "@/lib/api";
import {
  deserializeApiToMathlive,
  effectiveContentLength,
  hasMathContent,
  serializeMathliveToApi,
} from "@/lib/math-problem";
import { cn, difficultyColor, difficultyLabel, topicLabel } from "@/lib/utils";

type PageMode = "tutor" | "analyze";

interface AnalyzeResult {
  topic: string;
  subtopic: string;
  difficulty: number;
  recommended_method: string;
  key_observation: string;
  suggested_methods: string[];
  confidence: number;
  opening_question_seed: string;
  degraded: boolean;
}

interface Example {
  topic: "limits" | "derivatives" | "integrals";
  key: string;
  problem: string;
}

const EXAMPLES: Example[] = [
  { topic: "limits",      key: "indeterminate", problem: "Evaluate \\( \\lim_{x \\to 0} \\frac{\\sin(3x)}{x} \\)" },
  { topic: "limits",      key: "lhopital",      problem: "Find \\( \\lim_{x \\to \\infty} \\frac{x^2}{e^x} \\)" },
  { topic: "limits",      key: "onesided",      problem: "Evaluate \\( \\lim_{x \\to 2^-} \\frac{x^2 - 4}{x - 2} \\)" },
  { topic: "derivatives", key: "chain",         problem: "Find \\( \\frac{d}{dx}\\left[e^{\\sin(x^2)}\\right] \\)" },
  { topic: "derivatives", key: "implicit",      problem: "Find \\( \\frac{dy}{dx} \\) given \\( x^2 + y^2 = 25 \\)" },
  { topic: "derivatives", key: "product",       problem: "Differentiate \\( f(x) = x^3 \\ln(x) \\)" },
  { topic: "integrals",   key: "usub",          problem: "Compute \\( \\int x \\cdot e^{x^2}\\,dx \\)" },
  { topic: "integrals",   key: "parts",         problem: "Evaluate \\( \\int x \\ln(x)\\,dx \\)" },
  { topic: "integrals",   key: "definite",      problem: "Compute \\( \\int_0^{\\pi} \\sin(x)\\,dx \\)" },
];

const TOPIC_META = {
  limits:      { icon: Infinity,   color: "text-blue-600",   bg: "bg-blue-50",   border: "border-blue-200"   },
  derivatives: { icon: Calculator, color: "text-violet-600", bg: "bg-violet-50", border: "border-violet-200" },
  integrals:   { icon: BookOpen,   color: "text-emerald-600",bg: "bg-emerald-50",border: "border-emerald-200" },
} as const;

const TOPICS = ["limits", "derivatives", "integrals"] as const;

const MIN_CHARS = 10;
const MAX_CHARS = 800;

export default function ProblemPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [mode, setMode] = useState<PageMode>("tutor");
  const [editorValue, setEditorValue] = useState("");
  const [activeTopic, setActiveTopic] = useState<typeof TOPICS[number] | "all">("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyzeResult, setAnalyzeResult] = useState<AnalyzeResult | null>(null);

  const problemText = useMemo(
    () => serializeMathliveToApi(editorValue),
    [editorValue]
  );

  const filtered =
    activeTopic === "all"
      ? EXAMPLES
      : EXAMPLES.filter((e) => e.topic === activeTopic);

  const trimmed = problemText.trim();
  const charCount = effectiveContentLength(trimmed);
  const isValid =
    hasMathContent(trimmed) &&
    charCount >= MIN_CHARS &&
    charCount <= MAX_CHARS;

  function loadExample(ex: Example) {
    setEditorValue(deserializeApiToMathlive(ex.problem));
    setError(null);
  }

  function clearForm() {
    setEditorValue("");
    setError(null);
    setAnalyzeResult(null);
  }

  async function handleStartTutoring() {
    if (!isValid || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await sessionsApi.create(trimmed);
      navigate(`/chat/${res.data.session_id}`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : t("problem.createError");
      setError(msg);
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!isValid || loading) return;
    setLoading(true);
    setError(null);
    setAnalyzeResult(null);
    try {
      const { data } = await analyzeApi.analyze(trimmed);
      setAnalyzeResult({
        ...data.analysis,
        opening_question_seed: data.opening_question_seed,
        degraded: data.degraded,
      });
    } catch {
      setError(t("problem.analyzeError"));
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (mode === "analyze") {
      await handleAnalyze();
    } else {
      await handleStartTutoring();
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-bold">{t("problem.title")}</h1>
        <p className="mt-1 text-gray-500">{t("problem.subtitle")}</p>
      </div>

      <div className="flex rounded-lg border border-gray-200 bg-gray-50 p-1 w-fit">
        <button
          type="button"
          onClick={() => { setMode("tutor"); setAnalyzeResult(null); }}
          className={cn(
            "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            mode === "tutor" ? "bg-white text-violet-700 shadow-sm" : "text-gray-500"
          )}
        >
          <MessageSquare className="h-4 w-4" />
          {t("problem.modeTutor")}
        </button>
        <button
          type="button"
          onClick={() => setMode("analyze")}
          className={cn(
            "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            mode === "analyze" ? "bg-white text-violet-700 shadow-sm" : "text-gray-500"
          )}
        >
          <FlaskConical className="h-4 w-4" />
          {t("problem.modeAnalyze")}
        </button>
      </div>

      {mode === "analyze" && (
        <p className="text-sm text-muted-foreground">{t("problem.analyzeDesc")}</p>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("problem.yourProblem")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="mixed-problem-input" className="text-xs font-medium text-gray-500">
              {t("problem.statement")}
            </label>
            <p className="text-xs text-gray-400">{t("problem.inputHint")}</p>
            <MixedMathInputField
              id="mixed-problem-input"
              value={editorValue}
              onChange={setEditorValue}
              variant="problem"
              aria-label={t("problem.inputAria")}
              placeholder={t("problem.placeholder")}
            />
          </div>

          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>
              {editorValue.trim() && !hasMathContent(trimmed) && (
                <span className="text-amber-500">{t("problem.needFormula")}</span>
              )}
              {hasMathContent(trimmed) && charCount < MIN_CHARS && (
                <span className="text-amber-500">
                  {t("problem.needMoreChars", { min: MIN_CHARS })}
                </span>
              )}
            </span>
            <span className={charCount > MAX_CHARS * 0.9 ? "text-amber-500" : ""}>
              {charCount} / {MAX_CHARS}
            </span>
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-600">
              {error}
            </p>
          )}

          <div className="flex items-center justify-between pt-1">
            <button
              type="button"
              onClick={clearForm}
              className="flex min-h-12 items-center gap-1.5 rounded-lg px-2 text-sm text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {t("common.clear")}
            </button>
            <Button
              onClick={() => void handleSubmit()}
              disabled={!isValid || loading}
              className="gap-2"
            >
              {loading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  {mode === "analyze" ? t("problem.analyzing") : t("problem.starting")}
                </>
              ) : mode === "analyze" ? (
                <>
                  <FlaskConical className="h-4 w-4" />
                  {t("problem.runAnalyze")}
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  {t("problem.startTutoring")}
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {analyzeResult && (
        <Card className="border-violet-200 bg-violet-50/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FlaskConical className="h-4 w-4 text-violet-600" />
              {t("problem.analyzeResult")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{topicLabel(analyzeResult.topic)}</Badge>
              <Badge variant="outline">{analyzeResult.subtopic.replace(/_/g, " ")}</Badge>
              <Badge className={cn("text-xs", difficultyColor(analyzeResult.difficulty))} variant="outline">
                {difficultyLabel(analyzeResult.difficulty)}
              </Badge>
              {analyzeResult.degraded && (
                <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                  {t("problem.degraded")}
                </Badge>
              )}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 text-sm">
              <div>
                <p className="text-xs font-medium text-muted-foreground">{t("problem.recommendedMethod")}</p>
                <p className="font-medium">{analyzeResult.recommended_method.replace(/_/g, " ")}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">{t("problem.confidence")}</p>
                <p className="font-medium">{Math.round(analyzeResult.confidence * 100)}%</p>
              </div>
            </div>
            {analyzeResult.key_observation && (
              <div>
                <p className="text-xs font-medium text-muted-foreground">{t("problem.keyObservation")}</p>
                <p className="text-sm">{analyzeResult.key_observation}</p>
              </div>
            )}
            {analyzeResult.suggested_methods.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">{t("problem.suggestedMethods")}</p>
                <div className="flex flex-wrap gap-1.5">
                  {analyzeResult.suggested_methods.map((m) => (
                    <Badge key={m} variant="outline" className="text-xs">
                      {m.replace(/_/g, " ")}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            <div className="rounded-lg border border-violet-200 bg-white p-4">
              <p className="text-xs font-medium text-violet-700 mb-1">{t("problem.openingQuestion")}</p>
              <p className="text-sm italic text-violet-900">{analyzeResult.opening_question_seed}</p>
            </div>
            <Button className="gap-2" onClick={() => void handleStartTutoring()} disabled={loading}>
              <Send className="h-4 w-4" />
              {t("problem.startFromAnalyze")}
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
        <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <div className="text-sm text-amber-800 space-y-0.5">
          <p className="font-medium">{t("problem.tipsTitle")}</p>
          <ul className="list-disc list-inside space-y-0.5 text-amber-700 text-xs">
            <li>{t("problem.tip1")}</li>
            <li>{t("problem.tip2")}</li>
            <li>{t("problem.tip3")}</li>
          </ul>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("problem.examplesTitle")}</h2>
          <div className="flex gap-2">
            <button
              type="button"
              aria-pressed={activeTopic === "all"}
              onClick={() => setActiveTopic("all")}
              className={cn(
                "min-h-12 rounded-full px-4 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
                activeTopic === "all"
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              )}
            >
              {t("common.all")}
            </button>
            {TOPICS.map((topic) => {
              const { color, bg, border } = TOPIC_META[topic];
              return (
                <button
                  key={topic}
                  type="button"
                  aria-pressed={activeTopic === topic}
                  onClick={() => setActiveTopic(topic)}
                  className={cn(
                    "min-h-12 rounded-full border px-4 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
                    activeTopic === topic
                      ? cn(bg, color, border)
                      : "bg-gray-100 border-transparent text-gray-600 hover:bg-gray-200"
                  )}
                >
                  {topicLabel(topic)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((ex) => {
            const { icon: Icon, color, bg, border } = TOPIC_META[ex.topic];
            const label = t(`problem.examples.${ex.key}.label`);
            const hint = t(`problem.examples.${ex.key}.hint`);
            return (
              <button
                key={ex.problem}
                type="button"
                onClick={() => loadExample(ex)}
                aria-label={t("problem.loadExample", { label })}
                className={cn(
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
                  "group rounded-xl border bg-white p-4 text-left transition-all",
                  "hover:shadow-md hover:-translate-y-0.5",
                  problemText === ex.problem
                    ? cn("ring-2 ring-violet-500", border)
                    : "border-gray-200 hover:border-gray-300"
                )}
              >
                <div className="mb-3 flex items-center justify-between">
                  <div className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", bg, color)}>
                    <Icon className="h-3 w-3" />
                    <span>{topicLabel(ex.topic)}</span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 text-gray-300 transition-transform group-hover:translate-x-0.5 group-hover:text-gray-500" />
                </div>

                <p className="mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {label}
                </p>

                <div className="text-sm font-medium text-gray-800 leading-relaxed">
                  <LatexRenderer>{ex.problem}</LatexRenderer>
                </div>

                <p className="mt-2 text-xs text-gray-400 italic">{hint}</p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
