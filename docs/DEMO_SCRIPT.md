# MathMentor — 5-Minute Demo Script

> Narrate all four hackathon pillars using the live UI Agent Trace panel.

## Setup (before judges arrive)

1. Backend + frontend running (or Cloud Run URLs)
2. Dev-login as returning student (non-zero mastery bars)
3. Open a prepared problem: `Find the derivative of ln(sin x)`
4. Clear browser cache / use incognito for clean trace panel

---

## Minute 0:00 — Reasoning (Problem Analyzer)

**Say:** "MathMentor never gives answers. It classifies the problem and plans internally."

1. Paste problem → start session
2. Point to **Agent Trace** → `Problem Analyzer` event
3. Highlight: `topic: derivatives`, `subtopic: chain_rule`, `difficulty: 3/5`
4. **Do not** reveal milestone goals (server-only plan)

---

## Minute 1:00 — Planning (Milestone graph)

**Say:** "A reasoning plan drives pacing — milestones advance as the student works."

1. Submit a partial step: `Let u = sin x`
2. Show trace: `milestone: 1/3`, `route: critic→teaching`
3. Submit improved step with chain-rule factor
4. Show milestone advancing to `2/3`

---

## Minute 1:30 — Memory (Student Model)

**Say:** "Every step updates mastery and error patterns."

1. Point to `verdict: partially_correct` and `error_tag: missing_chain_rule_factor`
2. Open **Dashboard** → mastery bar for derivatives shifted
3. Mention returning student: bars start above zero

---

## Minute 2:00 — Multi-agent collaboration

**Say:** "Five agents collaborate every turn — visible in the trace."

1. Expand trace entry: `models: [gemini-2.5-flash]`, `latency_ms`, `leak_risk: 0.03`
2. Click **I'm stuck** → hint level increases (SSE stream, same as message)
3. Show `hint_level: 2` in trace without answer leakage

---

## Minute 3:00 — Answer embargo

**Say:** "Structural plan-stripping plus leak check keeps answers hidden."

1. Ask "Is my work complete?" 
2. Show tutor asks a check question — does **not** confirm the final derivative
3. Optional: mention golden eval harness (`pytest tests/golden/`)

---

## Minute 4:00 — Personalisation (Practice Agent)

**Say:** "Session end generates targeted exercises."

1. Complete session → 3 practice problems appear on Dashboard
2. Open **Report** page → learning tip + recommended next topic
3. Show one exercise marked complete → mastery nudges again

---

## Minute 5:00 — Close

**Say:** "Calculus I–II scope, Cloud Run + Vertex AI, MongoDB memory, full audit trail."

| Pillar | Evidence shown |
|--------|----------------|
| Reasoning | Analyzer classification + Socratic assessment in trace |
| Planning | Milestone `n/3` progression |
| Memory | Mastery bars + error tags influencing hints |
| Multi-agent | `critic→teaching` route, multiple model calls per turn |

---

## Fallback talking points

- LLM provider switch (Gemini / DeepSeek) in sidebar
- `POST /v1/analyze` for standalone classification demo
- `problem_library` seed fallback when generation fails
- Rate limits + idempotent message IDs for production safety
