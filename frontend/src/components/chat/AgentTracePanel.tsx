/**
 * AgentTracePanel
 *
 * Displays a live stream of agent decisions for every SSE turn.
 * Each entry shows:
 *   - Agent Name     derived from SSE route field
 *   - Timestamp      wall-clock time the event was received
 *   - Action         short label (Step Evaluation, Socratic Response, …)
 *   - Reasoning      student_understanding from SocraticAssessment
 *
 * Secondary details (verdict, latency, leak risk, mastery delta,
 * milestone progress) are visible on entry expansion.
 *
 * Consumes AgentTraceEntry[] — produced by useSessionSSE hook.
 */
import {
  useEffect,
  useRef,
  useState,
  type FC,
} from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ClipboardList,
  Cpu,
  Eraser,
  FlaskConical,
  Radio,
  Sparkles,
  TriangleAlert,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentTraceEntry } from "@/types/sse";

// ── Agent metadata ────────────────────────────────────────────────

interface AgentMeta {
  icon: FC<{ className?: string }>;
  label: string;
  ring: string;
  badge: string;
  dot: string;
}

const AGENT_META: Record<string, AgentMeta> = {
  "Problem Analyzer": {
    icon: FlaskConical,
    label: "Problem Analyzer",
    ring:  "ring-violet-500/40",
    badge: "bg-violet-500/15 text-violet-300 border-violet-500/30",
    dot:   "bg-violet-400",
  },
  "Teaching Agent": {
    icon: Brain,
    label: "Teaching Agent",
    ring:  "ring-emerald-500/40",
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    dot:   "bg-emerald-400",
  },
  "Practice Agent": {
    icon: ClipboardList,
    label: "Practice Agent",
    ring:  "ring-rose-500/40",
    badge: "bg-rose-500/15 text-rose-300 border-rose-500/30",
    dot:   "bg-rose-400",
  },
  Orchestrator: {
    icon: Cpu,
    label: "Orchestrator",
    ring:  "ring-sky-500/40",
    badge: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    dot:   "bg-sky-400",
  },
};

const FALLBACK_META: AgentMeta = {
  icon: Sparkles,
  label: "Agent",
  ring:  "ring-zinc-500/40",
  badge: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  dot:   "bg-zinc-400",
};

function getAgentMeta(agentName: string): AgentMeta {
  return AGENT_META[agentName] ?? FALLBACK_META;
}

// ── Verdict badge ─────────────────────────────────────────────────

const VERDICT_STYLE: Record<string, string> = {
  correct:           "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  partially_correct: "bg-amber-500/15   text-amber-300   border-amber-500/30",
  incorrect:         "bg-red-500/15     text-red-300     border-red-500/30",
  unclear:           "bg-zinc-500/15    text-zinc-300    border-zinc-500/30",
};

// ── Helpers ───────────────────────────────────────────────────────

