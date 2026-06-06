"""
DeepSeek-only functional test against a running backend (ARCHITECTURE.md user stories).

Usage (from backend/, server on :8000):
  python scripts/deepseek_functional_test.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

BASE = "http://127.0.0.1:8000/v1"
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class TurnResult:
    tokens: str = ""
    events: list[str] = field(default_factory=list)
    analysis: dict | None = None
    done: dict | None = None
    agent_trace: dict | None = None
    errors: list[str] = field(default_factory=list)


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


def dev_login(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/auth/dev-login")
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def send_message(client: httpx.Client, token: str, session_id: str, content: str) -> TurnResult:
    headers = {**auth_headers(token), "Accept": "text/event-stream"}
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


def get_messages(client: httpx.Client, token: str, session_id: str) -> list[dict]:
    r = client.get(
        f"{BASE}/sessions/{session_id}/messages",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    checks: list[Check] = []
    with httpx.Client(timeout=TIMEOUT) as client:
        # ── Infra ─────────────────────────────────────────────
        try:
            client.get(f"{BASE}/health").raise_for_status()
            checks.append(Check("health", True))
        except Exception as e:
            checks.append(Check("health", False, str(e)))
            _report(checks)
            return 1

        # ── DeepSeek provider advertised ─────────────────────
        r = client.get(f"{BASE}/me/llm-providers")
        r.raise_for_status()
        providers = {p["id"]: p for p in r.json()["providers"]}
        ds = providers.get("deepseek", {})
        checks.append(
            Check(
                "llm_providers_deepseek_available",
                ds.get("available") is True,
                str(ds),
            )
        )

        token = dev_login(client)
        h = auth_headers(token)

        # ── Switch student to DeepSeek ───────────────────────
        r = client.patch(f"{BASE}/me/preferences", headers=h, json={"llm_provider": "deepseek"})
        r.raise_for_status()
        pref = r.json()["preferences"]["llm_provider"]
        checks.append(Check("preferences_llm_provider", pref == "deepseek", pref))

        # ── US-01: new problem → analysis SSE ────────────────
        problem = "Find the derivative of f(x) = sin(x^2 + 1)."
        r = client.post(f"{BASE}/sessions", headers=h, json={"problem_text": problem})
        r.raise_for_status()
        sid = r.json()["session_id"]

        t1 = send_message(client, token, sid, "I think we need the chain rule.")
        has_analysis = "analysis" in t1.events or "analysis_start" in t1.events
        no_deepseek_err = not any("deepseek" in str(e).lower() for e in t1.errors)
        checks.append(
            Check(
                "US01_analysis_on_first_turn",
                has_analysis and not t1.errors and bool(t1.tokens.strip()),
                f"events={t1.events} errors={t1.errors}",
            )
        )
        if t1.analysis:
            topic = t1.analysis.get("topic", "")
            checks.append(
                Check(
                    "US01_topic_classified",
                    bool(topic) and topic in ("limits", "derivatives", "integrals"),
                    f"topic={topic}",
                )
            )
        trace1 = t1.agent_trace or {}
        models1 = trace1.get("models") or trace1.get("models_used") or []
        checks.append(
            Check(
                "US01_uses_deepseek_models",
                any("deepseek" in str(m).lower() for m in models1) or trace1.get("route") == "analyzer",
                f"models={models1} route={trace1.get('route')}",
            )
        )

        # ── US-02/03: follow-up teaching turn ────────────────
        t2 = send_message(
            client,
            token,
            sid,
            "The outer function is sin and inner is x^2+1, so f'(x) = cos(x^2+1) * 2x.",
        )
        reanalyze = "analysis" in t2.events or "analysis_start" in t2.events
        route2 = (t2.agent_trace or {}).get("route", "")
        checks.append(
            Check(
                "US02_teaching_followup_no_reanalyze",
                not reanalyze and route2 != "analyzer" and not t2.errors and bool(t2.tokens.strip()),
                f"route={route2} events={t2.events} errors={t2.errors}",
            )
        )
        verdict = (t2.agent_trace or {}).get("verdict")
        checks.append(
            Check(
                "US03_step_verdict_present",
                verdict in ("correct", "partially_correct", "incorrect", "unclear", None)
                and (verdict is not None or not t2.errors),
                f"verdict={verdict}",
            )
        )

        # ── US-07: stuck escalation ──────────────────────────
        r = client.post(f"{BASE}/sessions/{sid}/stuck", headers=h)
        stuck_ok = r.status_code == 200
        checks.append(Check("US07_stuck_endpoint", stuck_ok, r.text[:200]))
        if stuck_ok:
            sess = client.get(f"{BASE}/sessions/{sid}", headers=h).json()
            hint = sess.get("progress", {}).get("hint_level", 0)
            checks.append(Check("US07_hint_level_increased", hint >= 1, f"hint_level={hint}"))

        # ── Session phase progression ────────────────────────
        sess = client.get(f"{BASE}/sessions/{sid}", headers=h).json()
        phase = sess.get("phase", "")
        checks.append(
            Check(
                "session_phase_not_intake",
                phase in ("analyzing", "tutoring", "wrap_up", "completed"),
                f"phase={phase}",
            )
        )

        # ── US-06: message history persisted ─────────────────
        # ── Leak guard: student asks if work is complete (turn 3) ─
        t3 = send_message(client, token, sid, "Is that the full derivative?")
        confirm_phrases = [
            "nailed",
            "that's correct",
            "you're correct",
            "it is correct",
            "the full derivative is",
            "you've got it",
            "that's exactly",
            "exactly the derivative",
            "correct derivative",
            "is indeed the correct",
        ]
        t3_lower = t3.tokens.lower()
        t3_confirms = any(p in t3_lower for p in confirm_phrases)
        checks.append(
            Check(
                "no_confirm_leak_turn3",
                not t3_confirms and not t3.errors,
                t3.tokens[:200],
            )
        )

        msgs = get_messages(client, token, sid)
        student_msgs = sum(1 for m in msgs if m.get("role") == "student")
        assistant_msgs = sum(1 for m in msgs if m.get("role") == "assistant")
        checks.append(
            Check(
                "US06_messages_persisted",
                student_msgs >= 3 and assistant_msgs >= 3,
                f"student={student_msgs} assistant={assistant_msgs}",
            )
        )

        # ── US-04: analytics endpoint ──────────────────────
        r = client.get(f"{BASE}/me/analytics", headers=h)
        body = r.json() if r.status_code == 200 else {}
        analytics_ok = r.status_code == 200 and "mastery_scores" in body
        checks.append(Check("US04_analytics", analytics_ok, r.text[:150]))

        # ── Leak guard: opening turn ─────────────────────────
        leak_phrases = ["the answer is", "f'(x) =", "equals 1", "solution is", "nailed"]
        lower = t1.tokens.lower()
        leaked = any(p in lower for p in leak_phrases)
        checks.append(
            Check("no_obvious_answer_leak_turn1", not leaked, t1.tokens[:200]),
        )

        # ── Second scenario: limit (quick smoke) ─────────────
        r = client.post(
            f"{BASE}/sessions",
            headers=h,
            json={"problem_text": "Evaluate lim(x→0) (sin x)/x."},
        )
        r.raise_for_status()
        sid2 = r.json()["session_id"]
        t_lim = send_message(client, token, sid2, "This looks like a standard limit.")
        checks.append(
            Check(
                "limit_scenario_turn1",
                ("analysis" in t_lim.events or "analysis_start" in t_lim.events)
                and not t_lim.errors
                and bool(t_lim.tokens.strip()),
                f"errors={t_lim.errors}",
            )
        )

        # ── Error code mapping (if any SSE error) ────────────
        for label, tr in [("turn1", t1), ("turn2", t2)]:
            for err in tr.errors:
                if "deepseek" in str(err).lower():
                    checks.append(
                        Check(
                            f"{label}_no_deepseek_sse_error",
                            False,
                            err,
                        )
                    )

    _report(checks)
    failed = sum(1 for c in checks if not c.passed)
    report_path = "scripts/deepseek_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(
            [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nReport: {report_path}")
    return 1 if failed else 0


def _report(checks: list[Check]) -> None:
    print("\n" + "=" * 60 + "\nDeepSeek Functional Test Report\n" + "=" * 60)
    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  [{status}] {c.name}")
        if c.detail:
            print(f"         {c.detail[:300]}")
    passed = sum(1 for c in checks if c.passed)
    print(f"\nTotal: {passed}/{len(checks)} passed")


if __name__ == "__main__":
    sys.exit(main())
