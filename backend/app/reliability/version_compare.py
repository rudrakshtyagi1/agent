"""Run both executable fixture versions on the same immutable labeled cases."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from app.db.models.agent import AgentModel
from app.db.models.test_case import TestCaseModel
from app.db.models.regression import RegressionReportModel
from app.chaos.campaigns import execute_case
from app.schemas.chaos import ExecutionOptions,FaultConfig,RetryPolicy
from app.schemas.regression import ComparisonRequest
from app.reliability.regression_detector import compare_cases
from app.reliability.release_gate import evaluate_gate
from app.target_agents import support

DATASET_PATH=Path(__file__).resolve().parents[3]/'evals/datasets/regression/support_release.json'
VERSION='agentguard-comparison/1.0.0'


async def run_comparison(db,request:ComparisonRequest):
    dataset=json.loads(DATASET_PATH.read_text())
    report_id=uuid4()
    agents=[]
    for role,version in [('baseline',request.baseline_version),('candidate',request.candidate_version)]:
        agent=AgentModel(id=uuid4(),name=f'Release {role} {report_id}',version=version,
                         endpoint=support.ENDPOINT,model='deterministic-template',status='active')
        db.add(agent)
        agents.append(agent)
    await db.flush()
    cases=[]
    for index,source in enumerate(dataset['cases']):
        case=TestCaseModel(id=uuid4(),name=source['name'],category='regression',
                          input={'order_id':source['order_id'],'scenario':'success'},
                          expected_tools=['lookup_order'],forbidden_tools=['issue_refund'],
                          expected_documents=['refund-policy-v1'],tags=source['tags'],
                          tc_metadata={'evaluation':{'expected_output':{'eligible':source['eligible'],'citations':['refund-policy-v1']}}})
        db.add(case)
        await db.flush()
        results={}
        # Alternate execution order to reduce a fixed baseline-first timing bias.
        for role,agent in (list(zip(['baseline','candidate'],agents))[::1 if index%2==0 else -1]):
            options=ExecutionOptions(retry=RetryPolicy(max_attempts=support.VERSIONS[agent.version]['default_attempts']),
                                     fault=FaultConfig(kind=source['fault']) if source.get('fault') else None)
            results[role]=await execute_case(db,agent,case,options)
        cases.append({'case_id':source['id'],'name':source['name'],'tags':source['tags'],**results})
    compared=compare_cases(cases)
    report={'id':str(report_id),'comparison_version':VERSION,'dataset_version':dataset['version'],
            'dataset_sha256':hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest(),
            'request':request.model_dump(),'runtime_version':support.RUNTIME_VERSION,'provenance':support.PROVENANCE,
            'version_configs':{v:support.VERSIONS[v] for v in (request.baseline_version,request.candidate_version)},
            **compared,'gate':evaluate_gate(compared['summary'],request.gate),
            'limitations':['Fixed diagnostic cases, not a held-out production benchmark.',
                           'Slice memberships overlap; do not sum slice totals.',
                           'Timing is a single observation per case, not a stable latency estimate.',
                           'The deliberately faulty version exists only to demonstrate blocked releases.']}
    db.add(RegressionReportModel(id=report_id,report=report))
    await db.flush()
    return report
