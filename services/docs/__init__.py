# services/docs/__init__.py
"""Docs service — personal document RAG with ChromaDB.

Thin facade: DocsService lives here, RAGManager/VectorRAG are re-exported
from the canonical implementations in src/.
"""

from .service import DocsService, DocChunk, IndexResult
from src.rag_manager import RAGManager
from src.rag_vector import VectorRAG

__all__ = [
    "DocsService",
    "DocChunk",
    "IndexResult",
    "RAGManager",
    "VectorRAG",
]
