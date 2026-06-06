"""
Multi-scenario tutor chat continuity test against a running backend.

Usage (from backend/, server on :8000):
  python scripts/tutor_chat_continuity_test.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

BASE = "http://127.0.0.1:8000/v1"
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


def safe_print(text: str) -> None:
    """Avoid GBK console crashes on Windows when output contains Unicode."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"
        ))


@dataclass
class TurnResult:
    tokens: str = ""
    events: list[str] = field(default_factory=list)
    analysis: dict | None = None
    done: dict | None = None
    agent_trace: dict | None = None
    errors: list[str] = field(default_factory=list)
    raw_events: list[tuple[str, dict]] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    session_id: str
    turns: list[TurnResult] = field(default_factory=list)
    messages_after: list[dict] = field(default_factory=list)
    session_phase: str = ""
    issues: list[str] = field(default_factory=list)
    llm_errors: list[str] = field(default_factory=list)


def dev_login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/dev-login")
    r.raise_for_status()
    return r.json()["access_token"]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    event_name = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event_name:
            try:
                data = json.loads(line.split(":", 1)[1].strip())
            except json.JSONDecodeError:
                data = {"_raw": line}
            out.append((event_name, data))
            event_name = None
    return out


def send_message(client: httpx.Client, token: str, session_id: str, content: str) -> TurnResult:
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}
    body = {"content": content, "client_message_id": str(uuid.uuid4())}
    tr = TurnResult()
    with client.stream(
        "POST",
        f"{BASE}/sessions/{session_id}/messages",
        headers=headers,
        json=body,
        timeout=TIMEOUT,
    ) as resp:
        if resp.status_code != 200:
            tr.errors.append(f"HTTP {resp.status_code}: {resp.read().decode()[:500]}")
            return tr
        text = resp.read().decode()
    for ev, data in parse_sse(text):
        tr.events.append(ev)
        tr.raw_events.append((ev, data))
        if ev == "token":
            tr.tokens += data.get("text", "")
        elif ev == "analysis":
            tr.analysis = data
        elif ev == "done":
            tr.done = data
        elif ev == "agent_trace":
            tr.agent_trace = data
        elif ev == "error":
            tr.errors.append(str(data))
    return tr


def create_session(client: httpx.Client, token: str, problem: str) -> str:
    r = client.post(
        f"{BASE}/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"problem_text": problem},
    )
    r.raise_for_status()
    return r.json()["session_id"]


