"""Small deterministic BM25 retriever; no embedding service or vector DB needed."""

from collections import Counter
import math
import re


def terms(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def search(documents, query, limit=3):
    if not documents:
        return []
    bags = [Counter(terms(d["title"] + " " + d["text"])) for d in documents]
    lengths = [sum(b.values()) for b in bags]
    average = sum(lengths) / len(lengths) or 1
    scores = []
    for doc, bag, length in zip(documents, bags, lengths):
        score = 0
        for term in set(terms(query)):
            frequency = bag[term]
            if not frequency:
                continue
            df = sum(term in b for b in bags)
            idf = math.log(1 + (len(bags) - df + 0.5) / (df + 0.5))
            if term in terms(doc["title"]):
                score += idf  # Explicit title-match boost for short policy headings.
            score += (
                idf
                * frequency
                * 2.5
                / (frequency + 1.5 * (0.25 + 0.75 * length / average))
            )
        if score > 0:
            scores.append({**doc, "score": round(score, 6)})
    return sorted(scores, key=lambda d: (-d["score"], d["id"]))[:limit]
