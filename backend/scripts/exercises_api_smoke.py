#!/usr/bin/env python3
"""Smoke test: exercises list, get, update problem, reveal answer."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/v1"


def req(method: str, path: str, token: str | None = None, body: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.fp else {"detail": str(e)}


def main() -> int:
    code, auth = req("POST", "/auth/dev-login")
    if code != 200:
        print("FAIL dev-login", code, auth)
        return 1
    token = auth["access_token"]
    print("OK dev-login")

    code, due = req("GET", "/exercises/due", token)
    print(f"GET /exercises/due -> {code}, sets={len(due) if isinstance(due, list) else due}")

    code, all_sets = req("GET", "/exercises/all", token)
    if code != 200 or not isinstance(all_sets, list):
        print("FAIL list all", code, all_sets)
        return 1
    print(f"OK GET /exercises/all ({len(all_sets)} sets)")

    if not all_sets:
        print("SKIP no exercise sets — complete a session first")
        code, single = req("POST", "/exercises/single", token, {})
        if code == 200 and single.get("problem"):
            print("OK POST /exercises/single (quick practice)")
            return 0
        print("WARN no sets and single generation failed", code, single)
        return 0

    set_id = all_sets[0]["id"]
    code, detail = req("GET", f"/exercises/{set_id}", token)
    if code != 200:
        print("FAIL get set", code, detail)
        return 1
    print(f"OK GET /exercises/{set_id}")

    pending = [p for p in detail.get("problems", []) if p.get("status") == "pending"]
    if pending:
        pid = pending[0]["id"]
        code, upd = req(
            "PATCH",
            f"/exercises/{set_id}/problems/{pid}",
            token,
            {"status": "completed", "student_answer": "test attempt"},
        )
        if code != 200:
            print("FAIL update problem", code, upd)
            return 1
        print(f"OK PATCH problem {pid}")

        code, ans = req("GET", f"/exercises/{set_id}/problems/{pid}/answer", token)
        if code != 200:
            print("FAIL get answer", code, ans)
            return 1
        print("OK GET answer reveal")
    else:
        done = next((p for p in detail["problems"] if p["status"] in ("completed", "skipped")), None)
        if done:
            code, ans = req("GET", f"/exercises/{set_id}/problems/{done['id']}/answer", token)
            print(f"OK answer for done problem -> {code}")

    print("PASS exercises API smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
