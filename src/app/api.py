"""LARA web service: FastAPI API + Gradio chat UI in one process.

Routes:
    GET  /health   -> liveness + model config (no LLM call)
    POST /ask      -> {"question": "..."} -> {"answer": "..."}
    GET  /report   -> latest weekly interactive report (HTML)
    /              -> Gradio chat (charts render inline)

Design notes: the agent and the vector index are initialized LAZILY on the
first question, so the container boots fast and /health responds instantly.
Run locally:  uvicorn src.app.api:app --port 7860
"""

from __future__ import annotations

import re
import threading

import gradio as gr
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .config import (
    AGENT_NAME,
    BASE_DIR,
    BRAND_NAME,
    GEMINI_MODEL,
    GROQ_MODEL,
    VECTORSTORE_DIR,
)

REPORT_HTML = BASE_DIR / "data" / "reports" / "weekly_report.html"
LOGO = BASE_DIR / "assets" / "logo_latram.png"
CHART_RE = re.compile(r"(/\S*?data/charts/[\w\-]+\.png)")

_agent = None
_lock = threading.Lock()

# --- Hugging Face ZeroGPU compliance -------------------------------------
# ZeroGPU only boots apps whose gradio graph wires >=1 @spaces.GPU handler.
# LARA is CPU-only, so we register a hidden no-op event. Locally (no
# `spaces` package) all of this is skipped.
IS_SPACE = bool(__import__("os").getenv("SPACE_ID"))
try:
    import spaces as _spaces

    @_spaces.GPU
    def _zerogpu_noop():
        return None

    _HAS_SPACES = True
except ImportError:
    _HAS_SPACES = False

# On Spaces the /report FastAPI route is unavailable (gradio-native launch),
# so we serve the file through gradio's static file route instead.
gr.set_static_paths(paths=[str(REPORT_HTML.parent)])
REPORT_HREF = f"/gradio_api/file={REPORT_HTML}" if IS_SPACE else "/report"


def get_agent():
    """Build the index (first boot) and the agent once, thread-safely."""
    global _agent
    if _agent is None:
        with _lock:
            if _agent is None:
                if not VECTORSTORE_DIR.exists():
                    from . import build_index

                    build_index.main()
                from .agent import build_agent

                _agent = build_agent()
    return _agent


def answer(question: str) -> str:
    from .agent import ask

    return ask(get_agent(), question)


# ------------------------------ FastAPI ---------------------------------

app = FastAPI(title=f"{AGENT_NAME} — {BRAND_NAME} support agent")


class Question(BaseModel):
    question: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "primary_model": GEMINI_MODEL,
        "fallback_model": GROQ_MODEL,
    }


@app.post("/ask")
def ask_route(q: Question):
    try:
        return {"answer": answer(q.question)}
    except Exception as exc:  # keep the API alive on provider hiccups
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/report")
def report():
    if REPORT_HTML.exists():
        return FileResponse(REPORT_HTML, media_type="text/html")
    return JSONResponse(
        status_code=404,
        content={
            "error": "No weekly report generated yet. Run: python -m src.app.weekly_report --dry-run"
        },
    )


# ------------------------------ Gradio UI --------------------------------

EXAMPLES = [
    "¿Cuántos días tiene un cliente para solicitar una devolución por retracto?",
    "How many return requests were filed outside the withdrawal window allowed by our policy?",
    "Muéstrame la gráfica de ventas por mes",
    "Give me the details of order LT-102500",
]

WELCOME = (
    f"Internal support agent for {BRAND_NAME}. Ask about policies, "
    "live sales data, orders, charts or the weekly report — in "
    "English or Spanish (LARA replies in your language)."
)


BRAND_CSS = """<style>
.gradio-container{background:#eef2f6!important;max-width:940px!important;
  margin:0 auto!important;padding-top:18px!important;
  font-family:'Segoe UI',system-ui,-apple-system,sans-serif!important}
.gradio-container h3{color:#1a3c5e!important;font-size:1.25rem!important}
.gradio-container .prose p, .gradio-container p{color:#2b3a49!important}
.gradio-container .block{border-radius:12px!important;
  box-shadow:0 2px 10px rgba(18,41,63,.07)!important;border:none!important}
.gradio-container button{border-radius:10px!important;background:#fff!important;
  color:#1a3c5e!important;border:1px solid #c9d6e2!important;
  font-size:.85rem!important}
.gradio-container button:hover{background:#1a3c5e!important;color:#fff!important}
.gradio-container textarea{border-radius:10px!important;
  border:1px solid #c9d6e2!important}
.gradio-container small, .gradio-container small a{color:#5b6b7a!important}
#lara-header{justify-content:center!important}
#lara-header img{margin:0 auto!important}
.gradio-container [class*="chatbot"], .gradio-container [data-testid="chatbot"]{
  background:#ffffff!important}
.gradio-container [class*="chatbot"] *{color:#2b3a49!important}
.gradio-container [class*="message"]{background:#f4f7fa!important;
  border:1px solid #e2eaf1!important;border-radius:10px!important}
.gradio-container textarea, .gradio-container input[type="text"]{
  background:#ffffff!important;color:#22303d!important}
</style>"""


def chat_fn(message, history):
    history = history + [{"role": "user", "content": message}]
    try:
        reply = answer(message)
    except Exception as exc:
        reply = (
            "Lo siento, tuve un problema técnico procesando tu pregunta. "
            f"Intenta de nuevo en un momento. (detail: {str(exc)[:120]})"
        )
    history.append({"role": "assistant", "content": reply})
    m = CHART_RE.search(reply)
    if m:
        history.append({"role": "assistant", "content": gr.Image(value=m.group(1))})
    return history, ""


with gr.Blocks(title=f"{AGENT_NAME} · {BRAND_NAME}") as demo:
    gr.HTML(BRAND_CSS)
    with gr.Row(elem_id="lara-header"):
        gr.Image(str(LOGO), show_label=False, container=False, height=64)
    gr.Markdown(f"### {AGENT_NAME} — Internal Support Agent\n{WELCOME}")
    chatbot = gr.Chatbot(height=430, show_label=False)
    msg = gr.Textbox(
        placeholder="Type your question… (English or Spanish)",
        show_label=False,
        autofocus=True,
    )
    with gr.Row():
        btns = [gr.Button(e, size="sm") for e in EXAMPLES]
    clear = gr.Button("Clear chat", size="sm", variant="secondary")
    if _HAS_SPACES:
        _zg_btn = gr.Button(visible=False)
        _zg_btn.click(_zerogpu_noop)

    msg.submit(chat_fn, [msg, chatbot], [chatbot, msg])
    for b, e in zip(btns, EXAMPLES):
        b.click(lambda h, q=e: chat_fn(q, h), [chatbot], [chatbot, msg])
    clear.click(lambda: ([], ""), None, [chatbot, msg])
    gr.Markdown(
        f"<small>LARA · {BRAND_NAME} · [Weekly report]({REPORT_HREF}) · LangGraph · Gemini + Groq fallback · AI-generated — verify critical figures in the Weekly report (Methodology tab)</small>".replace(
            "{REPORT_HREF}", REPORT_HREF
        )
    )

app = gr.mount_gradio_app(app, demo, path="/")
