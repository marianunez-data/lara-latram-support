"""Central configuration for the Latram Shop support agent.

Everything tunable lives here: change the brand or agent name once and the
whole project follows.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Identity -----------------------------------------------------------------
BRAND_NAME = "Latram Shop"
AGENT_NAME = os.getenv("AGENT_NAME", "LARA")  # Latram Assistant for Retrieval & Analytics

# --- Paths ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = BASE_DIR / "data" / "documents"
SALES_CSV = BASE_DIR / "data" / "sales" / "orders.csv"
VECTORSTORE_DIR = BASE_DIR / "chroma_db"

# --- Models (all free tiers) ----------------------------------------------------
# Primary LLM: Google Gemini (free tier, multimodal-ready).
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
# Fallback LLM: Groq (free tier, very fast). Used if Gemini is unavailable.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Local multilingual embeddings: no API dependency on the critical path.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")

# --- Data source ------------------------------------------------------------
# Optional LIVE source for orders: a Google Sheet exported as CSV
# (https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>).
# If unset or unreachable, the agent falls back to the local snapshot.
ORDERS_SOURCE_URL = os.getenv("ORDERS_SOURCE_URL", "")
ORDERS_CACHE_TTL = int(os.getenv("ORDERS_CACHE_TTL", "60"))  # seconds

# --- Retrieval ------------------------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
RETRIEVER_K = int(os.getenv("RETRIEVER_K", "5"))

# Optional Cohere Rerank stage (free trial key). Degrades gracefully if off.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "rerank-multilingual-v3.0")
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "4"))
RETRIEVER_K_BEFORE_RERANK = int(os.getenv("RETRIEVER_K_BEFORE_RERANK", "12"))

# --- API keys (never hardcode; see .env.example) ---------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# --- Logs -------------------------------------------------------------------
QUESTIONS_LOG = BASE_DIR / "data" / "logs" / "questions.jsonl"
