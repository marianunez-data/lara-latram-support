"""Ingestion pipeline: PDFs -> section-aware chunks -> E5 embeddings -> Chroma.

Design note: naive fixed-size chunking blended adjacent policy sections and
measurably hurt cross-lingual retrieval. These documents have numbered
sections ("5. Plazos de solicitud", "5.1 Retracto..."), so we split on
section boundaries first, keep each section as a semantically pure unit,
prepend its heading to the chunk text (stronger embeddings), and only
char-split sections that exceed the chunk size.
"""

from __future__ import annotations

import re

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENTS_DIR,
    EMBEDDING_MODEL,
    VECTORSTORE_DIR,
)

DOC_TITLES = {
    "politica_reembolsos_devoluciones": "Política de Reembolsos y Devoluciones",
    "programa_afiliados": "Programa de Afiliados",
    "guia_tiempos_costos_envio": "Guía de Tiempos y Costos de Envío",
    "faq_metodos_pago": "FAQ de Métodos de Pago",
    "manual_garantia_productos": "Manual de Garantía de Productos",
}

# A section starts at a numbered heading like "5. Título" or "5.1 Subtítulo".
SECTION_SPLIT = re.compile(r"\n(?=\d{1,2}(?:\.\d{1,2})?\.?\s+[A-ZÁÉÍÓÚÑ¿«\"])")
HEADING_LINE = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?\.?\s+[^\n]{3,80})")
MIN_CHUNK_CHARS = 80  # drops table-of-contents fragments and page-footer noise


class E5Embeddings(HuggingFaceEmbeddings):
    """multilingual-e5 models expect 'query:'/'passage:' prefixes; skipping
    them silently degrades retrieval quality (see the model card)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return super().embed_query(f"query: {text}")


def get_embeddings() -> E5Embeddings:
    # device pinned to CPU: LARA needs no GPU, and ZeroGPU's CUDA-emulation
    # guard forbids cuda init outside @spaces.GPU functions.
    return E5Embeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def _section_chunks(pages: list, title: str) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[Document] = []
    current_section = "Introducción"

    for page in pages:
        page_no = page.metadata.get("page", 0) + 1
        for frag in SECTION_SPLIT.split(page.page_content):
            frag = frag.strip()
            if len(frag) < MIN_CHUNK_CHARS:
                continue
            m = HEADING_LINE.match(frag)
            if m:
                current_section = m.group(1).strip()
            body = frag if m else f"{current_section}\n{frag}"
            meta = {"title": title, "section": current_section, "page_label": page_no}
            if len(body) <= CHUNK_SIZE:
                chunks.append(Document(page_content=body, metadata=meta))
            else:
                for piece in splitter.split_text(body):
                    chunks.append(
                        Document(
                            page_content=(
                                piece
                                if piece.startswith(current_section)
                                else f"{current_section}\n{piece}"
                            ),
                            metadata=dict(meta),
                        )
                    )
    return chunks


def load_chunks() -> list[Document]:
    all_chunks: list[Document] = []
    for pdf in sorted(DOCUMENTS_DIR.glob("*.pdf")):
        pages = PyPDFLoader(str(pdf)).load()
        title = DOC_TITLES.get(pdf.stem, pdf.stem)
        all_chunks.extend(_section_chunks(pages, title))
    return all_chunks


def build_index() -> int:
    chunks = load_chunks()
    if not chunks:
        raise FileNotFoundError(f"No PDFs found in {DOCUMENTS_DIR}")
    Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(VECTORSTORE_DIR),
        collection_name="latram_policies",
    )
    return len(chunks)


if __name__ == "__main__":
    print(f"Index built: {build_index()} chunks -> {VECTORSTORE_DIR}")
