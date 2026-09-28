"""Reciprocal rank for one query (average across queries gives MRR)."""
def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float | None:
    if not relevant:
        return None
    return next((1 / rank for rank, doc in enumerate(dict.fromkeys(retrieved), 1)
                 if doc in set(relevant)), 0.0)
