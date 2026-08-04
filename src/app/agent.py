"""LARA — the Latram Shop support agent.

LangGraph ReAct agent: Gemini as primary brain with Groq (Llama 3.3) as
automatic fallback, the policy-retrieval tool and the safe analytics tools.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .analytics import ANALYTICS_TOOLS
from .charts import generate_chart
from .config import (
    AGENT_NAME,
    BRAND_NAME,
    GEMINI_MODEL,
    GOOGLE_API_KEY,
    GROQ_API_KEY,
    GROQ_MODEL,
    QUESTIONS_LOG,
)
from .retrieval import search_policies
from .weekly_report import report_summary

SYSTEM_PROMPT = f"""You are {AGENT_NAME}, the internal AI assistant for the \
support and operations team of {BRAND_NAME}, an e-commerce company operating \
across Latin America and North America.

LANGUAGE (CRITICAL RULE): Detect the language of the USER'S QUESTION and \
write your ENTIRE reply in that exact language. The policy passages are \
written in Spanish — when the user asks in English, translate the relevant \
facts into English. The language of retrieved context or tool outputs must \
NEVER change your reply language.

TOOLS AND GROUNDING:
- For questions about policies, rules, deadlines or processes, ALWAYS use \
search_policies and base your answer ONLY on the retrieved passages.
- For questions about sales, orders, metrics or data, use the analytics tools.
- For questions that mix policy and data (e.g. requests outside the allowed \
window), first retrieve the policy fact, then call the data tool with it.

CITATIONS: When answering from the policy corpus, cite the document and page \
like: (Política de Reembolsos y Devoluciones, p. 3).

COMPLETENESS: When a policy establishes a deadline or requirement, ALWAYS \
include its attached conditions in your answer (e.g., required photo/video \
evidence, eligibility requirements, channel restrictions). A deadline \
without its conditions is an incomplete answer.

HONESTY GUARDRAIL: If the answer is not in the retrieved passages or the \
data, say so explicitly and suggest contacting the corresponding team. NEVER \
invent policies, numbers, names or facts. Politely decline questions \
unrelated to {BRAND_NAME}'s policies or business data.

STYLE: Professional, concise, helpful. You serve employees, not end \
customers.

REPORT ROUTING (mandatory): for ANY question about the weekly report —
its figures, rates, weeks, or how a report metric is calculated — you MUST
call the report_summary tool FIRST and base every number on its output.
Never recompute report metrics through other tools.

FINAL CHECK before replying: does your reply language match the user's \
question language? If not, rewrite your reply in the user's language."""


def build_llm():
    """Primary Gemini with automatic Groq fallback (multi-provider resilience)."""
    if not GOOGLE_API_KEY and not GROQ_API_KEY:
        raise OSError(
            "No LLM credentials found. Set GOOGLE_API_KEY (and optionally "
            "GROQ_API_KEY as fallback) in your .env file."
        )

    primary = None
    if GOOGLE_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI

        # max_retries/timeout tuned from observability: default retry policy
        # kept a dead Gemini busy for 1,020s before falling back (LangSmith
        # trace, 2026-07-17). Fail fast -> fallback saves the answer.
        primary = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, temperature=0.2, max_retries=2, timeout=60
        )

    fallback = None
    if GROQ_API_KEY:
        from langchain_groq import ChatGroq

        fallback = ChatGroq(
            model=GROQ_MODEL, temperature=0.2, max_retries=2, timeout=30
        )

    if primary and fallback:
        return primary.with_fallbacks([fallback])
    return primary or fallback


def build_agent():
    tools = [search_policies, generate_chart, report_summary, *ANALYTICS_TOOLS]
    return create_react_agent(build_llm(), tools, prompt=SYSTEM_PROMPT)


def content_to_text(content) -> str:
    """Normalize LLM message content to plain text.

    Gemini 3.x returns content as a LIST of typed blocks (text + encrypted
    'thought signature' extras) instead of a plain string; older models and
    Groq return str. This helper makes every downstream consumer agnostic.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ).strip()
    return str(content)


# Injected into every question: recency-anchored, deterministic language steer.
# System-prompt rules alone proved insufficient when Spanish retrieved context
# dominated the window (observed language drift on EN cross-source questions).
LANGUAGE_REMINDER = (
    "\n\n[System note: reply strictly in the same language as the question "
    "above — English question, English answer; Spanish question, Spanish "
    "answer. Translate retrieved Spanish policy facts when needed.]"
)


def _usage(result: dict) -> dict:
    """Sum token usage across every LLM call in one agent run.

    LangChain attaches `usage_metadata` to each AIMessage, so a run's real
    cost is measurable locally — no observability vendor required.
    """
    inp = out = 0
    for m in result.get("messages", []):
        u = getattr(m, "usage_metadata", None) or {}
        inp += u.get("input_tokens", 0) or 0
        out += u.get("output_tokens", 0) or 0
    return {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


def _log_interaction(question: str, result: dict, latency_s: float = 0.0) -> None:
    """Append the question + tools used to a local JSONL audit log.

    Powers the weekly report's 'what does the team ask about' section
    (training-needs insight) and doubles as a provider-independent backup of
    interactions. Never breaks the agent on failure.
    """
    try:
        import json
        from datetime import datetime, timezone

        tools = [
            tc["name"]
            for m in result["messages"]
            if getattr(m, "tool_calls", None)
            for tc in m.tool_calls
        ]
        QUESTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(QUESTIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "question": question,
                        "tools": tools,
                        "latency_s": round(latency_s, 2),
                        **_usage(result),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass


def ask(agent, question: str) -> str:
    """Single-turn question -> final answer text."""
    import time

    _t0 = time.perf_counter()
    result = agent.invoke(
        {"messages": [HumanMessage(content=question + LANGUAGE_REMINDER)]}
    )
    _log_interaction(question, result, time.perf_counter() - _t0)
    return content_to_text(result["messages"][-1].content)
