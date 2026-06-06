import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { ExerciseSet } from "@/lib/api";
import { cn, difficultyColor, difficultyLabel, formatDateTime, topicLabel } from "@/lib/utils";

export interface ExerciseSetRowProps {
  set: ExerciseSet;
  onOpen: (id: string) => void;
  /** Show spaced-repetition due date (Exercises page). */
  showDueDate?: boolean;
  /** Show generation rationale as subtitle (Report page). */
  showRationale?: boolean;
  className?: string;
}

export default function ExerciseSetRow({
  set,
  onOpen,
  showDueDate = false,
  showRationale = false,
  className,
}: ExerciseSetRowProps) {
  const { t } = useTranslation();
  const pending = set.problems.filter((p) => p.status === "pending").length;
  const total = set.problems.length;
  const done = total - pending;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const isComplete = pending === 0;

  const subtitle = showRationale
    ? set.generation_meta.rationale || t("exercises.fromSession", { count: total })
    : showDueDate
      ? t("exercises.dueAt", {
          date: formatDateTime(set.spaced_repetition.due_at),
          count: total,
        })
      : t("dashboard.problemsDone", { done, total });

  return (
    <button
      type="button"
      onClick={() => onOpen(set.id)}
      aria-label={t("dashboard.exerciseSetAria", { done, total })}
      className={cn(
        "flex w-full min-h-14 items-start gap-3 rounded-lg border p-4 text-left transition-colors",
        "hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500",
        className
      )}
    >
      <div className="flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {set.problems[0]?.topic ? topicLabel(set.problems[0].topic) : t("common.calculus")}
          </Badge>
          {set.problems[0] && (
            <Badge
              variant="outline"
              className={cn("text-xs", difficultyColor(set.problems[0].difficulty))}
            >
              {difficultyLabel(set.problems[0].difficulty)}
            </Badge>
          )}
          {isComplete ? (
            <Badge
              variant="outline"
              className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs"
            >
              {t("common.completed")}
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-amber-200 bg-amber-50 text-amber-700 text-xs"
            >
              {showRationale
                ? t("report.dueBadge", { count: pending })
                : t("common.remaining", { count: pending })}
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground line-clamp-2">{subtitle}</p>
        <div className="flex items-center gap-3">
          <Progress
            value={pct}
            className="h-1.5 flex-1"
            aria-label={t("dashboard.progressAria", { pct })}
          />
          <span className="text-xs text-muted-foreground shrink-0">
            {done}/{total}
          </span>
        </div>
      </div>
      <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
    </button>
  );
}
