"""Validated, transactional trace persistence."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.trace import TraceSpanModel
from app.schemas.trace import TraceResponse, SpanResponse


def span_response(row: TraceSpanModel) -> SpanResponse:
    fields = {name: getattr(row, name) for name in SpanResponse.model_fields if name != "metadata"}
    return SpanResponse(**fields, metadata=row.span_metadata)


async def save_trace(db: AsyncSession, trace: TraceResponse) -> None:
    # Preorder insertion ensures parents exist before foreign-key checks.
    seen = set()
    for span in trace.spans:
        if span.run_id != trace.run_id or span.trace_id != trace.trace_id:
            raise ValueError("Span does not belong to this run/trace")
        if span.id in seen or (span.parent_span_id is not None and span.parent_span_id not in seen):
            raise ValueError("Duplicate span or invalid parent ordering")
        seen.add(span.id)
    for span in trace.spans:
        fields = span.model_dump(exclude={"metadata"})
        fields["span_type"] = span.span_type.value
        db.add(TraceSpanModel(**fields, span_metadata=span.metadata))
        await db.flush()
