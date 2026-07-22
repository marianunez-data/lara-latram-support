"""Evaluation harness for LARA: gold set -> agent -> LLM-as-judge -> report.

How agents are evaluated in practice (and what this implements):
1. A gold question set with verified expected facts (data/eval/gold_questions.json).
2. An automated harness that runs every question through the real agent.
3. An LLM-as-judge that compares each answer against the expected facts and
   returns PASS / PARTIAL / FAIL with a one-line reason.
4. Human spot-checks over the judge's verdicts + LangSmith traces for the
   step-by-step reasoning of any suspicious case.

Free-tier friendly: sleeps between questions (EVAL_SLEEP seconds, default 8)
so Gemini's requests-per-minute limits are respected.

Usage:
    python -m src.app.evaluate
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from .agent import ask, build_agent, build_llm, content_to_text
from .config import BASE_DIR

GOLD_PATH = BASE_DIR / "data" / "eval" / "gold_questions.json"
RESULTS_DIR = BASE_DIR / "data" / "eval"
EVAL_SLEEP = float(os.getenv("EVAL_SLEEP", "8"))

JUDGE_PROMPT = """You are a strict evaluator of an AI support agent.

QUESTION asked to the agent:
{question}

EXPECTED key facts (ground truth):
{expected}

AGENT'S ANSWER:
{answer}

Category: {category}. For 'guardrail' questions, PASS means the agent clearly
declined or stated the information is not available, WITHOUT inventing facts.
For all other categories, PASS means the answer contains the expected key
facts (numbers must match; language of the reply must match the question's
language); PARTIAL means it is incomplete or missing the citation/precision;
FAIL means wrong, fabricated, or off-topic.

Reply with ONLY a JSON object, no markdown fences:
{{"verdict": "PASS|PARTIAL|FAIL", "reason": "<one short sentence>"}}"""


def judge(llm, item: dict, answer: str) -> dict:
    prompt = JUDGE_PROMPT.format(
        question=item["question"],
        expected=item["expected"],
        answer=answer,
        category=item["category"],
    )
    try:
        raw = content_to_text(llm.invoke(prompt).content).strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(raw.strip())
        if data.get("verdict") in {"PASS", "PARTIAL", "FAIL"}:
            return data
    except Exception as exc:  # judge failures must not kill the run
        return {"verdict": "NEEDS_REVIEW", "reason": f"judge error: {exc}"}
    return {"verdict": "NEEDS_REVIEW", "reason": f"unparseable judge reply: {raw[:60]}"}


def main() -> None:
    items = json.loads(GOLD_PATH.read_text(encoding="utf-8"))["questions"]
    agent = build_agent()
    judge_llm = build_llm()

    rows, t0 = [], time.time()
    print(
        f"Evaluating {len(items)} gold questions "
        f"(~{EVAL_SLEEP:.0f}s pause between each for rate limits)...\n"
    )

    for item in items:
        start = time.time()
        try:
            answer = ask(agent, item["question"])
            error = ""
        except Exception as exc:
            answer, error = "", str(exc)
        elapsed = time.time() - start

        verdict = (
            {"verdict": "ERROR", "reason": error[:120]}
            if error
            else judge(judge_llm, item, answer)
        )
        rows.append(
            {**item, "answer": answer, "elapsed_s": round(elapsed, 1), **verdict}
        )
        icon = {
            "PASS": "✅",
            "PARTIAL": "🟡",
            "FAIL": "❌",
            "ERROR": "💥",
            "NEEDS_REVIEW": "👀",
        }[verdict["verdict"]]
        print(
            f"{icon} Q{item['id']:>2} [{item['category']:<9}|{item['lang']}] "
            f"{verdict['verdict']:<12} {elapsed:5.1f}s  {verdict['reason'][:70]}"
        )
        time.sleep(EVAL_SLEEP)

    # --- Summary -------------------------------------------------------------
    total = len(rows)
    counts = {
        v: sum(r["verdict"] == v for r in rows)
        for v in ("PASS", "PARTIAL", "FAIL", "ERROR", "NEEDS_REVIEW")
    }
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r["verdict"] == "PASS")

    print(
        f"\n{'='*62}\nRESULT: {counts['PASS']}/{total} PASS "
        f"({counts['PASS']/total:.0%}) | PARTIAL {counts['PARTIAL']} | "
        f"FAIL {counts['FAIL']} | ERROR {counts['ERROR']} | "
        f"REVIEW {counts['NEEDS_REVIEW']}"
    )
    for cat, oks in sorted(by_cat.items()):
        print(f"  {cat:<10} {sum(oks)}/{len(oks)} pass")
    print(f"Total time: {(time.time()-t0)/60:.1f} min")

    # --- Markdown report ------------------------------------------------------
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    report = RESULTS_DIR / f"results_{stamp}.md"
    lines = [
        f"# LARA evaluation — {stamp}",
        f"\n**{counts['PASS']}/{total} PASS** | partial {counts['PARTIAL']}"
        f" | fail {counts['FAIL']} | error {counts['ERROR']}"
        f" | review {counts['NEEDS_REVIEW']}\n",
        "| # | Cat | Lang | Verdict | Reason |",
        "|---|-----|------|---------|--------|",
    ]
    lines += [
        f"| {r['id']} | {r['category']} | {r['lang']} | "
        f"{r['verdict']} | {r['reason'].replace('|', '/')} |"
        for r in rows
    ]
    lines.append("\n## Answers\n")
    for r in rows:
        lines += [
            f"### Q{r['id']} ({r['lang']}) — {r['verdict']}",
            f"**Q:** {r['question']}\n",
            f"**Expected:** {r['expected']}\n",
            f"**Answer:** {r['answer'] or '(error)'}\n",
        ]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved: {report}")


if __name__ == "__main__":
    main()
