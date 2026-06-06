import axios from "axios";
import i18n from "@/i18n";
import { useAuthStore } from "@/store/auth";

const api = axios.create({ baseURL: "/api/v1" });

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  const lang = i18n.language === "zh" ? "zh" : "en";
  config.headers["Accept-Language"] = lang;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) useAuthStore.getState().logout();
    return Promise.reject(err);
  }
);

export default api;

// ── Typed API helpers ─────────────────────────────────────────────

export interface AuthResponse {
  access_token: string;
  token_type: string;
  student_id: string;
  display_name: string;
  email: string;
}

export const authApi = {
  google: (idToken: string) =>
    api.post<AuthResponse>("/auth/google", { id_token: idToken }),

  devLogin: () =>
    api.post<AuthResponse>("/auth/dev-login"),
};

export const meApi = {
  profile: () => api.get<StudentProfile>("/me"),
  updatePreferences: (data: Partial<StudentPreferences>) =>
    api.patch<StudentProfile>("/me/preferences", data),
  analytics: () => api.get<LearningAnalytics>("/me/analytics"),
  masteryHistory: (limit = 50) =>
    api.get<MasteryHistoryResponse>("/me/mastery/history", { params: { limit } }),
  llmProviders: () => api.get<{ providers: LlmProviderOption[] }>("/me/llm-providers"),
};

interface SessionResponseRaw {
  id: string;
  status: SessionSummary["status"];
  problem_text: string;
  analysis?: { topic: string; subtopic: string } | null;
  progress?: { turn_count: number };
  started_at: string;
  updated_at: string;
}

function toSessionSummary(s: SessionResponseRaw): SessionSummary {
  return {
    id: s.id,
    status: s.status,
    problem_text: s.problem_text,
    topic: s.analysis?.topic ?? null,
    subtopic: s.analysis?.subtopic ?? null,
    created_at: s.started_at,
    updated_at: s.updated_at,
    turn_count: s.progress?.turn_count ?? 0,
  };
}

export const sessionsApi = {
  list: () =>
    api
      .get<{ sessions: SessionResponseRaw[]; total: number }>("/sessions")
      .then((r) => ({
        ...r,
        data: (r.data.sessions ?? []).map(toSessionSummary),
      })),
  create: (problem: string) =>
    api.post<{ session_id: string }>("/sessions", { problem_text: problem }),
  get: (id: string) => api.get<SessionDetail>(`/sessions/${id}`),
  complete: (id: string) =>
    api.post<{
      status: string;
      exercises?: ExerciseProblem[];
      rationale?: string | null;
      summary?: Record<string, unknown> | null;
    }>(`/sessions/${id}/complete`),
};

export const analyzeApi = {
  analyze: (problem_text: string) =>
    api.post<{
      analysis: {
        topic: string;
        subtopic: string;
        difficulty: number;
        recommended_method: string;
        key_observation: string;
        suggested_methods: string[];
        confidence: number;
      };
      opening_question_seed: string;
      degraded: boolean;
    }>("/analyze", { problem_text }),
};

export interface StoredAgentTrace {
  route?: string;
  models?: string[];
  models_used?: string[];
  turn?: number;
  milestone?: string | null;
  hint_level?: number;
  verdict?: "correct" | "partially_correct" | "incorrect" | "unclear" | null;
  error_tag?: string | null;
  mastery_delta?: Record<string, number> | null;
  latency_ms?: number;
  leak_risk?: number | null;
  assessment?: {
    student_understanding?: string;
    next_question?: string;
    confidence?: number;
    milestone_complete?: boolean;
    should_reveal_solution?: boolean;
  };
  analysis?: {
    topic: string;
    subtopic: string;
    difficulty: number;
    methods?: string[];
    degraded?: boolean;
  };
}

export interface ChatMessageRecord {
  id: string;
  role: "student" | "assistant" | "system";
  content: string;
  turn_index: number;
  agent_trace?: StoredAgentTrace | null;
  metadata?: { milestone_id?: number; hint_level?: number; phase?: string } | null;
  created_at: string;
}

export const messagesApi = {
  list: (sessionId: string) =>
    api.get<ChatMessageRecord[]>(`/sessions/${sessionId}/messages`),
};

