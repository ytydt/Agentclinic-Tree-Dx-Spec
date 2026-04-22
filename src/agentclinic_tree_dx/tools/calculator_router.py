"""Naive placeholder for quantitative probability estimation tools."""


def naive_calculator_router(query: str, state: object | None = None) -> dict:
    return {
        "tool": "naive_calculator",
        "query": query,
        "result": "placeholder_score",
        "note": "Naive LLM-style placeholder used for calculator path.",
    }
