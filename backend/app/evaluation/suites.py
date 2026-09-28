"""Execute the small bundled, versioned dataset and persist its report."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.db.models.agent import AgentModel
from app.db.models.test_case import TestCaseModel
from app.db.models.run import RunModel
from app.db.models.evaluation_suite import EvaluationSuiteModel
from app.evaluation.engine import VERSION, aggregate
from app.evaluation.service import evaluate_run
from app.runtime.executor import execute_run
from app.schemas.test_case import TestCaseCreate

DATASET_PATH = Path(__file__).resolve().parents[3] / 'evals/datasets/golden/support_agent.json'


def dataset():
    return json.loads(DATASET_PATH.read_text())


async def run_suite(db):
    data = dataset()
    suite_id = uuid4()
    agent = AgentModel(id=uuid4(), name=f'Support evaluation {suite_id}', version='1.0.0',
                       endpoint='builtin://support', model='deterministic-template', status='active')
    db.add(agent)
    await db.flush()
    cases, all_results = [], []
    for source in data['cases']:
        payload = TestCaseCreate.model_validate(source)
        fields = payload.model_dump(exclude={'metadata'})
        fields['category'] = payload.category.value
        case = TestCaseModel(id=uuid4(), **fields, tc_metadata=payload.metadata)
        db.add(case)
        await db.flush()
        run = RunModel(id=uuid4(), agent_id=agent.id, agent_version=agent.version,
                       test_case_id=case.id, status='queued')
        db.add(run)
        await db.flush()
        await execute_run(db, run)
        evaluation = await evaluate_run(db, run.id)
        cases.append({'name': case.name, 'run_id': str(run.id), 'execution_status': run.status, **evaluation})
        all_results.extend(evaluation['results'])
    result = {'id': str(suite_id), 'dataset_version': data['version'],
              'dataset_sha256': hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(),
              'dataset_description': data['description'], 'evaluator_version': VERSION,
              'cases': cases, 'summary': aggregate(all_results)}
    db.add(EvaluationSuiteModel(id=suite_id, dataset_version=data['version'], report=result))
    await db.flush()
    return result
