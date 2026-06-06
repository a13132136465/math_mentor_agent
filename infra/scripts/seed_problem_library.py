#!/usr/bin/env python3
"""
Seed the problem_library collection with curated Calculus I–II showcase problems.

Usage (from backend/):
    python -m scripts.seed_problem_library
    # or
    python ../infra/scripts/seed_problem_library.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root or backend/
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.config import get_settings  # noqa: E402

PROBLEMS = [
    # ── Derivatives (8) ───────────────────────────────────────────
    {
        "prompt": r"Find \( \frac{d}{dx}[x^4 - 3x^2 + 7] \)",
        "topic": "derivatives", "subtopic": "power_rule", "difficulty": 2,
        "target_skill": "power_rule",
        "learning_intention": "Differentiate a polynomial term by term.",
        "answer": r"\( 4x^3 - 6x \)",
    },
    {
        "prompt": r"Differentiate \( f(x) = \sin(3x) \)",
        "topic": "derivatives", "subtopic": "chain_rule", "difficulty": 3,
        "target_skill": "missing_chain_rule_factor",
        "learning_intention": "Apply the chain rule to a trigonometric composition.",
        "answer": r"\( f'(x) = 3\cos(3x) \)",
    },
    {
        "prompt": r"Find \( \frac{d}{dx}[\ln(x^2 + 1)] \)",
        "topic": "derivatives", "subtopic": "chain_rule", "difficulty": 3,
        "target_skill": "missing_chain_rule_factor",
        "learning_intention": "Chain rule with a logarithmic outer function.",
        "answer": r"\( \frac{2x}{x^2 + 1} \)",
    },
    {
        "prompt": r"Find \( \frac{d}{dx}[e^{2x}\cos x] \)",
        "topic": "derivatives", "subtopic": "product_rule", "difficulty": 4,
        "target_skill": "wrong_derivative_rule",
        "learning_intention": "Combine product rule with basic derivative rules.",
        "answer": r"\( 2e^{2x}\cos x - e^{2x}\sin x \)",
    },
    {
        "prompt": r"Find \( \frac{d}{dx}\left[\frac{x}{x+1}\right] \)",
        "topic": "derivatives", "subtopic": "quotient_rule", "difficulty": 3,
        "target_skill": "wrong_derivative_rule",
        "learning_intention": "Apply the quotient rule carefully.",
        "answer": r"\( \frac{1}{(x+1)^2} \)",
    },
    {
        "prompt": r"If \( x^2 + y^2 = 25 \), find \( \frac{dy}{dx} \)",
        "topic": "derivatives", "subtopic": "implicit", "difficulty": 4,
        "target_skill": "conceptual_gap",
        "learning_intention": "Implicit differentiation on a circle equation.",
        "answer": r"\( \frac{dy}{dx} = -\frac{x}{y} \)",
    },
    {
        "prompt": r"Find \( \frac{d}{dx}[\arctan(x^2)] \)",
        "topic": "derivatives", "subtopic": "chain_rule", "difficulty": 4,
        "target_skill": "missing_chain_rule_factor",
        "learning_intention": "Chain rule with inverse tangent.",
        "answer": r"\( \frac{2x}{1 + x^4} \)",
    },
    {
        "prompt": r"Find \( \frac{d}{dx}[\sqrt{x^2 + 4}] \)",
        "topic": "derivatives", "subtopic": "chain_rule", "difficulty": 3,
        "target_skill": "missing_chain_rule_factor",
        "learning_intention": "Rewrite the square root as a power, then chain rule.",
        "answer": r"\( \frac{x}{\sqrt{x^2 + 4}} \)",
    },
    # ── Limits (6) ────────────────────────────────────────────────
    {
        "prompt": r"Evaluate \( \lim_{x \to 0} \frac{\sin(5x)}{x} \)",
        "topic": "limits", "subtopic": "indeterminate_forms", "difficulty": 2,
        "target_skill": "limit_form_error",
        "learning_intention": "Use the standard \( \sin u / u \) limit.",
        "answer": r"\( 5 \)",
    },
    {
        "prompt": r"Find \( \lim_{x \to 2} \frac{x^2 - 4}{x - 2} \)",
        "topic": "limits", "subtopic": "indeterminate_forms", "difficulty": 2,
        "target_skill": "incorrect_factoring",
        "learning_intention": "Factor to resolve a 0/0 form.",
        "answer": r"\( 4 \)",
    },
    {
        "prompt": r"Evaluate \( \lim_{x \to \infty} \frac{3x^2 + 1}{x^2 - 4} \)",
        "topic": "limits", "subtopic": "infinity_limits", "difficulty": 3,
        "target_skill": "limit_form_error",
        "learning_intention": "Compare leading terms at infinity.",
        "answer": r"\( 3 \)",
    },
    {
        "prompt": r"Find \( \lim_{x \to 0^+} \ln x \)",
        "topic": "limits", "subtopic": "one_sided", "difficulty": 2,
        "target_skill": "conceptual_gap",
        "learning_intention": "One-sided limit of the natural log.",
        "answer": r"\( -\infty \)",
    },
    {
        "prompt": r"Evaluate \( \lim_{x \to 0} \frac{1 - \cos x}{x^2} \)",
        "topic": "limits", "subtopic": "indeterminate_forms", "difficulty": 3,
        "target_skill": "wrong_trig_identity",
        "learning_intention": "Use a standard trigonometric limit or identity.",
        "answer": r"\( \frac{1}{2} \)",
    },
    {
        "prompt": r"Find \( \lim_{x \to 3} |x - 3| \)",
        "topic": "limits", "subtopic": "continuity", "difficulty": 1,
        "target_skill": "conceptual_gap",
        "learning_intention": "Evaluate a continuous piecewise-smooth function.",
        "answer": r"\( 0 \)",
    },
    # ── Integrals (6) ─────────────────────────────────────────────
    {
        "prompt": r"Compute \( \int (2x^3 - x)\,dx \)",
        "topic": "integrals", "subtopic": "ftc_part2", "difficulty": 2,
        "target_skill": "forgot_constant_of_integration",
        "learning_intention": "Integrate term by term; don't forget \( +C \).",
        "answer": r"\( \frac{x^4}{2} - \frac{x^2}{2} + C \)",
    },
    {
        "prompt": r"Evaluate \( \int_0^{\pi/2} \cos x\,dx \)",
        "topic": "integrals", "subtopic": "ftc_part2", "difficulty": 2,
        "target_skill": "wrong_integral_bounds",
        "learning_intention": "Definite integral of cosine on \( [0, \pi/2] \).",
        "answer": r"\( 1 \)",
    },
    {
        "prompt": r"Find \( \int x e^{x^2}\,dx \)",
        "topic": "integrals", "subtopic": "u_substitution", "difficulty": 3,
        "target_skill": "conceptual_gap",
        "learning_intention": "Recognize \( u = x^2 \) substitution.",
        "answer": r"\( \frac{1}{2}e^{x^2} + C \)",
    },
    {
        "prompt": r"Evaluate \( \int_1^e \frac{1}{x}\,dx \)",
        "topic": "integrals", "subtopic": "ftc_part2", "difficulty": 2,
        "target_skill": "wrong_integral_bounds",
        "learning_intention": "Logarithmic integral over \( [1, e] \).",
        "answer": r"\( 1 \)",
    },
    {
        "prompt": r"Compute \( \int \sin x \cos x\,dx \)",
        "topic": "integrals", "subtopic": "u_substitution", "difficulty": 3,
        "target_skill": "wrong_trig_identity",
        "learning_intention": "Use \( u = \sin x \) or a double-angle identity.",
        "answer": r"\( \frac{\sin^2 x}{2} + C \) (or equivalent)",
    },
    {
        "prompt": r"Find \( \int_0^1 x\sqrt{1 - x^2}\,dx \)",
        "topic": "integrals", "subtopic": "u_substitution", "difficulty": 4,
        "target_skill": "conceptual_gap",
        "learning_intention": "Substitution with a square-root integrand.",
        "answer": r"\( \frac{1}{3} \)",
    },
]


async def main() -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]
    col = db.problem_library

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    inserted = 0
    for p in PROBLEMS:
        existing = await col.find_one({
            "prompt": p["prompt"],
            "topic": p["topic"],
        })
        if existing:
            continue
        doc = {**p, "created_at": now, "schema_version": 1}
        await col.insert_one(doc)
        inserted += 1

    total = await col.count_documents({})
    print(f"Seeded {inserted} new problems ({total} total in problem_library).")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
