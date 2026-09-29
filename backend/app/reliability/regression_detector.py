"""Paired task outcomes with explicit missing-data denominators."""
from math import log, sqrt


def summarize(pairs):
    measured = [p for p in pairs if p['baseline_passed'] is not None and p['candidate_passed'] is not None and p['compatible']]
    n = len(measured)
    baseline = sum(p['baseline_passed'] for p in measured)
    candidate = sum(p['candidate_passed'] for p in measured)
    delta = (candidate-baseline)/n if n else None
    # For independent pairs with changes in [-1,1], Hoeffding's inequality.
    # These curated fixtures are not a random population sample; show the assumption.
    radius = sqrt(2*log(40)/n) if n else None
    latencies = [p['latency_delta_ms'] for p in measured if p['latency_delta_ms'] is not None]
    return {'total':len(pairs), 'measured_pairs':n, 'unmeasured_pairs':len(pairs)-n,
            'baseline_passes':baseline, 'candidate_passes':candidate,
            'baseline_success_rate':baseline/n if n else None,
            'candidate_success_rate':candidate/n if n else None,
            'success_rate_delta':delta,
            'regressions':sum(p['change']=='regressed' for p in pairs),
            'improvements':sum(p['change']=='improved' for p in pairs),
            'mean_latency_delta_ms':sum(latencies)/len(latencies) if latencies else None,
            'latency_measured_pairs':len(latencies),
            'uncertainty':{'lower':max(-1,delta-radius) if n else None,
                           'upper':min(1,delta+radius) if n else None,
                           'method':'95% Hoeffding bound for the mean paired binary change, assuming independent representative cases.',
                           'limitation':'This fixed diagnostic suite is not a random sample. The bound is illustrative, not evidence of production reliability.'}}


def compare_cases(cases):
    pairs=[]
    seen=set()
    for case in cases:
        if case['case_id'] in seen:
            raise ValueError('Duplicate comparison case ID')
        seen.add(case['case_id'])
        left,right=case['baseline'],case['candidate']
        a=next((r for r in left['evaluation']['results'] if r['evaluator']=='task_success'),None)
        b=next((r for r in right['evaluation']['results'] if r['evaluator']=='task_success'),None)
        compatible=bool(a and b and a['details'].get('expectations_sha256')
                        and a['details']['expectations_sha256']==b['details'].get('expectations_sha256')
                        and left['evaluation']['evaluator_version']==right['evaluation']['evaluator_version'])
        old=a['passed'] if a else None
        new=b['passed'] if b else None
        change='unmeasured' if not compatible or old is None or new is None else (
            'regressed' if old and not new else 'improved' if new and not old else 'unchanged_pass' if new else 'unchanged_fail')
        latency=(right['latency_ms']-left['latency_ms']) if left['latency_ms'] is not None and right['latency_ms'] is not None else None
        pairs.append({**case,'baseline_passed':old,'candidate_passed':new,'compatible':compatible,'change':change,'latency_delta_ms':latency})
    slices={tag:summarize([p for p in pairs if tag in p['tags']]) for tag in sorted({t for p in pairs for t in p['tags']})}
    return {'cases':pairs,'summary':summarize(pairs),'slices':slices}
