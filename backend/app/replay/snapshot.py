"""Capture ordered recorded boundary responses and immutable provenance."""
import hashlib
import json
from fastapi import HTTPException

VERSION='agentguard-playback/1.0.0'


def snapshot_trace(run_id,spans):
    roots=[s for s in spans if s.parent_span_id is None]
    case=roots[0].span_metadata.get('test_case_snapshot') if roots else None
    if not isinstance(case,dict):
        raise HTTPException(409,'Source trace has no frozen test-case snapshot')
    records=[]
    for s in spans:
        if s.span_type not in ('retrieval','tool_call'):
            continue
        if s.name not in ('retrieve_refund_policy','lookup_order'):
            raise HTTPException(409,'Source trace contains an unsupported replay boundary')
        if s.error and s.error.split(':',1)[0] not in ('TimeoutError','RecoverableStepError'):
            raise HTTPException(409,'Source trace contains an unsupported recorded exception')
        if s.ended_at is None or (not s.error and not isinstance(s.output,dict)):
            raise HTTPException(409,'Source response is incomplete')
        records.append({'span_id':str(s.id),'name':s.name,'input':s.input,'output':s.output,'error':s.error})
    if not records:
        raise HTTPException(409,'Source trace contains no recorded boundary responses')
    result={'version':VERSION,'source_run_id':str(run_id),'source_trace_id':str(roots[0].trace_id),
            'case':case,'records':records}
    result['sha256']=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return result
