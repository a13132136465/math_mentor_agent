/**
 * useSessionSSE — manages the full SSE lifecycle for a tutoring session.
 *
 * Sends a student message via POST (SSE response), parses the stream,
 * and exposes:
 *   messages       — chat history (student + assistant)
 *   traceEntries   — AgentTraceEntry[] for AgentTracePanel
 *   isStreaming    — true while the stream is open
 *   streamingText  — partial assistant text being received
 *   sendMessage    — trigger a new SSE turn
 *   clearTrace     — wipe trace entries
 *
 * SSE is received over fetch + ReadableStream (not EventSource)
 * because the API uses POST, not GET.
 */
import { useCallback, useRef, useState } from "react";
import type { ChatMessageRecord, StoredAgentTrace } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type {
  AgentTraceEntry,
  AgentTraceEvent,
  AnalysisEvent,
  SSEEvent,
} from "@/types/sse";

// ── Types ─────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  role: "student" | "assistant" | "system";
  content: string;
  timestamp: Date;
  verdict?: AgentTraceEvent["verdict"];
  errorTag?: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────

/** Parse raw SSE stream bytes into discrete SSEEvent objects. */
async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const block of parts) {
      const lines = block.split("\n");
      let eventType = "";
      let dataStr = "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataStr = line.slice(5).trim();
        }
      }

      if (!dataStr) continue;

      try {
        const parsed = JSON.parse(dataStr) as Record<string, unknown>;
        // Attach the event type as discriminant
        const event = { ...parsed, type: eventType || parsed.type } as SSEEvent;
        yield event;
      } catch {
        // Malformed JSON — skip
      }
    }
  }
}

let _entryCounter = 0;
const nextId = () => `trace-${++_entryCounter}-${Date.now()}`;

/** Derive display fields from an agent_trace or analysis SSE event. */
function buildTraceEntry(
  event: AgentTraceEvent | AnalysisEvent,
  now: Date
): AgentTraceEntry {
  if (event.type === "analysis") {
    return {
      id: nextId(),
      timestamp: now,
      agentName: "Problem Analyzer",
      action: "Topic Classification",
      reasoningSummary: event.degraded
        ? `Degraded mode — classified as ${event.topic} (low confidence)`
        : `Identified ${event.topic} › ${event.subtopic} · difficulty ${event.difficulty}/5`,
      turn: 0,
      route: "analyzer",
      models: [],
      milestone: null,
      hintLevel: 0,
      verdict: null,
      errorTag: null,
      masteryDelta: null,
      leakRisk: null,
      latencyMs: 0,
      assessment: undefined,
      eventKind: "analysis",
      degraded: event.degraded,
    };
  }

  const trace = normalizeAgentTrace(event);

  // agent_trace event
  const route = trace.route ?? "";
  const agentName = routeToAgentName(route);
  const action = routeToAction(route, trace.verdict);
  const reasoningSummary =
    trace.assessment?.student_understanding ||
    verdictToSummary(trace.verdict, trace.error_tag, route);

  return {
    id: nextId(),
    timestamp: now,
    agentName,
    action,
    reasoningSummary,
    turn: trace.turn ?? 0,
    route,
    models: trace.models ?? [],
    milestone: trace.milestone ?? null,
    hintLevel: trace.hint_level ?? 0,
    verdict: trace.verdict ?? null,
    errorTag: trace.error_tag ?? null,
    masteryDelta: trace.mastery_delta ?? null,
    leakRisk: trace.leak_risk ?? null,
    latencyMs: trace.latency_ms ?? 0,
    assessment: trace.assessment,
    eventKind: "agent_trace",
  };
}

/** Backend may send assessment fields flat on agent_trace (post-done). */
function normalizeAgentTrace(event: AgentTraceEvent): AgentTraceEvent {
  const raw = event as AgentTraceEvent & Record<string, unknown>;
  if (raw.assessment) return raw;

  const understanding = raw.student_understanding as string | undefined;
  const nextQuestion = raw.next_question as string | undefined;
  if (!understanding && !nextQuestion && !raw.verdict) {
    return { ...raw, turn: raw.turn ?? 0, models: raw.models ?? [] };
  }

  return {
    ...raw,
    turn: raw.turn ?? 0,
    models: raw.models ?? [],
    error_tag: raw.error_tag ?? null,
    assessment: {
      student_understanding: understanding ?? "",
      next_question: nextQuestion ?? "",
      confidence: Number(raw.confidence ?? 0),
      milestone_complete: Boolean(raw.milestone_complete),
      should_reveal_solution: false,
    },
  };
}

