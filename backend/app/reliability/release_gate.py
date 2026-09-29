"""Release checks fail closed; missing measurements cannot silently pass."""
from app.schemas.regression import GatePolicy

VERSION='agentguard-release-gate/1.0.0'


def evaluate_gate(summary, policy: GatePolicy):
    checks=[]
    def check(name,actual,threshold,passed,required=True):
        checks.append({'name':name,'actual':actual,'threshold':threshold,'passed':passed,'required':required})
    complete=summary['total']>0 and summary['unmeasured_pairs']==0
    check('complete_task_measurements',summary['measured_pairs'],summary['total'],complete)
    check('minimum_cases',summary['measured_pairs'],policy.min_measured_cases,summary['measured_pairs']>=policy.min_measured_cases)
    check('regression_budget',summary['regressions'],policy.max_regressions,summary['regressions']<=policy.max_regressions)
    rate=summary['candidate_success_rate']
    check('candidate_task_success_rate',rate,policy.min_task_success_rate,rate is not None and rate>=policy.min_task_success_rate)
    if policy.max_mean_latency_increase_ms is not None:
        value=summary['mean_latency_delta_ms']
        latency_complete=summary['latency_measured_pairs']==summary['total'] and summary['total']>0
        check('complete_latency_measurements',summary['latency_measured_pairs'],summary['total'],latency_complete)
        check('mean_latency_increase_ms',value,policy.max_mean_latency_increase_ms,
              value is not None and value<=policy.max_mean_latency_increase_ms)
    passed=all(c['passed'] for c in checks)
    incomplete=not complete or summary['measured_pairs']<policy.min_measured_cases or any(c['name']=='complete_latency_measurements' and not c['passed'] for c in checks)
    return {'version':VERSION,'policy':policy.model_dump(),'passed':passed,
            'status':'passed' if passed else 'blocked' if incomplete else 'failed','checks':checks}
