"""Report knowledge-base extraction and retrieval for the assistant."""

from issuedoctor.rag.knowledge import INDEX_VERSION, AssistantKnowledgeBuilder
from issuedoctor.rag.retrieval import RetrievalResult, retrieve_chunks

__all__ = [
    "AssistantKnowledgeBuilder",
    "INDEX_VERSION",
    "RetrievalResult",
    "retrieve_chunks",
]
