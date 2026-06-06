/**
 * Tutor Chat — SSE streaming session with agent trace panel.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  MessageSquare,
  PenLine,
  Send,
  Sparkles,
  Square,
} from "lucide-react";

import AgentTracePanel from "@/components/chat/AgentTracePanel";
import ChatMessageBubble from "@/components/chat/ChatMessageBubble";
import ChatSessionHeader from "@/components/chat/ChatSessionHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import LatexRenderer from "@/components/ui/latex-renderer";
import MixedMathInputField from "@/components/ui/mixed-math-input-field";
import { Skeleton } from "@/components/ui/skeleton";
import { useSessionSSE, type TurnCompletePayload } from "@/hooks/useSessionSSE";
import { messagesApi, sessionsApi, type SessionDetail } from "@/lib/api";
import { refreshProfile } from "@/lib/profile";
import type { AgentTraceEntry } from "@/types/sse";
import { serializeMathliveToApi } from "@/lib/math-problem";
import { cn, topicLabel } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";

function formatMilestoneDisplay(
  session: SessionDetail,
  traceEntries: AgentTraceEntry[]
): string {
  const fromTrace = [...traceEntries].reverse().find((e) => e.milestone)?.milestone;
  if (fromTrace) return fromTrace;
  const total = session.session_summary?.milestones_total;
  const current = session.progress.current_milestone;
  if (total && total > 0) return `${current}/${total}`;
  return `${current}/3`;
}

export default function ChatPage() {
  const { t } = useTranslation();
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const llmProvider = useAuthStore((s) => s.profile?.preferences.llm_provider ?? "gemini");

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(true);
  const [editorValue, setEditorValue] = useState("");
  const [statusNote, setStatusNote] = useState<string | null>(null);

  const kickoffSent = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const refreshSession = useCallback(async () => {
    if (!sessionId) return;
    const { data } = await sessionsApi.get(sessionId);
    setSession(data);
  }, [sessionId]);

  const handleTurnComplete = useCallback(
    (payload: TurnCompletePayload) => {
      void refreshSession();
      void refreshProfile();
      const count = payload.exercises?.length ?? 0;
      if (count > 0) {
        setStatusNote(t("chat.sessionComplete", { count }));
      } else if (payload.solution_ready) {
        setStatusNote(t("chat.milestonesCompleteHint"));
      }
    },
    [refreshSession, t]
  );

  const {
    messages,
    traceEntries,
    isStreaming,
    sseError,
    sendMessage,
    sendStuck,
    hydrateMessages,
    clearTrace,
    abort,
  } = useSessionSSE(sessionId ?? null, handleTurnComplete);

  // Load session + message history
  useEffect(() => {
    if (!sessionId) {
      setLoadingSession(false);
      return;
    }

    let cancelled = false;
    kickoffSent.current = false;

    (async () => {
      setLoadingSession(true);
      setLoadError(null);
      try {
        const [sessionRes, messagesRes] = await Promise.all([
          sessionsApi.get(sessionId),
          messagesApi.list(sessionId),
        ]);
        if (cancelled) return;
        setSession(sessionRes.data);
        hydrateMessages(messagesRes.data);
      } catch {
        if (!cancelled) setLoadError(t("chat.loadError"));
      } finally {
        if (!cancelled) setLoadingSession(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, hydrateMessages]);

  // Auto-start tutoring on new sessions (intake phase, no messages yet)
  useEffect(() => {
    if (
      !sessionId ||
      loadingSession ||
      isStreaming ||
      kickoffSent.current ||
      !session ||
      session.phase !== "intake" ||
      messages.length > 0
    ) {
      return;
    }

    kickoffSent.current = true;
    void sendMessage(t("chat.kickoff"));
  }, [
    sessionId,
    loadingSession,
    isStreaming,
    session,
    messages.length,
    sendMessage,
  ]);

  // Scroll to latest message (respect prefers-reduced-motion)
  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    messagesEndRef.current?.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }, [messages, isStreaming]);

  async function handleSend() {
    const text = serializeMathliveToApi(editorValue).trim();
    if (!text || isStreaming || !sessionId) return;
    setEditorValue("");
    setStatusNote(null);
    await sendMessage(text);
    await refreshSession();
    await refreshProfile();
  }

  async function handleStuck() {
    if (!sessionId || isStreaming) return;
    setStatusNote(null);
    await sendStuck();
    await refreshSession();
    await refreshProfile();
  }

  async function handleComplete() {
    if (!sessionId) return;
    try {
      const { data } = await sessionsApi.complete(sessionId);
      await refreshSession();
      await refreshProfile();
      const count = data.exercises?.length ?? 0;
      setStatusNote(
        count > 0
          ? t("chat.sessionComplete", { count })
          : t("chat.sessionMarkedComplete")
      );
    } catch {
      setStatusNote(t("chat.completeError"));
    }
  }

  // ── No session selected ─────────────────────────────────────────
  if (!sessionId) {
    return <ChatSessionPicker />;
  }

  if (loadingSession) {
    return (
      <div className="flex h-[calc(100vh)] flex-col gap-4 bg-gray-50 p-8">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-24 w-full max-w-3xl" />
        <Skeleton className="flex-1 w-full" />
      </div>
    );
  }

  if (loadError || !session) {
    return (
      <div className="flex h-[calc(100vh)] flex-col items-center justify-center gap-4 bg-gray-50 p-8">
        <p className="text-muted-foreground">{loadError ?? t("chat.notFound")}</p>
        <Button variant="outline" onClick={() => navigate("/")}>
          {t("chat.backToDashboard")}
        </Button>
      </div>
    );
  }

  const isCompleted = session.status === "completed";
  const milestoneLabel = formatMilestoneDisplay(session, traceEntries);

  return (
    <div className="flex h-[calc(100vh)] flex-col overflow-hidden bg-gray-50">
      <ChatSessionHeader
        session={session}
        milestoneLabel={milestoneLabel}
        llmProvider={llmProvider}
        isCompleted={isCompleted}
        isStreaming={isStreaming}
        statusNote={statusNote}
        sseError={sseError}
        onBack={() => navigate("/")}
        onStuck={() => void handleStuck()}
        onComplete={() => void handleComplete()}
      />

      {/* ── Main: chat + trace ─────────────────────────────────── */}
      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col" aria-label={t("chat.chatAria")}>
          <div
            className="flex-1 overflow-y-auto px-6 py-6"
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label={t("chat.messageLog")}
          >
            <div className="mx-auto max-w-3xl space-y-6">
              {messages.length === 0 && !isStreaming && (
                <Card className="border-dashed">
                  <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
                    <Sparkles className="h-8 w-8 text-violet-400" />
                    <p className="text-sm font-medium text-gray-700">
                      {t("chat.starting")}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t("chat.startingDesc")}
                    </p>
                  </CardContent>
                </Card>
              )}

              {messages.map((msg) => (
                <ChatMessageBubble
                  key={msg.id}
                  message={msg}
                  isStreaming={
                    isStreaming &&
                    msg.role === "assistant" &&
                    msg.id === messages[messages.length - 1]?.id
                  }
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="shrink-0 border-t border-gray-200 bg-white px-6 py-4">
            <div className="mx-auto max-w-3xl space-y-2">
              <label htmlFor="chat-message-input" className="sr-only">
                {t("chat.inputLabel")}
              </label>
              <div className="flex gap-2">
                <MixedMathInputField
                  id="chat-message-input"
                  value={editorValue}
                  onChange={setEditorValue}
                  onSubmit={() => void handleSend()}
                  variant="chat"
                  disabled={isCompleted || isStreaming}
                  aria-label={t("chat.inputLabel")}
                  aria-describedby={isCompleted ? undefined : "chat-input-hint"}
                  placeholder={
                    isCompleted
                      ? t("chat.sessionCompleted")
                      : t("chat.placeholder")
                  }
                  className="flex-1"
                />
                {isStreaming ? (
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-12 w-12 shrink-0 self-start"
                    onClick={abort}
                    aria-label={t("chat.stopGeneration")}
                  >
                    <Square className="h-4 w-4" aria-hidden />
                  </Button>
                ) : (
                  <Button
                    className="h-12 shrink-0 gap-2 px-5 self-start"
                    disabled={!serializeMathliveToApi(editorValue).trim() || isCompleted}
                    onClick={() => void handleSend()}
                  >
                    <Send className="h-4 w-4" />
                    {t("common.send")}
                  </Button>
                )}
              </div>
              {!isCompleted && (
                <span id="chat-input-hint" className="sr-only">
                  {t("chat.inputHint")}
                </span>
              )}
            </div>
          </div>
        </section>

        <aside
          aria-label={t("chat.tracePanel")}
          className="hidden w-80 shrink-0 border-l border-gray-200 bg-zinc-950 p-3 lg:flex lg:flex-col"
        >
          <AgentTracePanel
            entries={traceEntries}
            isStreaming={isStreaming}
            onClear={clearTrace}
            className="min-h-0 flex-1"
          />
        </aside>
      </div>

      {/* Mobile trace drawer */}
      <div className="border-t border-gray-200 bg-zinc-950 p-3 lg:hidden">
        <AgentTracePanel
          entries={traceEntries}
          isStreaming={isStreaming}
          onClear={clearTrace}
          defaultCollapsed
          className="max-h-48"
        />
      </div>
    </div>
  );
}

function ChatSessionPicker() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<
    Awaited<ReturnType<typeof sessionsApi.list>>["data"]
  >([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    sessionsApi
      .list()
      .then((r) => setSessions(r.data.slice(0, 10)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-8">
      <div>
        <h1 className="text-2xl font-bold">{t("chat.title")}</h1>
        <p className="mt-1 text-muted-foreground">{t("chat.subtitle")}</p>
      </div>

      <Button className="w-full gap-2" onClick={() => navigate("/problem")}>
        <PenLine className="h-4 w-4" />
        {t("nav.newProblem")}
      </Button>

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-700">{t("chat.recentSessions")}</h2>
        {loading ? (
          <Skeleton className="h-20 w-full" />
        ) : sessions.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
              <MessageSquare className="h-8 w-8 text-gray-300" />
              <p className="text-sm text-muted-foreground">{t("chat.noSessions")}</p>
            </CardContent>
          </Card>
        ) : (
          sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => navigate(`/chat/${s.id}`)}
              aria-label={t("chat.continueSession", { text: s.problem_text })}
              className="w-full min-h-12 rounded-xl border border-gray-200 bg-white p-4 text-left transition-colors hover:border-violet-300 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
            >
              <p className="line-clamp-2 text-sm font-medium text-gray-800">
                <LatexRenderer>{s.problem_text}</LatexRenderer>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {s.topic ? topicLabel(s.topic) : t("common.calculus")} · {t("common.turns", { count: s.turn_count })}
                {s.status !== "active" && ` · ${t(`chat.status.${s.status}`)}`}
              </p>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
