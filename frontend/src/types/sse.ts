/**
 * SSE event types emitted by POST /sessions/{id}/messages
 * and POST /sessions/{id}/stuck.
 *
 * Every event has a "type" discriminant matching the SSE "event:" field.
 */

// ── Individual event payloads ─────────────────────────────────────

export interface AnalysisEvent {
  type: "analysis";
  topic: string;
  subtopic: string;
  difficulty: number;         // 1–5
  methods: string[];
  degraded: boolean;
}

export interface TokenEvent {
  type: "token";
  text: string;
}

export interface RetractEvent {
  type: "retract";
}

export interface AnalysisStartEvent {
  type: "analysis_start";
}

export interface PracticeStartEvent {
  type: "practice_start";
}

export interface DoneEvent {
  type: "done";
  session_id?: string;
  phase?: string;
  milestone?: number;
  hint_level?: number;
  solution_ready?: boolean;
  verdict?: string | null;
  error_tag?: string | null;
  milestone_advanced?: boolean;
  exercises?: Array<Record<string, unknown>>;
  rationale?: string | null;
  message_id?: string;
}

export interface ErrorEvent {
  type: "error";
  code: "safety" | "timeout" | "vertex" | "deepseek" | "unknown";
  detail: string;
}

export interface AgentTraceEvent {
  type: "agent_trace";
  turn: number;
  route: string;                        // e.g. "critic->teaching", "analyzer"
  models: string[];
  milestone: string | null;             // e.g. "2/3"
  hint_level: number;
  verdict: "correct" | "partially_correct" | "incorrect" | "unclear" | null;
  error_tag: string | null;
  mastery_delta: Record<string, number> | null;
  leak_risk: number | null;             // 0.0–1.0
  latency_ms: number;
  assessment?: {
    student_understanding: string;
    next_question: string;
    confidence: number;                 // 0–100
    milestone_complete: boolean;
    should_reveal_solution: boolean;
  };
}

// ── Union discriminated type ──────────────────────────────────────

export type SSEEvent =
  | AnalysisEvent
  | TokenEvent
  | RetractEvent
  | AnalysisStartEvent
  | PracticeStartEvent
  | DoneEvent
  | ErrorEvent
  | AgentTraceEvent;

// ── Derived trace entry (what AgentTracePanel displays) ───────────

export interface AgentTraceEntry {
  /** Unique client-side ID */
  id: string;
  /** Wall-clock time the event was received by the browser */
  timestamp: Date;
  /** Canonical agent name derived from route */
  agentName: string;
  /** Short action label derived from route + verdict */
  action: string;
  /** Primary reasoning summary shown in the panel */
  reasoningSummary: string;

  // ── Raw trace fields for expanded detail view ──────────────────
  turn: number;
  route: string;
  models: string[];
  milestone: string | null;
  hintLevel: number;
  verdict: AgentTraceEvent["verdict"];
  errorTag: string | null;
  masteryDelta: Record<string, number> | null;
  leakRisk: number | null;
  latencyMs: number;
  assessment: AgentTraceEvent["assessment"];

  /** "agent_trace" | "analysis" — for icon + color selection */
  eventKind: "agent_trace" | "analysis";
  /** Degraded mode flag (from analysis events) */
  degraded?: boolean;
}
