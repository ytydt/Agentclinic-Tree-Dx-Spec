"""Naive placeholder for external knowledge/tool invocation."""


def naive_knowledge_router(query: str) -> dict:
    return {
        "tool": "naive_knowledge_lookup",
        "query": query,
        "summary": "Placeholder external context from naive LLM interaction.",
    }