function routeToAgentName(route: string): string {
  const map: Record<string, string> = {
    analyzer:          "Problem Analyzer",
    teaching:          "Teaching Agent",
    "critic->teaching": "Teaching Agent",
    practice:          "Practice Agent",
    noop:              "Orchestrator",
  };
  return map[route] ?? "Orchestrator";
}

function routeToAction(route: string, verdict: AgentTraceEvent["verdict"]): string {
  if (route === "analyzer")          return "Problem Classification";
  if (route === "practice")          return "Exercise Generation";
  if (route === "noop")              return "No Action";
  if (route === "critic->teaching")  return verdict ? "Step Evaluation" : "Socratic Response";
  if (route === "teaching")          return verdict ? "Step Evaluation" : "Socratic Response";
  return "Agent Response";
}

function verdictToSummary(
  verdict: AgentTraceEvent["verdict"],
  errorTag: string | null,
  route: string
): string {
  if (!verdict) return `Route: ${route}`;
  const base = verdict.replace(/_/g, " ");
  return errorTag ? `${base} — ${errorTag.replace(/_/g, " ")}` : base;
}

/** Rebuild trace panel entries from persisted assistant message traces. */
function buildTraceEntriesFromHistory(
  records: ChatMessageRecord[]
): AgentTraceEntry[] {
  const entries: AgentTraceEntry[] = [];

  for (const record of records) {
    if (record.role !== "assistant" || !record.agent_trace) continue;

    const trace = record.agent_trace;
    const timestamp = new Date(record.created_at);

    if (trace.analysis) {
      entries.push(
        buildTraceEntry(
          {
            type: "analysis",
            topic: trace.analysis.topic,
            subtopic: trace.analysis.subtopic,
            difficulty: trace.analysis.difficulty,
            methods: trace.analysis.methods ?? [],
            degraded: trace.analysis.degraded ?? false,
          },
          timestamp
        )
      );
    }

    if (trace.route) {
      entries.push(
        buildTraceEntry(storedTraceToEvent(trace, record), timestamp)
      );
    }
  }

  return entries;
}

function storedTraceToEvent(
  trace: StoredAgentTrace,
  record: ChatMessageRecord
): AgentTraceEvent {
  const models = trace.models ?? trace.models_used ?? [];
  const assessment = trace.assessment
    ? {
        student_understanding: trace.assessment.student_understanding ?? "",
        next_question: trace.assessment.next_question ?? "",
        confidence: trace.assessment.confidence ?? 0,
        milestone_complete: trace.assessment.milestone_complete ?? false,
        should_reveal_solution: trace.assessment.should_reveal_solution ?? false,
      }
    : undefined;

  return {
    type: "agent_trace",
    turn: trace.turn ?? record.turn_index,
    route: trace.route ?? "",
    models,
    milestone: trace.milestone ?? null,
    hint_level: trace.hint_level ?? record.metadata?.hint_level ?? 0,
    verdict: trace.verdict ?? null,
    error_tag: trace.error_tag ?? null,
    mastery_delta: trace.mastery_delta ?? null,
    leak_risk: trace.leak_risk ?? null,
    latency_ms: trace.latency_ms ?? 0,
    assessment,
    ...(assessment
      ? {
          student_understanding: assessment.student_understanding,
          next_question: assessment.next_question,
          confidence: assessment.confidence,
          milestone_complete: assessment.milestone_complete,
        }
      : {}),
  };
}

/** User-visible message when the tutor LLM call fails. */
export function formatLlmError(code: string, detail: string): string {
  const labels: Record<string, string> = {
    timeout: "模型调用超时",
    safety: "内容被安全策略拦截",
    vertex: "Gemini 服务异常",
    deepseek: "DeepSeek 服务异常",
    unknown: "模型调用失败",
  };
  const label = labels[code] ?? labels.unknown;
  return `⚠️ ${label}：${detail}`;
}

// ── Hook ──────────────────────────────────────────────────────────

export interface TurnCompletePayload {
  solution_ready?: boolean;
  exercises?: Array<Record<string, unknown>>;
  rationale?: string | null;
  phase?: string;
  milestone?: number;
  hint_level?: number;
}

