# DEPLOY.md — LARA on Hugging Face Spaces (Docker, free tier)

Public URL in ~20 minutes, no credit card, no server. This runbook is
reproducible by anyone cloning the repo.

## 0 · Pre-flight (local)

- [ ] Sabotage rows `LT-9990xx` deleted from the Google Sheet; `python -m src.app.verify_report` back to clean figures.
- [ ] `uvicorn src.app.api:app --port 7860` works locally (chat + `/health` + `/report`).
- [ ] A fresh `data/reports/weekly_report.html` exists (`python -m src.app.weekly_report --dry-run`) so `/report` serves on day one.

## 1 · Create the Space

1. huggingface.co → sign in → **New Space**.
2. Name: `lara-latram-support` · License: `mit` · **SDK: Gradio → template Blank** (July 2026: HF moved the Docker SDK to paid plans; the Gradio SDK stays free and runs our app identically via app.py) · Hardware: the free option shown (ZeroGPU Free — our app is CPU-only and runs fine on it) · Visibility: Public.

## 2 · Upload the project

**Method A — web UI (simplest):** Space → *Files* → *Add file → Upload files*, drag these preserving folders:

```
app.py               <- Spaces entrypoint (launches the FastAPI+Gradio stack)
README.md            <- this is SPACE_README.md, RENAMED (front-matter
requirements.txt        sdk: gradio / app_file: app.py is what HF reads)
src/                 <- whole folder
assets/              <- logo
data/documents/      <- the 5 policy PDFs (index builds from these at runtime)
data/sales/orders.csv     <- local fallback for the live Sheet
data/reports/weekly_report.html   <- pre-generated, powers /report
```

**NEVER upload:** `.env` (secrets live in HF Secrets), `chroma_db/`, `.venv/`, `data/charts|logs|traces_backup`, `dev-tools/`, `notebooks/`.

**Method B — git (alternative):** `git clone https://huggingface.co/spaces/<user>/lara-latram-support`, copy files in, `git push` (password = an HF *write* token from Settings → Access Tokens).

## 3 · Secrets & variables (Settings → Variables and secrets)

As **Secrets** (hidden): `GOOGLE_API_KEY`, `GROQ_API_KEY`, `LANGSMITH_API_KEY`.
As **Variables** (plain): `GEMINI_MODEL=gemini-3.5-flash`, `GROQ_MODEL=openai/gpt-oss-120b`, `ORDERS_SOURCE_URL=<your Sheet export URL>`, `LANGSMITH_TRACING=true`, `LANGSMITH_PROJECT=latram-support-agent`.

(Email vars are NOT needed here — the weekly report runs on GitHub Actions, not on the Space.)

## 4 · Build & boot expectations (free tier honesty)

- First build: **5–10 min** (pip installs torch & friends). Watch the *Logs* tab.
- The Dockerfile is NOT used by the Gradio SDK — it stays in the repo for Render/Cloud Run/AWS/Azure portability (section 7).
- `/health` responds the moment the app boots (lazy design).
- **First question: 2–4 min** — downloads the multilingual-E5 embedding model and builds the Chroma index (ephemeral disk → rebuilt on each cold boot, by design). After that: normal free-tier latency.
- Sleep: free Spaces pause after ~48h without visits; any visit wakes them (~1–2 min). They are never deleted.

## 5 · Post-deploy checklist

- [ ] `https://<user>-lara-latram-support.hf.space/health` → JSON with model names.
- [ ] Ask a question in the chat → answer with citation; watch the trace land in LangSmith *from the cloud*.
- [ ] Ask for a chart → renders inline.
- [ ] `/report` → interactive weekly report.
- [ ] Put the direct URL in `.env` (`LARA_URL=`) **and** in GitHub → Settings → Secrets (`LARA_URL`) → next Monday's email ships with the "Ask LARA" button live.

## 6 · Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Build failed | *Logs* tab shows the pip/COPY error; usually a missing file or requirements typo. |
| "No LLM credentials found" on first ask | `GOOGLE_API_KEY`/`GROQ_API_KEY` secret missing → add → *Restart Space*. |
| 404 model on ask | Model variable stale (providers rotate models) → update `GEMINI_MODEL`/`GROQ_MODEL` → restart. |
| First answer very slow | Normal (model download + index build). Subsequent ones are fine. |
| App asleep | Visit the URL; it wakes alone. |

## 7 · Portability note

The same `Dockerfile` deploys unchanged to Render, Cloud Run, AWS App
Runner/Fargate, Azure Container Apps or SAP BTP Kyma — swap this page's
"Secrets" step for the platform's secret manager. Build once, deploy anywhere.
