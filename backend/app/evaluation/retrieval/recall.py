"""Recall over unique relevant document IDs; unlabeled queries are undefined."""
def recall(retrieved: list[str], relevant: list[str]) -> float | None:
    expected = set(relevant)
    return len(set(retrieved) & expected) / len(expected) if expected else None