function formatTime(d: Date): string {
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function formatDelta(delta: Record<string, number>): string {
  return Object.entries(delta)
    .filter(([, v]) => v !== 0)
    .map(([k, v]) => `${v >= 0 ? "+" : ""}${v.toFixed(3)} ${k}`)
    .join("  ");
}

function truncate(text: string, max = 120): string {
  return text.length > max ? text.slice(0, max) + "…" : text;
}

// ── Single entry ──────────────────────────────────────────────────

interface EntryProps {
  entry: AgentTraceEntry;
  isLatest: boolean;
}

function TraceEntry({ entry, isLatest }: EntryProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const meta = getAgentMeta(entry.agentName);
  const Icon = meta.icon;

  const hasCritic = entry.route === "critic->teaching";
  const hasAssessment = !!entry.assessment;
  const canExpand = hasAssessment || !!entry.errorTag || !!entry.masteryDelta;

  return (
    <div
      className={cn(
        "rounded-lg border ring-1 ring-inset transition-all",
        "border-zinc-700/60 bg-zinc-900",
        meta.ring,
        isLatest && "border-zinc-600"
      )}
    >
      {/* ── Compact header ──────────────────────────────────────── */}
      <button
        type="button"
        onClick={() => canExpand && setExpanded((v) => !v)}
        aria-expanded={canExpand ? expanded : undefined}
        disabled={!canExpand}
        className={cn(
          "w-full rounded-lg px-3 py-2.5 text-left",
          canExpand
            ? "cursor-pointer hover:bg-zinc-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 focus-visible:ring-inset"
            : "cursor-default"
        )}
      >
        <div className="flex items-start gap-2.5">

          {/* Agent icon */}
          <div className={cn(
            "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded",
            meta.badge, "border"
          )}>
            <Icon className="h-3.5 w-3.5" />
          </div>

          {/* Main content */}
          <div className="min-w-0 flex-1 space-y-1">

            {/* Row 1: agent name · action · turn */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="text-xs font-semibold text-zinc-200">
                {entry.agentName}
              </span>

              {hasCritic && (
                <span className="text-xs text-zinc-500">
                  {t("trace.viaStudentModel")}
                </span>
              )}

              <span className={cn(
                "rounded border px-1.5 py-0.5 text-[10px] font-medium",
                meta.badge
              )}>
                {entry.action}
              </span>

              {entry.verdict && (
                <span className={cn(
                  "rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize",
                  VERDICT_STYLE[entry.verdict] ?? VERDICT_STYLE.unclear
                )}>
                  {entry.verdict.replace(/_/g, " ")}
                </span>
              )}

              {entry.degraded && (
                <span className="flex items-center gap-0.5 rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">
                  <TriangleAlert className="h-2.5 w-2.5" />
                  {t("trace.degraded")}
                </span>
              )}
            </div>

            {/* Row 2: reasoning summary */}
            <p className="text-xs leading-snug text-zinc-400">
              {truncate(entry.reasoningSummary)}
            </p>

            {/* Row 3: metrics row */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-zinc-500">
              <span>{formatTime(entry.timestamp)}</span>

              {entry.latencyMs > 0 && (
                <span className="flex items-center gap-0.5">
                  <Zap className="h-2.5 w-2.5" />
                  {formatMs(entry.latencyMs)}
                </span>
              )}

              {entry.milestone && (
                <span className="font-mono">
                  {t("trace.milestone")} {entry.milestone}
                  {entry.assessment?.milestone_complete && (
                    <span className="ml-0.5 text-emerald-400"> ✓</span>
                  )}
                </span>
              )}

              {entry.hintLevel > 0 && (
                <span>{t("trace.hintLevel", { level: entry.hintLevel })}</span>
              )}

              {entry.leakRisk != null && entry.leakRisk > 0 && (
                <span className={cn(
                  entry.leakRisk >= 0.3 ? "text-amber-400" : "text-zinc-500"
                )}>
                  {t("trace.leakRisk", { pct: (entry.leakRisk * 100).toFixed(0) })}
                </span>
              )}

              {entry.masteryDelta && (
                <span className="font-mono text-zinc-400">
                  {formatDelta(entry.masteryDelta)}
                </span>
              )}

              {entry.models.length > 0 && (
                <span className="truncate text-zinc-600">
                  {[...new Set(entry.models.map((m) => m.split("-")[1] ?? m))].join("+")}
                </span>
              )}
            </div>
          </div>

          {/* Expand chevron */}
          {canExpand && (
            <div className="mt-1 shrink-0 text-zinc-600">
              {expanded
                ? <ChevronUp className="h-3.5 w-3.5" />
                : <ChevronDown className="h-3.5 w-3.5" />}
            </div>
          )}
        </div>
      </button>

      {/* ── Expanded detail ──────────────────────────────────────── */}
      {expanded && (
        <div className="border-t border-zinc-700/50 px-3 pb-3 pt-2 space-y-3">

          {/* Error tag */}
          {entry.errorTag && (
            <Detail label={t("trace.errorTag")}>
              <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-[11px] text-amber-300">
                {entry.errorTag}
              </code>
            </Detail>
          )}

          {/* Full reasoning (assessment.student_understanding) */}
          {entry.assessment?.student_understanding && (
            <Detail label={t("trace.studentUnderstanding")}>
              <p className="text-xs leading-relaxed text-zinc-300">
                {entry.assessment.student_understanding}
              </p>
            </Detail>
          )}

          {/* Next question */}
          {entry.assessment?.next_question && (
            <Detail label={t("trace.nextQuestion")}>
              <p className="text-xs italic leading-relaxed text-zinc-300">
                "{entry.assessment.next_question}"
              </p>
            </Detail>
          )}

          {/* Confidence */}
          {entry.assessment?.confidence != null && (
            <Detail label={t("trace.assessmentConfidence")}>
              <ConfidenceBar value={entry.assessment.confidence} />
            </Detail>
          )}

          {/* Mastery delta */}
          {entry.masteryDelta && Object.keys(entry.masteryDelta).length > 0 && (
            <Detail label={t("trace.masteryDelta")}>
              <div className="flex flex-wrap gap-2">
                {Object.entries(entry.masteryDelta).map(([topic, delta]) => (
                  <span key={topic} className={cn(
                    "rounded border px-2 py-0.5 font-mono text-[11px]",
                    delta >= 0
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                      : "border-red-500/30 bg-red-500/10 text-red-300"
                  )}>
                    {topic}: {delta >= 0 ? "+" : ""}{delta.toFixed(4)}
                  </span>
                ))}
              </div>
            </Detail>
          )}

          {/* Route + models (raw) */}
          <Detail label={t("trace.route")}>
            <code className="text-[11px] text-zinc-400">
              {entry.route}
              {entry.models.length > 0 && (
                <span className="ml-2 text-zinc-600">
                  [{entry.models.join(", ")}]
                </span>
              )}
            </code>
          </Detail>
        </div>
      )}
    </div>
  );
}

// ── Small presentational sub-components ──────────────────────────

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        {label}
      </p>
      {children}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const color =
    pct >= 75 ? "bg-emerald-500" :
    pct >= 50 ? "bg-amber-500"   :
                "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-700">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-[11px] text-zinc-400">
        {pct}%
      </span>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────

interface AgentTracePanelProps {
  /** Entries produced by useSessionSSE */
  entries: AgentTraceEntry[];
  /** True while an SSE stream is open */
  isStreaming?: boolean;
  /** Callback to clear all entries */
  onClear?: () => void;
  /** Allow parent to control collapsed state */
  defaultCollapsed?: boolean;
  className?: string;
}

export default function AgentTracePanel({
  entries,
  isStreaming = false,
  onClear,
  defaultCollapsed = false,
  className,
}: AgentTracePanelProps) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when a new entry arrives
  useEffect(() => {
    if (!collapsed && entries.length > 0) {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      bottomRef.current?.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "end",
      });
    }
  }, [entries.length, collapsed]);

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-zinc-700/80 bg-zinc-950 shadow-lg",
        className
      )}
      role="region"
      aria-label={t("chat.tracePanel")}
    >

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <Radio className="h-3.5 w-3.5 text-zinc-400" />
          <span className="text-xs font-semibold text-zinc-300">
            {t("trace.title")}
          </span>

          {/* Live indicator */}
          {isStreaming && (
            <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              {t("trace.live")}
            </span>
          )}

          {/* Entry count */}
          {entries.length > 0 && !isStreaming && (
            <span className="rounded-full bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500">
              {entries.length}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {/* Clear */}
          {entries.length > 0 && onClear && (
            <button
              type="button"
              onClick={onClear}
              aria-label={t("trace.clear")}
              className="touch-target rounded-lg text-zinc-600 transition-colors hover:bg-zinc-800 hover:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
            >
              <Eraser className="h-3.5 w-3.5" aria-hidden />
            </button>
          )}

          {/* Collapse toggle */}
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            aria-expanded={!collapsed}
            aria-label={collapsed ? t("trace.expand") : t("trace.collapse")}
            className="touch-target rounded-lg text-zinc-600 transition-colors hover:bg-zinc-800 hover:text-zinc-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
          >
            {collapsed
              ? <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
          </button>
        </div>
      </div>

      {/* ── Body ────────────────────────────────────────────────── */}
      {!collapsed && (
        <div className="flex-1 overflow-y-auto overscroll-contain px-2 py-2">
          {entries.length === 0 ? (
            <EmptyState isStreaming={isStreaming} t={t} />
          ) : (
            <div className="space-y-1.5">
              {entries.map((entry, i) => (
                <TraceEntry
                  key={entry.id}
                  entry={entry}
                  isLatest={i === entries.length - 1}
                />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────

function EmptyState({
  isStreaming,
  t,
}: {
  isStreaming: boolean;
  t: (key: string) => string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
      <Cpu className="h-6 w-6 text-zinc-700" />
      <p className="text-xs text-zinc-600">
        {isStreaming ? t("trace.waiting") : t("trace.empty")}
      </p>
    </div>
  );
}
