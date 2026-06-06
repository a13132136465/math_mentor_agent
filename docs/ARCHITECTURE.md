# MathMentor — Canonical Architecture
### Single source of truth · Google Cloud Rapid Agent Hackathon

> **Stack:** Python 3.12 · FastAPI · Vertex AI (Gemini 2.5) · MongoDB Atlas · Cloud Run · React · Vite

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [Agent Architecture](#4-agent-architecture)
5. [Shared Contracts](#5-shared-contracts)
6. [Database Design](#6-database-design)
7. [API Design](#7-api-design)
8. [Folder Structure](#8-folder-structure)
9. [Development Roadmap](#9-development-roadmap)

---

## 1. Product Overview

### 1.1 Vision

MathMentor is an AI Socratic tutor for university Calculus (I–II). It guides students to discover solutions themselves through structured questioning — it never provides answers directly. Each interaction demonstrates the four hackathon pillars in a tangible, auditable way.

| Attribute | Definition |
|-----------|------------|
| **What it is** | Guided discovery: analyze → plan → coach → remember → personalize |
| **What it is not** | A step-by-step answer engine, Wolfram clone, or homework solver |
| **Scope (MVP)** | Limits, derivatives, integrals (Calculus I–II) |
| **Out of scope** | Multivariable, differential equations, OCR from photos |

### 1.2 Hackathon Pillar Mapping

| Pillar | Owner Agent(s) | Evidence |
|--------|----------------|---------|
| **Reasoning** | Problem Analyzer, Teaching Agent | Structured `AnalysisResult` + two-phase `SocraticAssessment` |
| **Planning** | Problem Analyzer | `ReasoningPlan` milestone graph drives session pacing |
| **Memory** | Student Model Agent | Mastery EMA, error pattern persistence, session continuity |
| **Multi-agent collaboration** | All agents via Orchestrator | Typed artifacts passed through the routing graph, visible in SSE `agent_trace` event |

### 1.3 User Stories (Prioritized)

| ID | Story | Priority |
|----|-------|----------|
| US-01 | Student pastes a problem and receives topic/method identification without the final answer | P0 |
| US-02 | Student gets one guiding question per turn until they show their work | P0 |
| US-03 | Student submits an intermediate step and receives targeted feedback | P0 |
| US-07 | Student can flag "I'm stuck" to get a stronger scaffold (never the full solution) | P0 |
| US-04 | Student sees mastery by topic (limits / derivatives / integrals) over time | P1 |
| US-05 | Student receives 2–3 personalized practice problems after a session | P1 |
| US-06 | Student can resume a prior session on the same problem | P1 |

### 1.4 Non-Functional Requirements

| Category | Target (MVP) |
|----------|--------------|
| **Latency** | First SSE token < 4s P95 on tutoring turns |
| **Answer leakage** | < 5% on 50 golden evaluation problems |
| **Scale** | 100 concurrent sessions (hackathon demo) |
| **Security** | Google OAuth → API JWT; secrets in Secret Manager |
| **Cost** | Gemini Flash for routing/hints/critique; Pro for analysis/planning/exercises |
| **Observability** | Cloud Logging + Trace; per-agent spans; SSE `agent_trace` event |

---

## 2. Technology Stack

| Layer | Choice | Version |
|-------|--------|---------|
| Runtime | Python | 3.12+ |
| API framework | FastAPI + uvicorn | 0.115+ |
| Data validation | Pydantic v2 | 2.7+ |
| MongoDB driver | motor (async) | 3.4+ |
| Vertex AI SDK | google-cloud-aiplatform | 1.58+ |
| LLM — reasoning/planning | `gemini-2.5-pro-preview-05-06` | via Vertex AI |
| LLM — tutoring/routing/critique | `gemini-2.5-flash-preview-05-20` | via Vertex AI |
| Orchestration | Custom Python FSM (`SessionContext` state machine) | — |
| Frontend | React + Vite | React 19 · Vite 8 |
| Routing | React Router | 7.x |
| Styling | Tailwind CSS + shadcn/ui | — |
| Math rendering | KaTeX + MathLive | — |
| i18n | react-i18next | en / zh |
| Deployment | Cloud Run (2 services) | — |
| Database | MongoDB Atlas | M10+ |
| Auth | Google OAuth 2.0 → HS256 JWT | 7-day expiry |
| Logging | structlog → Cloud Logging | — |

> **Frontend stack:** React SPA (Vite build, React Router, zustand). Deployed as static assets behind nginx on Cloud Run; `/api` is proxied to `mathmentor-api`. Earlier architecture drafts referenced Next.js App Router — that stack was **not** adopted.

> **No LangGraph.** Orchestration uses a custom typed FSM. The `SessionContext` Pydantic model is the shared state; the `OrchestratorAgent` drives all phase transitions.

---

## 3. System Architecture

### 3.1 High-Level Diagram

```
┌─────────────────────────────────────────────────────┐
│                    CLIENT LAYER                     │
│         React 19 · Vite · React Router (SPA)        │
│   Auth · Chat UI · LaTeX render · Mastery dashboard │
└────────────────────────┬────────────────────────────┘
                         │ HTTPS / SSE
┌────────────────────────▼────────────────────────────┐
│                  GOOGLE CLOUD                       │
│                                                     │
│  Cloud Run (mathmentor-web)   Cloud Run (mathmentor-api)
│  nginx static SPA + /api proxy  FastAPI + uvicorn     │
│                               ├── OrchestratorAgent │
│                               ├── AnalyzerAgent     │
│                               ├── TeachingAgent     │
│                               ├── StudentModelAgent │
│                               ├── PracticeAgent     │
│                               └── AnalyticsAgent    │
│                                                     │
│  Secret Manager (MONGODB_URI, JWT_SECRET)           │
│  Cloud Logging / Cloud Trace                        │
└──────────┬────────────────────────┬─────────────────┘
           │                        │
┌──────────▼──────────┐  ┌──────────▼──────────────────┐
│     Vertex AI       │  │      MongoDB Atlas           │
│  Gemini 2.5 Pro     │  │  students · sessions         │
│  Gemini 2.5 Flash   │  │  messages · mastery_events   │
└─────────────────────┘  │  exercises · problem_library │
                         └─────────────────────────────-┘
```

### 3.2 Request Flow — Tutoring Turn

```
Student submits message
  └── POST /v1/sessions/{id}/messages  (SSE)
        │
        ├── Load SessionContext from MongoDB
        │
        ├── OrchestratorAgent.handle_turn()
        │     │
        │     ├── _fast_route()          [deterministic, no LLM]
        │     │    or
        │     ├── _llm_route()           [Gemini Flash, JSON]
        │     │
        │     ├── "analyzer" → AnalyzerAgent.run()
        │     │     ├── Phase 1: classify (Gemini Pro)
        │     │     ├── Phase 2: plan    (Gemini Pro)
        │     │     └── Phase 2.5: seed  (Gemini Flash)
        │     │                          then → TeachingAgent.run()
        │     │
        │     └── "teaching" → StudentModelAgent.evaluate_step()  [if step submission]
        │                       + StudentModelAgent.apply_mastery_update()
        │                       + TeachingAgent.run()
        │                             ├── Phase 1: SocraticAssessment (Gemini Flash)
        │                             ├── Phase 2: compose + stream (Gemini Flash)
        │                             └── leak_check()  (Gemini Flash)
        │
        ├── Persist: session progress, message, mastery_event
        └── SSE events: analysis · token · agent_trace · done
```

### 3.3 Deployment

| Service | Image | Config |
|---------|-------|--------|
| `mathmentor-api` | FastAPI + uvicorn | 1 GiB RAM, 2 vCPU, min_instances=1, timeout=300s |
| `mathmentor-web` | Vite build → nginx (static SPA, `/api` reverse proxy) | 512 MiB RAM, 1 vCPU, min_instances=1 |
| **CI/CD** | Cloud Build → Artifact Registry → Cloud Run deploy | Trigger: `main` branch |

---

## 4. Agent Architecture

### 4.1 Agent Roster

The system has **five core agents** in the per-turn routing loop, and one **supporting agent** invoked independently for the analytics dashboard.

| Agent | Model | Role in loop | Hackathon pillar |
|-------|-------|-------------|-----------------|
| **Orchestrator** | Flash | Routes every turn; enforces phase machine + answer embargo | Collaboration |
| **Problem Analyzer** | Pro (×2) + Flash | Classifies problem, builds reasoning plan, generates opening seed | Reasoning + Planning |
| **Teaching Agent** | Flash (×2–4) | Socratic questioning, hint escalation, SSE streaming | Reasoning |
| **Student Model Agent** | Flash (Critic) + Python | Step validation, mastery EMA update, error pattern tracking | Memory |
| **Practice Agent** | Pro | Post-session exercise generation, spaced repetition scheduling | Memory + Planning |
| **Analytics Agent** *(supporting)* | Flash | Dashboard: mastery insights, learning tips, next-topic recommendation | Memory |

### 4.2 Routing State Machine

```
                   ┌─────────┐
                   │  INTAKE │ ◄── Session created
                   └────┬────┘
                        │ new_problem received
                        ▼
                 ┌──────────────┐
                 │  ANALYZING   │ ◄── AnalyzerAgent running
                 └──────┬───────┘
                        │ AnalyzerOutput received
                        ▼
                 ┌──────────────┐
          ┌─────►│   TUTORING   │◄─────────────────────┐
          │      └──────┬───────┘                       │
          │             │ student submits step           │
          │      ┌──────▼───────┐                       │
          │      │ StudentModel │ evaluate + mastery     │
          │      └──────┬───────┘                       │
          │             │ verdict                        │
          │      ┌──────▼───────┐  milestone ✓           │
          │      │   Teaching   │ ──────────────────────-┘
          │      └──────┬───────┘
          │             │ all milestones complete OR solution_ready
          │             ▼
          │      ┌──────────────┐
          │      │   WRAP_UP    │ ◄── PracticeAgent runs
          │      └──────┬───────┘
          │             │ PracticeOutput received
          │             ▼
          └──────┌──────────────┐
                 │  COMPLETED   │ (terminal)
                 └──────────────┘

  Any phase ──stuck──► hint_level = min(hint_level + 1, 3)
  hint_level = 3  ────► TeachingAgent near-example mode
```

**Fast routing (deterministic, no LLM):**

```python
def _fast_route(ctx: SessionContext, message: str) -> str | None:
    if ctx.session_ended:              return "noop"
    if ctx.is_new_problem and
       ctx.phase == "intake":          return "analyzer"
    if ctx.phase == "wrap_up":         return "practice"
    lower = message.lower()
    if any(w in lower for w in
       ("stuck", "help", "hint",
        "don't know", "confused")):    return "teaching"  # stuck_requested=True
    return None  # fall through to LLM route
```

**Turn decision table:**

| Condition | Route | LLM calls this turn |
|-----------|-------|---------------------|
| New session, phase=intake | analyzer → teaching | Pro×2 + Flash×3–4 |
| Student submits work step | teaching (with critic) | Flash×1 (critic) + Flash×2–3 (teach) |
| Student says "stuck" | teaching (hint_level++) | Flash×2–3 |
| Student asks clarification | teaching | Flash×2–3 |
| All milestones done / session end | practice | Pro×1 |

### 4.3 Agent 1 — Orchestrator

**Class:** `OrchestratorAgent`  
**Model:** Gemini 2.5 Flash (routing only)  
**File:** `backend/app/agents/orchestrator.py`

**Responsibilities:**
- Classify turn type via `_fast_route()` first (deterministic), `_llm_route()` as fallback
- Dispatch to sub-agents in correct order
- Enforce **answer embargo**: strip `ReasoningPlan` from Teaching Agent input
- Apply hint escalation on `stuck_requested`
- Run Critic inline when a step submission is detected (`_looks_like_step()`)
- Circuit breaker: after 3 consecutive failures, return graceful degradation message

**Routing LLM output schema:**
```json
{
  "message_type": "new_problem | step_submission | stuck_signal | clarification | off_topic",
  "route": "analyzer | teaching | practice | noop",
  "phase_transition": "tutoring | wrap_up | null",
  "hint_level": 0,
  "milestone_index": 2,
  "reason": "one sentence"
}
```

**Failure handling:**
- LLM parse error → retry once → fallback to `route="teaching"`, preserve current state
- Phase inconsistency → log + reset to `tutoring`
- Vertex timeout → `fast_route` defaults
- 3+ consecutive failures → circuit breaker message, session paused

---

### 4.4 Agent 2 — Problem Analyzer

**Class:** `AnalyzerAgent`  
**Model:** Gemini 2.5 Pro (Phase 1 + Phase 2), Flash (Phase 2.5)  
**File:** `backend/app/agents/analyzer.py`  
**Invocation:** Once per new problem (phase = `intake` → `analyzing`)

**Three-phase pipeline:**

**Phase 1 — Classification (Gemini Pro, JSON)**

Input: `problem_text` + student mastery scores + error patterns  
Output: `AnalysisResult`

```json
{
  "topic": "derivatives",
  "subtopic": "chain_rule",
  "difficulty": 3,
  "recommended_method": "chain_rule",
  "key_observation": "The problem is a composition of ln and sin",
  "suggested_methods": ["chain_rule", "logarithmic_differentiation"],
  "prerequisites": ["derivative_of_ln", "derivative_of_sin"],
  "confidence": 0.95,
  "ambiguity_note": null
}
```

> `difficulty` is an integer 1–5. Labels: 1=trivial, 2=easy, 3=medium, 4=hard, 5=very hard.

**Phase 2 — Planning (Gemini Pro, JSON)**

Input: `problem_text` + `AnalysisResult` (including `key_observation`)  
Output: `ReasoningPlan` — **server-only, never sent to client**

```json
{
  "milestones": [
    {"id": 1, "goal": "Identify ln(u) as outer and sin(x) as inner function", "skills_required": ["function_decomposition"], "completed": false},
    {"id": 2, "goal": "Apply chain rule: multiply (1/u) by the derivative of sin(x)", "skills_required": ["chain_rule", "derivative_of_trig"], "completed": false},
    {"id": 3, "goal": "Simplify to reach the simplified form", "skills_required": ["trig_identities", "algebra"], "completed": false}
  ],
  "common_pitfalls": ["Forgetting to multiply by the inner derivative"],
  "estimated_turns": 6
}
```

**Phase 2.5 — Opening Seed (Gemini Flash)**

Produces one short Socratic question (≤20 words) that directs the student's attention without hinting at the method. Passed immediately to Teaching Agent as `opening_question_seed`.

**Fallback behavior:**
- Phase 1 timeout/failure → `degraded=True`, generic plan for inferred topic, `confidence=0.3`
- Phase 2 failure → `_generic_milestones(topic)` (3 hardcoded milestones per topic)
- Phase 2.5 failure → `"What do you notice about the structure of this problem?"`

---

### 4.5 Agent 3 — Teaching Agent

**Class:** `TeachingAgent`  
**Model:** Gemini 2.5 Flash  
**File:** `backend/app/agents/teaching.py`  
**Invocation:** Every tutoring turn (after Analyzer on intake; every subsequent student message)

**Two-phase architecture:**

**Phase 1 — `SocraticAssessment` (Flash, JSON — not shown to student)**

Enforces Socratic discipline before generating any text. Output:

```python
class SocraticAssessment(BaseModel):
    student_understanding: str   # internal diagnosis
    next_question: str           # the question to ask
    hint: str                    # hint text if hint_level >= 2
    confidence: int              # 0–100, Teaching Agent's confidence in assessment
    should_reveal_solution: bool # true ONLY if hint_level >= 3 AND failed_attempts >= 3
    milestone_complete: bool     # true if this step satisfies current milestone
```

**Phase 2 — Natural Language Reply (Flash, streaming)**

Composes a warm, concise student-facing message from the `SocraticAssessment`. Streams tokens to `asyncio.Queue` for real-time SSE delivery.

**Leak check (Flash, post-Phase 2):**

```python
# Risk thresholds
LEAK_RISK_REWRITE  = 0.30   # Re-prompt with [STRICT MODE] prefix
LEAK_RISK_OVERRIDE = 0.70   # Discard; use canned scaffold by hint_level
MAX_REWRITES       = 2
```

**Answer embargo guarantee:** The Teaching Agent never receives the `ReasoningPlan` in its input. The Orchestrator strips it before building `TeachingInput`. The plan's `key_observation` and milestone goals are injected only as pedagogical guidance — never as solution steps.

**Hint level behavior:**

| `hint_level` | Teaching behavior |
|---|---|
| 0 | Open Socratic question — "What do you notice about...?" |
| 1 | Narrow question — refers to a specific rule by name without applying it |
| 2 | Analogy or recall prompt — "Recall how we handle sin(u)·u'..." |
| 3 | Near-example mode — works a structurally identical problem (different numbers/letters), then asks student to try original |

**Failure handling:**
- Phase 1 failure → `_fallback_assessment()` (safe defaults, no LLM)
- Leak risk > 0.70 → `_canned_response(hint_level, assessment)` (template, no LLM)
- Leak risk > 0.30 → re-prompt with `[STRICT MODE]` prefix, max 2 retries
- Response has no `?` → append `assessment.next_question`

---

### 4.6 Agent 4 — Student Model Agent

**Class:** `StudentModelAgent`  
**Model:** Gemini 2.5 Flash (Critic only); mastery updates are deterministic Python  
**File:** `backend/app/agents/student_model.py`  
**Invocation:** Every step submission turn (Critic); every turn's mastery update

**Responsibilities:**
- **Critic sub-task:** Evaluate whether the student's step is valid for the current milestone
- **Mastery EMA update:** Deterministic — no LLM
- **Error pattern tracking:** Accumulate error tags; surface persistent gaps
- **Profile write-back:** Persist updated mastery + error patterns to `students` collection (async, non-blocking)
- **Mastery event logging:** Append each verdict to `mastery_events` collection

**Critic output schema (Flash, JSON):**
```json
{
  "verdict": "correct | partially_correct | incorrect | unclear",
  "error_tag": "missing_chain_rule_factor | arithmetic_error | sign_error | ...",
  "correct_parts": "Student correctly identified the outer function derivative",
  "reasoning": "Omitted multiplication by inner derivative cos(x)"
}
```

**Mastery EMA (deterministic Python):**
```python
ALPHA = 0.15

verdict_delta  = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0, "unclear": 0.3}
hint_penalty   = {0: 1.0, 1: 0.85, 2: 0.65, 3: 0.4}

raw = verdict_delta[verdict] * hint_penalty[hint_level]
new_score = round(current + ALPHA * (raw - current), 4)   # clamped to [0.0, 1.0]
```

**Error tag taxonomy:**
```
wrong_derivative_rule · missing_chain_rule_factor · arithmetic_error
wrong_integral_bounds · forgot_constant_of_integration · limit_form_error
incorrect_factoring · sign_error · wrong_trig_identity · conceptual_gap
notation_error
```

**Failure handling:**
- Critic parse failure → default `"unclear"`, no mastery change
- MongoDB write failure → retry × 3 with exponential backoff, log warning
- Mastery out of bounds → clamp to [0.0, 1.0], log anomaly

---

### 4.7 Agent 5 — Practice Agent

**Class:** `PracticeAgent`  
**Model:** Gemini 2.5 Pro  
**File:** `backend/app/agents/practice.py`  
**Invocation:** Once at session end (phase = `wrap_up`)

**Responsibilities:**
- Read session error tags and mastery deltas to identify top 2 weak subtopics
- Generate 3 calibrated exercises targeting those subtopics
- Enforce diversity (no near-duplicate of session problem or last 10 exercises)
- Set `due_at` based on mastery score (spaced repetition scheduling)
- Persist to `exercises` collection

**Exercise output schema (Pro, JSON):**
```json
{
  "exercises": [
    {
      "id": "ex-1",
      "prompt": "Find \\( \\frac{d}{dx}[\\cos(x^2)] \\)",
      "topic": "derivatives",
      "subtopic": "chain_rule",
      "difficulty": "medium",
      "target_skill": "missing_chain_rule_factor",
      "learning_intention": "Practice identifying and multiplying by the inner derivative"
    }
  ],
  "rationale": "Targeting chain_rule gap observed 3 times this session"
}
```

**Spaced repetition scheduling:**
```python
mastery < 0.4  → due in 4 hours
mastery < 0.6  → due in 24 hours
mastery < 0.8  → due in 72 hours
mastery ≥ 0.8  → due in 168 hours (1 week)
```

**Fallback chain:**
1. Generation succeeds → return exercises
2. Generation yields < 3 → re-prompt with `avoid_patterns` list, max 3 attempts
3. Gemini Pro timeout → query `problem_library` filtered by weak subtopic + difficulty
4. `problem_library` empty → return 1 generic consolidation exercise

---

### 4.8 Analytics Agent (Supporting)

**Class:** `AnalyticsAgent`  
**Model:** Gemini 2.5 Flash (enrichment only); base layer is deterministic Python  
**File:** `backend/app/agents/analytics.py`  
**Invocation:** On-demand — called by `GET /me` and the mastery dashboard endpoint

**Not part of the per-turn routing loop.** Operates independently as a stateless reporting agent.

**Two-layer architecture:**

Layer 1 (deterministic, always succeeds):
- Compute strengths (score ≥ 0.70), weaknesses (score < 0.40 OR error tag ≥ 3 occurrences)
- Select recommended next topic by prerequisite order × mastery score
- Assign error severity labels (high/medium/low)

Layer 2 (Flash LLM enrichment, best-effort):
- Fills `recommended_subtopic` and `learning_tip`
- Falls back gracefully to deterministic-only output on any failure

**Output:** `LearningAnalyticsOutput` — consumed by the mastery dashboard UI.

---

## 5. Shared Contracts

All inter-agent communication uses typed Pydantic v2 models. Agents never pass raw LLM strings downstream — outputs are parsed before being handed to the next agent.

### 5.1 `SessionContext` (Central State)

```python
class MasteryTopic(BaseModel):
    score: float = 0.5           # EMA score [0.0, 1.0]
    attempts: int = 0
    last_practiced: datetime | None = None

class MasterySnapshot(BaseModel):
    limits:      MasteryTopic = MasteryTopic()
    derivatives: MasteryTopic = MasteryTopic()
    integrals:   MasteryTopic = MasteryTopic()

    def get_score(self, topic: str) -> float:
        return getattr(self, topic).score

class ErrorPattern(BaseModel):           # stored in students collection
    tag: str
    count: int
    last_seen: datetime

class SessionContext(BaseModel):
    session_id:   str
    student_id:   str
    problem_text: str
    phase:        Literal["intake","analyzing","tutoring","wrap_up","completed"] = "intake"

    analysis:             AnalysisResult | None = None
    plan:                 ReasoningPlan  | None = None   # NEVER sent to client
    current_milestone:    int = 0
    current_milestone_obj: Milestone | None = None

    hint_level:      int = 0
    solution_ready:  bool = False
    turn_count:      int = 0
    is_new_problem:  bool = True
    stuck_requested: bool = False
    session_ended:   bool = False

    mastery:        MasterySnapshot = MasterySnapshot()
    error_patterns: list[str] = []     # tag strings only — full ErrorPattern objects in DB
    student_steps:  list[dict] = []    # {milestone_id, content, verdict, error_tag}
    recent_messages: list[dict] = []   # last 6 messages: {role, content}
```

### 5.2 Key Output Types

```python
class AnalyzerOutput(BaseModel):
    analysis:              AnalysisResult
    plan:                  ReasoningPlan
    opening_question_seed: str
    degraded:              bool = False

class OrchestratorDecision(BaseModel):
    route:              Literal["analyzer", "teaching", "practice", "noop"]
    message_type:       Literal["new_problem","step_submission","stuck_signal","clarification","off_topic"]
    reason:             str
    updated_phase:      str
    updated_hint_level: int
    updated_milestone:  int

class TeachingOutput(BaseModel):
    assessment:       SocraticAssessment   # internal, forwarded to SSE agent_trace
    response_text:    str                  # streamed to student
    milestone_advanced: bool
    answer_leak_risk: float                # 0.0–1.0

class CriticVerdict(BaseModel):
    verdict:       Literal["correct","partially_correct","incorrect","unclear"]
    error_tag:     str | None
    correct_parts: str | None
    reasoning:     str

class PracticeOutput(BaseModel):
    exercises: list[dict]
    rationale: str
    source:    Literal["generated", "problem_library", "fallback"]
```

---

## 6. Database Design

### 6.1 Collections (MVP)

| Collection | Purpose | Write pattern | Retention |
|------------|---------|---------------|-----------|
| `students` | Identity, preferences, aggregate mastery, error patterns | Upsert on mastery update | Indefinite |
| `sessions` | Session metadata, embedded analysis + plan, progress | Create + frequent updates | Indefinite |
| `messages` | Full chat history (student + assistant + system) | Insert-only per turn | 90 days (TTL) |
| `mastery_events` | Append-only learning signal ledger | Insert-only per step | Indefinite |
| `exercises` | Generated practice sets + completion state | Insert on session end; update on progress | 6 months |
| `problem_library` | Curated seed problems for demo + fallback | Admin writes only | Indefinite |

> **Not in MVP:** `attempts` (verdict data is in `messages.metadata`) and `agent_memory` (turn traces go to Cloud Logging; profile memory is embedded in `students`).

### 6.2 Key Schemas

#### `students`
```javascript
{
  _id: ObjectId,
  auth_sub: "google-oauth2|...",    // unique index
  email: "student@university.edu",
  display_name: "Alex",
  preferences: {
    hint_style: "balanced",          // gentle | balanced | challenging
    latex_enabled: true
  },
  mastery: {
    limits:      { score: 0.65, attempts: 12, last_practiced: ISODate },
    derivatives: { score: 0.42, attempts: 8,  last_practiced: ISODate },
    integrals:   { score: 0.30, attempts: 5,  last_practiced: ISODate }
  },
  error_patterns: [
    { tag: "missing_chain_rule_factor", count: 5, last_seen: ISODate }
  ],
  stats: {
    total_sessions: 14, total_steps_submitted: 87,
    total_exercises_done: 22, streak_days: 3, last_active_at: ISODate
  },
  created_at: ISODate,
  updated_at: ISODate
}
```
Indexes: `{ auth_sub: 1 }` unique · `{ email: 1 }` unique sparse

#### `sessions`
```javascript
{
  _id: ObjectId,
  student_id: ObjectId,
  status: "active",                  // active | completed | abandoned | paused
  phase: "tutoring",                 // intake | analyzing | tutoring | wrap_up | completed
  problem_text: "Find d/dx[ln(sin x)]...",
  analysis: { /* AnalysisResult — safe for client */ },
  plan: { /* ReasoningPlan — server-only, never serialized to client API */ },
  progress: {
    current_milestone: 1, hint_level: 1,
    solution_ready: false, turn_count: 5, stuck_count: 1
  },
  session_summary: null,             // populated on completion
  flags: { degraded_mode: false, circuit_breaker: false },
  started_at: ISODate,
  ended_at: null,
  updated_at: ISODate
}
```
Indexes: `{ student_id: 1, started_at: -1 }` · `{ status: 1, started_at: -1 }`

#### `messages`
```javascript
{
  _id: ObjectId,
  session_id: ObjectId,
  student_id: ObjectId,
  client_message_id: "uuid",         // unique per session — idempotency key
  role: "student",                   // student | assistant | system
  content: "Let u = sin x",
  turn_index: 3,
  agent_trace: {                     // assistant messages only
    route: "critic->teaching",
    models_used: ["gemini-2.5-flash"],
    latency_ms: 1240,
    leak_risk: 0.03
  },
  metadata: {                        // populated on step_submission assistant messages
    milestone_id: 1,
    verdict: "partially_correct",
    error_tag: "missing_chain_rule_factor",
    mastery_delta: { derivatives: -0.004 }
  },
  created_at: ISODate
}
```
Indexes: `{ session_id: 1, created_at: 1 }` · `{ session_id: 1, client_message_id: 1 }` unique sparse · TTL `created_at` 90d

#### `mastery_events`
```javascript
{
  _id: ObjectId,
  student_id: ObjectId,
  session_id: ObjectId,
  topic: "derivatives",
  subtopic: "chain_rule",
  event_type: "step_partially_correct",
  delta: -0.004,
  score_after: 0.476,
  context: { milestone_id: 2, hint_level: 0, error_tag: "missing_chain_rule_factor" },
  created_at: ISODate
}
```
Indexes: `{ student_id: 1, topic: 1, created_at: -1 }` · `{ session_id: 1 }`

#### `exercises`
```javascript
{
  _id: ObjectId,
  student_id: ObjectId,
  session_id: ObjectId,
  status: "pending",                 // pending | in_progress | completed | expired
  generation_meta: { model_used, rationale, weak_subtopics, source },
  problems: [
    {
      id: "ex-1", prompt: "...", topic: "derivatives", subtopic: "chain_rule",
      difficulty: "medium", target_skill: "missing_chain_rule_factor",
      learning_intention: "Practice identifying and multiplying by inner derivative",
      status: "pending", student_answer: null, completed_at: null
    }
  ],
  due_at: ISODate,                   // spaced repetition trigger
  created_at: ISODate,
  expires_at: ISODate                // 6 months TTL
}
```
Indexes: `{ student_id: 1, status: 1, due_at: 1 }` · `{ session_id: 1 }`

### 6.3 Mastery Scoring

- Score ∈ [0.0, 1.0], EMA with α = 0.15
- `hint_penalty` reduces credit for hints: level 0 = full credit, level 3 = 40% credit
- `error_patterns` in `students`: persist only tags seen ≥ 3 times; cap at 50 entries (`$slice: -50`)
- Analytics Agent reads `mastery` + `error_patterns` from student document — no aggregation needed for the dashboard hot path

### 6.4 Connection Pooling
```python
AsyncIOMotorClient(
    MONGODB_URI,
    maxPoolSize=50,
    minPoolSize=5,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=3000,
    socketTimeoutMS=10000,
)
```

---

## 7. API Design

### 7.1 Conventions

- Base URL: `https://api.mathmentor.example/v1`
- Auth: `Authorization: Bearer <JWT>` (Google OAuth → JWT exchange)
- All JSON bodies; errors: RFC 7807 `{ "type", "title", "detail", "status" }`
- Streaming: SSE (`text/event-stream`) on message send and stuck endpoints

### 7.2 Endpoints

#### Auth & Profile

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/google` | Exchange Google ID token for API JWT |
| `GET` | `/me` | Current student profile + mastery + analytics summary |
| `PATCH` | `/me/preferences` | Update hint style |
| `GET` | `/me/mastery/history` | Mastery timeline per topic (for dashboard chart) |

#### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create session with `{ "problem_text": "..." }` |
| `GET` | `/sessions` | List sessions (`?status=active&limit=20`) |
| `GET` | `/sessions/{session_id}` | Session detail + phase (plan stripped) |
| `GET` | `/sessions/{session_id}/messages` | Full chat history for session (chat replay on reload) |
| `POST` | `/sessions/{session_id}/messages` | Send student message → SSE stream |
| `POST` | `/sessions/{session_id}/stuck` | Escalate hint level → SSE stream (same format as /messages) |
| `POST` | `/sessions/{session_id}/complete` | End session → triggers PracticeAgent |

#### Analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyze` | Standalone Analyzer output (demo only) — returns `AnalysisResult`, plan stripped |

#### Exercises

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/exercises` | All pending exercises for student |
| `GET` | `/exercises/due` | Exercises where `due_at <= now` (spaced repetition queue) |
| `GET` | `/exercises/{exercise_set_id}` | Detail |
| `PATCH` | `/exercises/{exercise_set_id}/problems/{id}` | Mark completed / skipped |

#### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | MongoDB + Vertex AI connectivity check |

### 7.3 SSE Event Format

All streaming endpoints (`/messages`, `/stuck`) emit the same event stream:

```
event: analysis
data: {"topic":"derivatives","subtopic":"chain_rule","difficulty":3,"methods":["chain_rule"],"degraded":false}

event: token
data: {"text":"Good "}

event: token
data: {"text":"observation"}

event: agent_trace
data: {
  "turn": 3,
  "route": "critic->teaching",
  "models": ["gemini-2.5-flash","gemini-2.5-flash"],
  "milestone": "2/3",
  "hint_level": 1,
  "verdict": "partially_correct",
  "error_tag": "missing_chain_rule_factor",
  "mastery_delta": {"derivatives": -0.004},
  "leak_risk": 0.03,
  "latency_ms": 1480
}

event: done
data: {"message_id":"...","milestone":1,"hint_level":0}
```

> The `agent_trace` event is the demo's most important feature. It makes all four hackathon pillars visible in the UI without requiring code inspection.

### 7.4 Rate Limits (MVP)

| Scope | Limit |
|-------|-------|
| Messages per session per hour | 60 |
| New sessions per day per student | 20 |
| `/analyze` | 10/min |

> **Rate limiting (MVP):** Implemented as an in-process sliding window (`RateLimitMiddleware`). Accurate per-student limits require a single API instance or an external store (Redis) when Cloud Run scales beyond one replica.

### 7.5 Example: Session Create + First Message

```http
POST /v1/sessions
Content-Type: application/json
Authorization: Bearer <jwt>

{ "problem_text": "Find the derivative of ln(sin x)" }
```
```json
{ "session_id": "665b2c3d...", "status": "active", "phase": "analyzing" }
```

```http
POST /v1/sessions/665b2c3d.../messages
Content-Type: application/json
Accept: text/event-stream

{ "content": "Find the derivative of ln(sin x)", "client_message_id": "uuid-1" }
```
```
event: analysis
data: {"topic":"derivatives","subtopic":"chain_rule","difficulty":3,...}

event: token
data: {"text":"Before "}
...
event: done
data: {"message_id":"...","milestone":0,"hint_level":0}
```

---

## 8. Folder Structure

```
math_mentor_agent/
├── docs/
│   ├── ARCHITECTURE.md              # This document — single source of truth
│   └── DEMO_SCRIPT.md               # Judge walkthrough script
│
├── frontend/                        # React 19 · Vite 8 · React Router (SPA)
│   ├── index.html
│   ├── vite.config.ts               # dev proxy: /api → localhost:8000
│   ├── src/
│   │   ├── main.tsx                 # app entry
│   │   ├── App.tsx                  # route definitions
│   │   ├── index.css
│   │   ├── i18n.ts                  # react-i18next (en / zh)
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx    # Mastery overview dashboard
│   │   │   ├── ProblemPage.tsx      # New problem intake
│   │   │   ├── ChatPage.tsx         # Chat tutor UI + SSE
│   │   │   ├── ReportPage.tsx       # Learning analytics report
│   │   │   ├── ExercisesPage.tsx
│   │   │   └── ExerciseSetPage.tsx
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatMessageBubble.tsx
│   │   │   │   └── AgentTracePanel.tsx  # Debug panel — all 4 pillars live
│   │   │   ├── layout/              # AppLayout, Sidebar, LanguageSwitcher, …
│   │   │   ├── mastery/TopicProgress.tsx
│   │   │   ├── exercises/           # ExerciseProblemCard, QuickPracticeCard
│   │   │   └── ui/                  # shadcn/ui + latex-renderer, math inputs
│   │   ├── hooks/
│   │   │   └── useSessionSSE.ts     # POST + ReadableStream SSE consumer
│   │   ├── lib/
│   │   │   ├── api.ts               # axios client (/api/v1)
│   │   │   ├── utils.ts
│   │   │   └── math-problem.ts
│   │   ├── store/auth.ts            # zustand auth + profile
│   │   ├── types/sse.ts
│   │   └── locales/                 # en.json, zh.json
│   ├── Dockerfile                   # multi-stage: Vite build → nginx
│   ├── package.json
│   └── tsconfig.json
│
├── backend/                         # FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py                # Pydantic Settings — all env vars
│   │   ├── dependencies.py          # Auth, DB, Vertex client injection
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   ├── auth.py
│   │   │   ├── sessions.py
│   │   │   ├── messages.py          # SSE streaming endpoint
│   │   │   ├── exercises.py
│   │   │   ├── me.py                # Profile + analytics
│   │   │   └── health.py
│   │   ├── agents/
│   │   │   ├── orchestrator.py      # OrchestratorAgent
│   │   │   ├── analyzer.py          # AnalyzerAgent (3-phase)
│   │   │   ├── teaching.py          # TeachingAgent (2-phase + leak check)
│   │   │   ├── student_model.py     # StudentModelAgent (Critic + mastery)
│   │   │   ├── practice.py          # PracticeAgent
│   │   │   ├── analytics.py         # AnalyticsAgent (dashboard)
│   │   │   └── __init__.py
│   │   ├── models/
│   │   │   ├── agent.py             # All agent I/O types + SessionContext
│   │   │   ├── session.py           # AnalysisResult, ReasoningPlan, Milestone
│   │   │   ├── student.py           # StudentProfile, MasterySnapshot, ErrorPattern
│   │   │   └── message.py
│   │   ├── services/
│   │   │   ├── vertex_service.py    # GeminiService (classify, analyze, teach, leak_check)
│   │   │   ├── vertex_prompts.py    # All prompt templates
│   │   │   ├── vertex_types.py      # GeminiModel, GenerationConfig, PromptMessage
│   │   │   ├── mastery.py           # mastery_label(), mastery_pct(), update_mastery()
│   │   │   └── session_service.py   # SessionContext load/save, SSE orchestration
│   │   └── db/
│   │       ├── client.py            # Motor client + connection pool
│   │       └── repositories/
│   │           ├── base.py
│   │           ├── students.py
│   │           ├── sessions.py
│   │           ├── messages.py
│   │           ├── mastery_events.py
│   │           └── exercises.py
│   ├── tests/
│   │   ├── test_teaching.py
│   │   ├── test_analyzer_schema.py
│   │   ├── test_student_model.py
│   │   └── golden/                  # 50 answer-leak evaluation cases
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── openapi.yaml
│
├── infra/
│   ├── cloudbuild.yaml
│   ├── deploy/
│   │   ├── api.service.yaml
│   │   └── web.service.yaml
│   └── scripts/
│       └── seed_problem_library.py
│
├── .env.example
└── README.md
```

---

## 9. Development Roadmap

### 9.1 Phase Overview (10-Day Sprint)

| Phase | Days | Goal | Exit Criteria |
|-------|------|------|---------------|
| **0 — Foundation** | 1 | GCP + Mongo + Cloud Run hello world | `/health` and `/ready` green on Cloud Run URLs |
| **1 — Core agents** | 2–3 | All 5 core agents + orchestrator + FSM | CLI script completes 5-turn Socratic session without DB |
| **2 — API & memory** | 4–5 | Sessions, messages, mastery persistence, SSE streaming | curl completes 5-turn session with full persistence |
| **3 — Frontend** | 6–7 | Chat UI + SSE consumer + LaTeX + `AgentTracePanel` | End-to-end demo in browser on Cloud Run |
| **4 — Personalization** | 8 | PracticeAgent, exercises UI, AnalyticsAgent, mastery dashboard | Session end generates 3 exercises; leak rate < 5% |
| **5 — Demo hardening** | 9–10 | Eval set, DEMO_SCRIPT.md, Cloud Trace spans, README | Rehearsed demo under 5 minutes |

### 9.2 Day-by-Day Backlog

#### Phase 0 — Foundation (Day 1)
- [ ] GCP project: enable Vertex AI, Artifact Registry, Cloud Run, Secret Manager
- [ ] MongoDB Atlas cluster + database user + IP allowlist
- [ ] FastAPI skeleton: health, ready, structured logging (structlog)
- [ ] React + Vite skeleton: layout, Tailwind, dev proxy for API URL
- [ ] Cloud Build pipeline deploys both services

#### Phase 1 — Core Agents (Days 2–3)
- [ ] `vertex_service.py`: `GeminiService.classify()`, `.analyze()`, `.teach()`, `.leak_check()`
- [ ] `vertex_prompts.py`: all prompt templates (ORCHESTRATOR_SYSTEM, ANALYZER_SYSTEM, PLANNER_SYSTEM, TEACHING_ASSESSMENT_SYSTEM, TEACHING_REPLY_SYSTEM, CRITIC_SYSTEM)
- [ ] `SessionContext` Pydantic model + `AnalysisResult` + `ReasoningPlan`
- [ ] `AnalyzerAgent`: 3-phase pipeline + fallback
- [ ] `TeachingAgent`: 2-phase + leak check (already written)
- [ ] `StudentModelAgent`: Critic + deterministic mastery update
- [ ] `OrchestratorAgent`: fast_route + llm_route + dispatch (already written)
- [ ] Unit tests: schema validation + 5 golden classification cases

#### Phase 2 — API & Memory (Days 4–5)
- [ ] All MongoDB repositories: students, sessions, messages, mastery_events
- [ ] `SessionService`: load/save context per turn
- [ ] `POST /sessions`, `POST /sessions/{id}/messages` with SSE streaming
- [ ] `POST /sessions/{id}/stuck` — same SSE format
- [ ] Mastery EMA write-back on every critic verdict
- [ ] JWT auth: Google ID token exchange, JWT middleware
- [ ] Idempotency: `client_message_id` deduplication on message insert

#### Phase 3 — Frontend (Days 6–7)
- [ ] Google sign-in + token exchange
- [ ] Session create + chat with SSE consumer (`useSessionSSE.ts`)
- [ ] KaTeX rendering (`latex-renderer.tsx`) + MathLive input
- [ ] `AgentTracePanel.tsx`: shows route, models, milestone, verdict, leak_risk per turn
- [ ] "I'm stuck" button → `POST /stuck`
- [ ] Mastery bar component (`TopicProgress.tsx`)

#### Phase 4 — Personalization (Day 8)
- [ ] `PracticeAgent`: exercise generation + diversity check + `due_at`
- [ ] `exercises` repository
- [ ] Exercises list UI + mark complete
- [ ] `AnalyticsAgent`: mastery dashboard data
- [ ] `GET /me/mastery/history` endpoint
- [ ] Answer-leak eval harness (50 golden problems)

#### Phase 5 — Demo Hardening (Days 9–10)
- [ ] `DEMO_SCRIPT.md`: 5-minute judge path (all 4 pillars narrated)
- [ ] Cloud Trace: per-agent spans in `vertex_service.py`
- [ ] Seed `problem_library` with 20 curated showcase problems
- [ ] README: architecture diagram, setup, GIF screencast
- [ ] Rehearse: verify `agent_trace` panel visible, mastery bars update, leak test passes

### 9.3 Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| First-turn latency (Analyzer Phase 1 + Phase 2 sequential Pro calls) | High | Stream Phase 2.5 seed to student immediately after Phase 1; Phase 2 plan generation runs in background |
| Answer leakage in Teaching Agent | Critical | Structural plan-stripping + leak check + golden eval harness |
| Gemini preview model quota/availability | Medium | Keep `gemini-1.5-pro` / `gemini-1.5-flash` as env-var fallbacks; test quota before demo |
| MongoDB Atlas cold connection on Cloud Run scale-up | Medium | `min_instances=1` on API service; startup probe on `/ready` |
| Frontend SSE + KaTeX integration bugs | High | Build `AgentTracePanel` on Day 6 before mastery UI — it is the demo's key visual |
| Solo developer scope creep | Critical | Freeze features after Day 7; Days 8–10 are polish + demo only |

### 9.4 Hackathon Demo Narration Checklist

| Pillar | What to show in demo |
|--------|---------------------|
| **Reasoning** | `AgentTracePanel`: Analyzer JSON classification + Teaching Agent `SocraticAssessment` |
| **Planning** | `AgentTracePanel`: milestone `2/3` advancing as student works through problem |
| **Memory** | Returning student: mastery bars start at non-zero; error_patterns influence hint framing |
| **Multi-agent** | `AgentTracePanel`: `route: "critic->teaching"`, 2 model calls, `verdict`, `leak_risk` — 5 agents working every turn |

### 9.5 Post-MVP Backlog (v1.1+)

- Photo OCR (Vision API) for textbook problems
- SymPy symbolic checker for step validation (removes LLM dependency for Critic)
- Full SM-2 spaced repetition algorithm for exercises
- RAG over textbook chunks (Vertex AI Search + `text-embedding-005`)
- Instructor dashboard (class-level mastery analytics)
- `gemini-2.5-pro` stable release migration when preview ends

---

## Appendix A — Environment Variables

```bash
# API service
APP_ENV=production
JWT_SECRET=<min-32-char-random-string>       # Required — no default
GCP_PROJECT=mathmentor-prod
GCP_REGION=us-central1
VERTEX_LOCATION=us-central1
GEMINI_MODEL_PRO=gemini-2.5-pro-preview-05-06
GEMINI_MODEL_FLASH=gemini-2.5-flash-preview-05-20
MONGODB_URI=mongodb+srv://...                # Required — from Secret Manager
MONGODB_DB_NAME=mathmentor
CORS_ORIGINS=https://mathmentor-web-xxx.run.app
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com

# Frontend (React · Vite)
# Local dev: Vite proxies /api → http://localhost:8000 (see vite.config.ts)
# Production: nginx serves dist/ and proxies /api/ to mathmentor-api
VITE_API_URL=https://mathmentor-api-xxx.run.app/v1   # optional; build-time override
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com   # when Google OAuth UI is wired
```

---

*ARCHITECTURE.md · Version 2.1 · MathMentor · Canonical — frontend stack: React + Vite (not Next.js). Supersedes MATHMENTOR_DESIGN.md, MULTI_AGENT_ARCHITECTURE.md, MONGODB_DESIGN.md*
