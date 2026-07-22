"""Policy retrieval tool: semantic search over the internal policy corpus."""

from __future__ import annotations

from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.tools import tool

from .config import RETRIEVER_K, VECTORSTORE_DIR
from .ingest import get_embeddings


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    return Chroma(
        persist_directory=str(VECTORSTORE_DIR),
        collection_name="latram_policies",
        embedding_function=get_embeddings(),
    )


def search(query: str, k: int = RETRIEVER_K) -> str:
    results = get_vectorstore().similarity_search(query, k=k)
    if not results:
        return "NO_RESULTS: nothing relevant found in the policy corpus."
    blocks = []
    for doc in results:
        title = doc.metadata.get("title", "Documento interno")
        page = doc.metadata.get("page_label", "?")
        blocks.append(f"[{title} — p. {page}]\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(blocks)


@tool
def search_policies(query: str) -> str:
    """Search Latram Shop's internal policy documents (refunds & returns,
    affiliate program, shipping times & costs, payment methods, product
    warranty). The corpus is written in Spanish, but you can query it in ANY
    language — retrieval is cross-lingual. Returns the most relevant passages,
    each preceded by [Document Title — p. N] so you can cite the source.
    Use this for every question about rules, policies, deadlines or processes.
    """
    return search(query)
