import { useTranslation } from "react-i18next";
import { cn, formatPct, masteryColor, masteryLabel, topicLabel } from "@/lib/utils";

interface TopicProgressProps {
  topic: string;
  score: number;
  attempts?: number;
  className?: string;
}

export default function TopicProgress({
  topic,
  score,
  attempts,
  className,
}: TopicProgressProps) {
  const { t } = useTranslation();
  const pct = Math.round(score * 100);
  const barColor =
    score >= 0.7 ? "bg-emerald-500" :
    score >= 0.4 ? "bg-amber-500"   : "bg-red-400";
  const topicName = topicLabel(topic);

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{topicName}</span>
        <div className="flex items-center gap-2">
          {attempts !== undefined && (
            <span className="text-xs text-muted-foreground">
              {t("common.attempts", { count: attempts })}
            </span>
          )}
          <span className={cn("font-semibold", masteryColor(score))}>
            {formatPct(score)} · {masteryLabel(score)}
          </span>
        </div>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("mastery.ariaLabel", { topic: topicName, pct })}
        className="relative h-2.5 w-full overflow-hidden rounded-full bg-gray-100"
      >
        <div
          className={cn("h-full transition-all", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