export function useSessionSSE(
  sessionId: string | null,
  onTurnComplete?: (payload: TurnCompletePayload) => void
) {
  const token = useAuthStore((s) => s.token);
  const onTurnCompleteRef = useRef(onTurnComplete);
  onTurnCompleteRef.current = onTurnComplete;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [traceEntries, setTraceEntries] = useState<AgentTraceEntry[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [sseError, setSseError] = useState<string | null>(null);

  // Ref to accumulate streaming text without stale closure issues
  const streamBuf = useRef("");
  const abortRef = useRef<AbortController | null>(null);

  const runSseTurn = useCallback(
    async (
      url: string,
      options: {
        studentContent: string;
        body?: Record<string, unknown>;
        clientMessageId?: string;
      }
    ) => {
      if (!sessionId || isStreaming) return;

      const msgId = options.clientMessageId ?? crypto.randomUUID();

      const studentMsg: ChatMessage = {
        id: msgId,
        role: "student",
        content: options.studentContent,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, studentMsg]);
      setSseError(null);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsStreaming(true);
      streamBuf.current = "";
      setStreamingText("");

      const assistantId = crypto.randomUUID();
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantPlaceholder]);

      let streamFailed = false;
      try {
        const res = await fetch(url, {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(
            options.body ?? { content: options.studentContent, client_message_id: msgId }
          ),
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const reader = res.body.getReader();

        for await (const event of parseSSEStream(reader)) {
          const now = new Date();

          switch (event.type) {
            case "token": {
              streamBuf.current += event.text;
              const current = streamBuf.current;
              setStreamingText(current);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: current } : m
                )
              );
              break;
            }

            case "retract": {
              // Clear the streaming buffer — a corrected response is coming
              streamBuf.current = "";
              setStreamingText("");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: "" } : m
                )
              );
              break;
            }

            case "done": {
              if (!streamFailed) {
                const finalContent = streamBuf.current;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: finalContent } : m
                  )
                );
                onTurnCompleteRef.current?.({
                  solution_ready: Boolean(
                    (event as { solution_ready?: boolean }).solution_ready
                  ),
                  exercises: (event as { exercises?: Array<Record<string, unknown>> })
                    .exercises,
                  rationale: (event as { rationale?: string | null }).rationale,
                  phase: (event as { phase?: string }).phase,
                  milestone: (event as { milestone?: number }).milestone,
                  hint_level: (event as { hint_level?: number }).hint_level,
                });
              }
              setStreamingText("");
              break;
            }

            case "agent_trace": {
              const trace = normalizeAgentTrace(event);
              const entry = buildTraceEntry(trace, now);
              if (trace.verdict) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          verdict: trace.verdict,
                          errorTag: trace.error_tag,
                        }
                      : m
                  )
                );
              }
              setTraceEntries((prev) => [...prev, entry]);
              break;
            }

            case "analysis": {
              const entry = buildTraceEntry(event, now);
              setTraceEntries((prev) => [...prev, entry]);
              break;
            }

            case "error": {
              const errMsg = formatLlmError(event.code, event.detail);
              streamFailed = true;
              setSseError(errMsg);
              streamBuf.current = "";
              setStreamingText("");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, role: "system", content: errMsg }
                    : m
                )
              );
              break;
            }

            default:
              break;
          }

          if (streamFailed) break;
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          const errMsg = formatLlmError("unknown", err.message ?? "Stream error");
          streamFailed = true;
          setSseError(errMsg);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, role: "system", content: errMsg }
                : m
            )
          );
        }
      } finally {
        setIsStreaming(false);
        setStreamingText("");
        streamBuf.current = "";
        setMessages((prev) =>
          prev.filter(
            (m) =>
              m.role === "system" ||
              m.role === "student" ||
              (m.role === "assistant" && m.content.trim().length > 0)
          )
        );
      }
    },
    [sessionId, isStreaming, token]
  );

  const sendMessage = useCallback(
    async (content: string, clientMessageId?: string) => {
      if (!sessionId) return;
      await runSseTurn(`/api/v1/sessions/${sessionId}/messages`, {
        studentContent: content,
        clientMessageId,
      });
    },
    [sessionId, runSseTurn]
  );

  const sendStuck = useCallback(async () => {
    if (!sessionId) return;
    await runSseTurn(`/api/v1/sessions/${sessionId}/stuck`, {
      studentContent: "I'm stuck — can I get a hint?",
      body: {},
    });
  }, [sessionId, runSseTurn]);

  const hydrateMessages = useCallback((records: ChatMessageRecord[]) => {
    setMessages(
      records
        .filter((m) => m.content.trim().length > 0)
        .map((m) => ({
          id: m.id,
          role: m.role as ChatMessage["role"],
          content: m.content,
          timestamp: new Date(m.created_at),
          verdict: m.agent_trace?.verdict ?? undefined,
          errorTag: m.agent_trace?.error_tag ?? undefined,
        }))
    );
    setTraceEntries(buildTraceEntriesFromHistory(records));
  }, []);

  const clearTrace = useCallback(() => setTraceEntries([]), []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setStreamingText("");
    streamBuf.current = "";
  }, []);

  return {
    messages,
    traceEntries,
    isStreaming,
    streamingText,
    sseError,
    sendMessage,
    sendStuck,
    hydrateMessages,
    clearTrace,
    abort,
  };
}
