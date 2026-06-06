"""Smoke test: reach wrap_up and trigger Practice agent with DeepSeek."""
from __future__ import annotations

import json
import uuid

import httpx

BASE = "http://127.0.0.1:8000/v1"
TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)


def parse_sse(body: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    event_name = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event_name:
            out.append((event_name, json.loads(line.split(":", 1)[1].strip())))
            event_name = None
    return out


def main() -> None:
    with httpx.Client(timeout=TIMEOUT) as c:
        token = c.post(f"{BASE}/auth/dev-login").raise_for_status().json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}
        c.patch(f"{BASE}/me/preferences", headers=h, json={"llm_provider": "deepseek"})
        sid = c.post(
            f"{BASE}/sessions",
            headers=h,
            json={"problem_text": "Differentiate g(x) = (3x+1)^4"},
        ).json()["session_id"]

        msgs = [
            "I need the chain rule.",
            "g prime of x equals 4 times (3x+1) cubed",
            "times 3 so 12 times (3x+1) cubed",
            "I think we are finished",
        ]
        for i, msg in enumerate(msgs, 1):
            body = {"content": msg, "client_message_id": str(uuid.uuid4())}
            with c.stream(
                "POST",
                f"{BASE}/sessions/{sid}/messages",
                headers={**h, "Accept": "text/event-stream"},
                json=body,
            ) as resp:
                text = resp.read().decode("utf-8", "replace")
            evs = parse_sse(text)
            practice = [e for e, _ in evs if e == "practice_start"]
            done = next((d for e, d in evs if e == "done"), {})
            sess = c.get(f"{BASE}/sessions/{sid}", headers=h).json()
            prog = sess.get("progress", {})
            print(
                f"turn{i}: phase={sess.get('phase')} "
                f"milestone={prog.get('current_milestone')} "
                f"solution_ready={prog.get('solution_ready')} "
                f"practice_sse={bool(practice)} "
                f"exercises={bool(done.get('exercises'))}"
            )


if __name__ == "__main__":
    main()
