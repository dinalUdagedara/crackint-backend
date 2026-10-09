"""
Compare models on answer scoring (session_qa.evaluate) against evals/answer_scoring.json.

Each case has an expected score range; a model "passes" a case when its score falls inside it.
Makes real OpenAI calls (one per case per model) using OPENAI_API_KEY from .env.

Usage:
    python scripts/eval_answer_scoring.py                       # SESSION_QA_AGENT_MODEL
    python scripts/eval_answer_scoring.py gpt-4o-mini gpt-4.1-mini gpt-4o
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

# Count cost locally instead of writing llm_usage rows.
settings.LLM_USAGE_TRACKING_ENABLED = False
settings.SESSION_QA_AGENT_ENABLED = True

from app.agents import session_qa_agent  # noqa: E402
from app.services import llm  # noqa: E402

EVAL_FILE = Path(__file__).resolve().parents[1] / "evals" / "answer_scoring.json"


async def run_model(model: str, data: dict) -> dict:
    settings.SESSION_QA_AGENT_MODEL = model
    costs: list[float] = []
    original_record = llm.record_usage

    async def collect(record):
        if record.cost_usd is not None:
            costs.append(record.cost_usd)
        await original_record(record)

    llm.record_usage = collect
    rows = []
    try:
        for case in data["cases"]:
            start = time.monotonic()
            result = await session_qa_agent.evaluate_answer(
                question=case["question"],
                answer=case["answer"],
                role_level=data["role_level"],
                job_entities=data["job_entities"],
                resume_entities=data["resume_entities"],
            )
            lo, hi = case["expected"]
            rows.append(
                {
                    "id": case["id"],
                    "score": result.score,
                    "expected": case["expected"],
                    "ok": lo <= result.score <= hi,
                    "distance": 0 if lo <= result.score <= hi else min(abs(result.score - lo), abs(result.score - hi)),
                    "seconds": time.monotonic() - start,
                }
            )
    finally:
        llm.record_usage = original_record
    return {
        "model": model,
        "rows": rows,
        "pass_rate": sum(r["ok"] for r in rows) / len(rows),
        "mean_distance": statistics.mean(r["distance"] for r in rows),
        "mean_seconds": statistics.mean(r["seconds"] for r in rows),
        "cost_usd": sum(costs),
    }


async def main(models: list[str]) -> None:
    if not settings.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY is not set.")
    data = json.loads(EVAL_FILE.read_text())
    results = [await run_model(m, data) for m in models]

    for res in results:
        print(f"\n== {res['model']}")
        for r in res["rows"]:
            flag = "ok " if r["ok"] else "OUT"
            print(f"  {flag} {r['id']:<28} score={r['score']:>3} expected={r['expected']}")
    print("\nmodel                 pass   mean-miss  sec/call  cost($)")
    for res in results:
        print(
            f"{res['model']:<20} {res['pass_rate']:>5.0%}  {res['mean_distance']:>9.1f}"
            f"  {res['mean_seconds']:>8.2f}  {res['cost_usd']:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or [settings.SESSION_QA_AGENT_MODEL]))
