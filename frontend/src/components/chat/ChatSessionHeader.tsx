import { memo } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  CheckCircle2,
  HelpCircle,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import LatexRenderer from "@/components/ui/latex-renderer";
import type { SessionDetail } from "@/lib/api";
import { cn, difficultyColor, difficultyLabel, topicLabel } from "@/lib/utils";

const LLM_LABELS = { gemini: "Gemini", deepseek: "DeepSeek" } as const;

interface Props {
  session: SessionDetail;
  milestoneLabel: string;
  llmProvider: keyof typeof LLM_LABELS;
  isCompleted: boolean;
  isStreaming: boolean;
  statusNote: string | null;
  sseError: string | null;
  onBack: () => void;
  onStuck: () => void;
  onComplete: () => void;
}

function ChatSessionHeader({
  session,
  milestoneLabel,
  llmProvider,
  isCompleted,
  isStreaming,
  statusNote,
  sseError,
  onBack,
  onStuck,
  onComplete,
}: Props) {
  const { t } = useTranslation();
  const analysis = session.analysis;
  const hintLevel = session.progress.hint_level;

  return (
    <header className="shrink-0 border-b border-gray-200 bg-white px-6 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5 text-gray-500"
              onClick={onBack}
            >
              <ArrowLeft className="h-4 w-4" />
              {t("nav.dashboard")}
            </Button>
            {isCompleted && (
              <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">
                {t("chat.completed")}
              </Badge>
            )}
          </div>
          <div className="text-sm font-medium leading-relaxed text-gray-800">
            <LatexRenderer>{session.problem_text}</LatexRenderer>
          </div>
          {analysis && (
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">{topicLabel(analysis.topic)}</Badge>
              <Badge variant="outline">{analysis.subtopic}</Badge>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  difficultyColor(analysis.difficulty)
                )}
              >
                {difficultyLabel(analysis.difficulty)}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1 border-violet-200 bg-violet-50 text-violet-700">
            <Sparkles className="h-3 w-3" />
            {LLM_LABELS[llmProvider]}
          </Badge>
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-center">
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-400">
              {t("chat.milestone")}
            </p>
            <p className="text-sm font-semibold text-gray-800">{milestoneLabel}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-center">
            <p className="text-[10px] font-medium uppercase tracking-wide text-gray-400">
              {t("chat.hintLevel")}
            </p>
            <p className="text-sm font-semibold text-gray-800">{hintLevel}/3</p>
          </div>
          {!isCompleted && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={isStreaming}
                onClick={onStuck}
              >
                <HelpCircle className="h-4 w-4" />
                {t("chat.stuck")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={onComplete}
              >
                <CheckCircle2 className="h-4 w-4" />
                {t("chat.finish")}
              </Button>
            </>
          )}
        </div>
      </div>

      {(statusNote || sseError) && (
        <p
          role={sseError ? "alert" : "status"}
          className={cn(
            "mt-3 rounded-lg px-3 py-2 text-xs",
            sseError
              ? "border border-red-200 bg-red-50 text-red-600"
              : "border border-violet-200 bg-violet-50 text-violet-700"
          )}
        >
          {sseError ?? statusNote}
        </p>
      )}
    </header>
  );
}

export default memo(ChatSessionHeader);