def get_messages(client: httpx.Client, token: str, session_id: str) -> list[dict]:
    r = client.get(
        f"{BASE}/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


def get_session(client: httpx.Client, token: str, session_id: str) -> dict:
    r = client.get(
        f"{BASE}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


def _turn_had_llm_error(t: TurnResult) -> bool:
    return bool(t.errors) or "error" in t.events


def check_continuity(sc: ScenarioResult) -> None:
    """Continuity checks (routing, phase, re-analyze). LLM failures tracked separately."""
    if not sc.turns:
        sc.issues.append("no turns executed")
        return

    for i, t in enumerate(sc.turns, start=1):
        if t.errors or "error" in t.events:
            sc.llm_errors.append(f"turn{i}: {t.errors or 'SSE error event'}")
            continue
        if not t.tokens.strip():
            sc.issues.append(f"turn{i}: empty tutor response (no error event)")
        if "done" not in t.events:
            sc.issues.append(f"turn{i}: missing done event")

    t0 = sc.turns[0]
    if not _turn_had_llm_error(t0):
        if "analysis" not in t0.events and "analysis_start" not in t0.events:
            sc.issues.append("turn1: missing analysis SSE on new session")

    for i, t in enumerate(sc.turns[1:], start=2):
        if _turn_had_llm_error(t):
            continue
        if "analysis" in t.events or "analysis_start" in t.events:
            sc.issues.append(f"turn{i}: unexpected analysis event (re-analyze bug)")
        trace = t.agent_trace or {}
        route = trace.get("route", "")
        if route == "analyzer":
            sc.issues.append(f"turn{i}: route still analyzer (should be teaching)")

    roles = [m.get("role") for m in sc.messages_after]
    student_count = sum(1 for r in roles if r == "student")
    if student_count < len(sc.turns):
        sc.issues.append(
            f"student messages {student_count} < turns {len(sc.turns)}"
        )

    ok_turns = sum(1 for t in sc.turns if not _turn_had_llm_error(t))
    assistant_count = sum(1 for r in roles if r == "assistant")
    if assistant_count < ok_turns:
        sc.issues.append(
            f"assistant messages {assistant_count} < successful turns {ok_turns}"
        )

    if sc.session_phase == "intake" and any(
        not _turn_had_llm_error(t) for t in sc.turns
    ):
        sc.issues.append("session phase still intake after successful turn(s)")

    for i, t in enumerate(sc.turns, start=1):
        if _turn_had_llm_error(t):
            continue
        trace = t.agent_trace or {}
        if trace.get("student_understanding", "").startswith("Unable to assess"):
            sc.issues.append(f"turn{i}: legacy fallback text still present")


SCENARIOS: list[tuple[str, str, list[str]]] = [
    (
        "chain_rule_3turn",
        "Find the derivative of f(x) = sin(x^2 + 1).",
        [
            "I think we need the chain rule because it's a composition.",
            "The outer function is sin and inner is x^2+1, so f'(x) = cos(x^2+1) * 2x.",
            "Is that the full derivative?",
        ],
    ),
    (
        "limit_2turn",
        "Evaluate lim(x→0) (sin x)/x.",
        [
            "This looks like a standard limit; maybe L'Hopital?",
            "Using L'Hopital: cos(x)/1, so the limit is 1.",
        ],
    ),
]

# Set QUICK=1 to run only 2 scenarios (faster smoke test)
import os
if os.environ.get("QUICK", "0") != "1":
    SCENARIOS.extend([
        (
            "integral_2turn",
            "Compute ∫ 2x cos(x^2) dx.",
            [
                "Substitution: let u = x^2, du = 2x dx.",
                "Then ∫ cos(u) du = sin(u) + C = sin(x^2) + C.",
            ],
        ),
        (
            "wrong_then_fix",
            "Differentiate g(x) = (3x+1)^4.",
            [
                "g'(x) = 4(3x+1)^3.",
                "Oh, chain rule: g'(x) = 4(3x+1)^3 * 3 = 12(3x+1)^3.",
            ],
        ),
        (
            "off_topic_recovery",
            "Find dy/dx if y = ln(x^3 + 2x).",
            [
                "What's the weather like today?",
                "Sorry — for ln(x^3+2x) I use chain rule: y' = (3x^2+2)/(x^3+2x).",
            ],
        ),
    ])


def run_scenario(client: httpx.Client, token: str, name: str, problem: str, msgs: list[str]) -> ScenarioResult:
    sc = ScenarioResult(name=name, session_id="")
    safe_print(f"\n{'='*60}\nScenario: {name}\nProblem: {problem[:70]}...")
    sid = create_session(client, token, problem)
    sc.session_id = sid
    for i, msg in enumerate(msgs, start=1):
        safe_print(f"  Turn {i}: {msg[:60]}...")
        t0 = time.time()
        tr = send_message(client, token, sid, msg)
        elapsed = time.time() - t0
        sc.turns.append(tr)
        preview = (tr.tokens.strip()[:120] + "...") if len(tr.tokens.strip()) > 120 else tr.tokens.strip()
        route = (tr.agent_trace or {}).get("route", "?")
        safe_print(f"    {elapsed:.1f}s | route={route} | tokens={len(tr.tokens)} | events={tr.events}")
        if preview:
            safe_print(f"    Reply: {preview}")
        if tr.errors:
            safe_print(f"    ERRORS: {tr.errors}")
        time.sleep(0.5)

    sc.messages_after = get_messages(client, token, sid)
    sess = get_session(client, token, sid)
    sc.session_phase = sess.get("phase", "")
    safe_print(
        f"  Session phase={sc.session_phase} "
        f"milestone={sess.get('progress', {}).get('current_milestone')}"
    )
    check_continuity(sc)
    return sc


def main() -> int:
    results: list[ScenarioResult] = []
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            r = client.get(f"{BASE}/health")
            r.raise_for_status()
        except Exception as e:
            print(f"Backend not reachable at :8000 — {e}")
            return 1

        token = dev_login(client)
        headers = {"Authorization": f"Bearer {token}"}
        provider = os.environ.get("LLM_PROVIDER", "deepseek")
        client.patch(
            f"{BASE}/me/preferences",
            headers=headers,
            json={"llm_provider": provider},
        ).raise_for_status()
        print(f"Using llm_provider={provider}")

        for name, problem, msgs in SCENARIOS:
            try:
                results.append(run_scenario(client, token, name, problem, msgs))
            except Exception as exc:
                sc = ScenarioResult(name=name, session_id="")
                sc.issues.append(f"scenario crashed: {exc}")
                results.append(sc)

    print(f"\n{'='*60}\nSUMMARY")
    failed = 0
    for sc in results:
        status = "PASS" if not sc.issues else "FAIL"
        if sc.issues:
            failed += 1
        warn = " WARN" if sc.llm_errors else ""
        print(f"  [{status}{warn}] {sc.name} (session={sc.session_id[:12]}...) phase={sc.session_phase}")
        for issue in sc.issues:
            print(f"       [continuity] {issue}")
        for err in sc.llm_errors:
            print(f"       [llm] {err}")

    report_path = "scripts/tutor_chat_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "name": sc.name,
                    "session_id": sc.session_id,
                    "issues": sc.issues,
                    "llm_errors": sc.llm_errors,
                    "session_phase": sc.session_phase,
                    "turns": [
                        {
                            "events": t.events,
                            "errors": t.errors,
                            "response_preview": t.tokens[:300],
                            "agent_trace": t.agent_trace,
                            "done": t.done,
                        }
                        for t in sc.turns
                    ],
                    "message_count": len(sc.messages_after),
                }
                for sc in results
            ],
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nReport written to {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
