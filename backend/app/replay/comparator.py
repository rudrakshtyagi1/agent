"""Create an isolated replay run using frozen source input and boundary results."""
from uuid import uuid4
from fastapi import HTTPException
from app.db.models.run import RunModel
from app.db.models.agent import AgentModel
from app.db.models.test_case import TestCaseModel
from app.db.repositories.trace_repo import TraceSpanRepository
from app.schemas.test_case import TestCaseCreate
from app.runtime.executor import execute_run
from app.evaluation.service import evaluate_run
from app.replay.snapshot import snapshot_trace
from app.replay.replay_engine import Playback
from app.target_agents import support


async def replay_run(db,source_id,candidate_version):
    source=await db.get(RunModel,source_id)
    if source is None:
        raise HTTPException(404,'Source run not found')
    if source.status not in ('completed','failed'):
        raise HTTPException(409,'Replay requires a finished source run')
    source_agent=await db.get(AgentModel,source.agent_id)
    if source_agent is None or source_agent.endpoint!=support.ENDPOINT:
        raise HTTPException(409,'Only built-in support traces support playback')
    spans=await TraceSpanRepository(db).list_by_run(source_id)
    snapshot=snapshot_trace(source_id,spans)
    contract=TestCaseCreate.model_validate(snapshot['case'])
    fields=contract.model_dump(exclude={'metadata'})
    fields['category']=contract.category.value
    case=TestCaseModel(id=uuid4(),**fields,tc_metadata=contract.metadata)
    agent=AgentModel(id=uuid4(),name=f'Playback {uuid4()}',version=candidate_version,
                     endpoint=support.ENDPOINT,model='deterministic-template',status='active')
    db.add_all([case,agent])
    await db.flush()
    run=RunModel(id=uuid4(),agent_id=agent.id,agent_version=agent.version,test_case_id=case.id,status='queued')
    db.add(run)
    await db.flush()
    playback=Playback(snapshot)
    await execute_run(db,run,playback=playback)
    evaluation=await evaluate_run(db,run.id)
    replay_spans=await TraceSpanRepository(db).list_by_run(run.id)
    before=next((s.output for s in reversed(spans) if s.span_type=='final_response' and not s.error),None)
    after=next((s.output for s in reversed(replay_spans) if s.span_type=='final_response' and not s.error),None)
    return {'run_id':str(run.id),'source_run_id':str(source.id),'candidate_version':candidate_version,
            'status':run.status,'error':run.error,'mode':'recorded_boundary_playback',
            'snapshot_sha256':snapshot['sha256'],'recorded_calls':len(snapshot['records']),
            'consumed_calls':playback.position,'source_output':before,'candidate_output':after,
            'output_changed':before!=after,'evaluation':evaluation,
            'limitation':'Only retrieval/tool responses are replayed. Candidate answer generation runs again; recorded timing is not reproduced. No fallback to unrecorded calls.'}
