"""Observed trace features; injection labels are never classification inputs."""
def descendants(span, spans):
    pending, seen = [span.id], set()
    while pending:
        parent = pending.pop()
        for child in spans:
            if child.parent_span_id == parent and child.id not in seen:
                seen.add(child.id)
                pending.append(child.id)
    return [s for s in spans if s.id in seen]


def error_origins(spans):
    errors = [s for s in spans if s.error]
    deadlines = [s for s in errors if s.parent_span_id is None and s.error.startswith('TimeoutError:')
                 and any(c.error and c.error.startswith('CancelledError:') for c in descendants(s, spans))]
    origins = []
    for span in errors:
        children = descendants(span, spans)
        if deadlines and span.error.startswith('CancelledError:'):
            continue
        if any(s.error == span.error for s in children):
            continue  # Same exception propagated to a parent, not a second cause.
        origins.append(span)
    return sorted(origins, key=lambda s: (s.ended_at or s.started_at, str(s.id))), deadlines