export const exercisesApi = {
  get: (id: string) => api.get<ExerciseSet>(`/exercises/${id}`),
  pending: () => api.get<ExerciseSet[]>("/exercises"),
  due: () => api.get<ExerciseSet[]>("/exercises/due"),
  all: () => api.get<ExerciseSet[]>("/exercises/all"),
  single: (body: { topic?: string; focus_weakness?: boolean }) =>
    api.post<SingleExercise>("/exercises/single", body),
  updateProblem: (
    exerciseId: string,
    problemId: string,
    data: { status: "completed" | "skipped"; student_answer?: string }
  ) => api.patch(`/exercises/${exerciseId}/problems/${problemId}`, data),
  getAnswer: (exerciseId: string, problemId: string) =>
    api.get<{ problem_id: string; answer: string }>(
      `/exercises/${exerciseId}/problems/${problemId}/answer`
    ),
};

// ── Shared types ──────────────────────────────────────────────────

export interface TopicMastery {
  score: number;
  attempts: number;
  last_practiced: string | null;
}

export interface MasterySnapshot {
  limits: TopicMastery;
  derivatives: TopicMastery;
  integrals: TopicMastery;
}

export interface ErrorPattern {
  tag: string;
  count: number;
  last_seen: string;
}

export interface StudentStats {
  total_sessions: number;
  total_steps_submitted: number;
  total_exercises_done: number;
  streak_days: number;
  last_active_at: string | null;
}

export type LlmProvider = "gemini" | "deepseek";

export interface LlmProviderOption {
  id: LlmProvider;
  label: string;
  available: boolean;
}

export interface StudentPreferences {
  hint_style: "gentle" | "balanced" | "challenging";
  latex_enabled: boolean;
  notify_exercises: boolean;
  llm_provider: LlmProvider;
  locale: "en" | "zh";
}

export interface StudentProfile {
  id: string;
  display_name: string;
  email: string;
  avatar_url: string | null;
  preferences: StudentPreferences;
  mastery: MasterySnapshot;
  error_patterns: ErrorPattern[];
  stats: StudentStats;
}

export interface ErrorFrequency {
  tag: string;
  count: number;
  severity: "low" | "medium" | "high";
}

export interface LearningAnalytics {
  strengths: string[];
  weaknesses: string[];
  mastery_scores: Record<string, number>;
  recommended_next_topic: string;
  recommended_subtopic: string;
  error_summary: ErrorFrequency[];
  learning_tip: string;
  confidence: number;
  deterministic_only: boolean;
  computed_at: string;
}

export interface MasteryHistoryPoint {
  score_after: number;
  delta: number;
  event_type: string;
  subtopic: string | null;
  created_at: string;
}

export interface MasteryHistoryResponse {
  limits: MasteryHistoryPoint[];
  derivatives: MasteryHistoryPoint[];
  integrals: MasteryHistoryPoint[];
}

export interface SessionSummary {
  id: string;
  status: "active" | "completed" | "abandoned";
  problem_text: string;
  topic: string | null;
  subtopic: string | null;
  created_at: string;
  updated_at: string;
  turn_count: number;
}

/** Raw session payload from GET /sessions/:id */
export interface SessionDetail {
  id: string;
  status: string;
  phase: string;
  problem_text: string;
  analysis: {
    topic: string;
    subtopic: string;
    difficulty: number;
    recommended_method: string;
  } | null;
  progress: {
    current_milestone: number;
    hint_level: number;
    solution_ready: boolean;
    turn_count: number;
    message_count?: number;
  };
  session_summary?: {
    milestones_completed: number;
    milestones_total: number;
  } | null;
  started_at: string;
  updated_at: string;
}

export interface ExerciseProblem {
  id: string;
  prompt: string;
  topic: string;
  subtopic: string;
  difficulty: number;
  target_skill: string;
  learning_intention: string;
  status: "pending" | "attempted" | "completed" | "skipped";
  student_answer: string | null;
  completed_at: string | null;
}

export interface ExerciseSet {
  id: string;
  status: string;
  problems: ExerciseProblem[];
  generation_meta: { rationale: string; source: string };
  spaced_repetition: { due_at: string; interval_hours: number };
  created_at: string;
}

export interface SingleExercise {
  problem: string;
  difficulty: number;
  topic: string;
  subtopic: string;
  target_skill: string;
  learning_intention: string;
  answer: string;
}
