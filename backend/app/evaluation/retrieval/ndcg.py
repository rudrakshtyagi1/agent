"""Binary-relevance NDCG at the observed ranking depth, deduplicated by ID."""
from math import log2


def ndcg(retrieved: list[str], relevant: list[str]) -> float | None:
    if not relevant:
        return None
    ranking = list(dict.fromkeys(retrieved))
    ideal = sum(1 / log2(i + 2) for i in range(min(len(ranking), len(set(relevant)))))
    gain = sum(1 / log2(i + 2) for i, doc in enumerate(ranking) if doc in set(relevant))
    return gain / ideal if ideal else 0.0
