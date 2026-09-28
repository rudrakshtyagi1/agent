"""Counterexamples for each metric, not only perfect demo outputs."""
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from app.evaluation.engine import evaluate, aggregate
from app.evaluation.retrieval.recall import recall
from app.evaluation.retrieval.mrr import reciprocal_rank
from app.evaluation.retrieval.ndcg import ndcg


def span(kind, name='', output=None, metadata=None, error=None):
    return NS(id=uuid4(), span_type=kind, name=name, output=output, span_metadata=metadata or {}, error=error)


def score(spans, expected=None, **case):
    results = evaluate(NS(status='completed', total_latency_ms=50), spans,
                       {'metadata': {'evaluation': {'expected_output': expected or {}}}, **case})
    return {r['evaluator']: r for r in results}


def test_retrieval_rankings_and_missing_labels():
    ranking = ['noise', 'a', 'a', 'b']
    assert recall(ranking, ['a', 'b', 'c']) == pytest.approx(2/3)
    assert reciprocal_rank(ranking, ['b']) == pytest.approx(1/3)
    assert 0 < ndcg(ranking, ['a','b']) < 1
    assert ndcg(['a','b'], ['a','b']) == 1
    for metric in (recall, reciprocal_rank, ndcg):
        assert metric([], ['a']) == 0
        assert metric(['a'], []) is None


def test_task_success_is_not_execution_success_and_types_are_strict():
    results = score([span('final_response', output={'eligible': 1})], {'eligible': True})
    assert results['execution_success']['passed'] is True
    assert results['task_success']['passed'] is False
    assert score([])['task_success']['score'] is None
    assert score([], {'eligible': True})['task_success']['score'] == 0


def test_tool_constraints_and_hallucinated_citation():
    results = score([span('tool_call', 'delete_account'), span('final_response', output={'citations':['invented']})],
                    expected_tools=['lookup_order'], forbidden_tools=['delete_account'])
    assert results['tool_correctness']['passed'] is False
    assert results['tool_correctness']['details']['missing_tools'] == ['lookup_order']
    assert results['citation_validity']['score'] == 0


def test_groundedness_detects_wrong_answer_despite_valid_citation():
    spans = [span('retrieval', output={'documents':[{'id':'refund-policy-v1','text':'Orders delivered within 30 days are eligible for a refund.'}]}),
             span('tool_call', 'lookup_order', {'order_id':'ORD-1001','days_since_delivery':12}),
             span('final_response', output={'eligible':False, 'answer':'No refund', 'citations':['refund-policy-v1']})]
    results = score(spans)
    assert results['citation_validity']['score'] == 1
    assert results['groundedness']['score'] == 0


def test_tokens_missing_partial_and_simulated_are_not_zero():
    real = span('model', metadata={'usage':{'input_tokens':10,'output_tokens':5}})
    assert score([real])['token_usage']['details']['value'] == 15
    assert score([real,span('model')])['token_usage']['details']['value'] is None
    simulated = span('model', metadata={'simulated':True,'usage':{'input_tokens':10,'output_tokens':5}})
    assert score([simulated])['token_usage']['details']['value'] is None
    assert score([])['token_usage']['details']['value'] is None


def test_aggregate_uses_per_metric_denominators():
    measured = list(score([span('final_response',output={'eligible':True})], {'eligible':True}).values())
    missing = list(score([]).values())
    summary = aggregate(measured+missing)
    assert summary['task_success']['mean_score'] == 1
    assert summary['task_success']['scored'] == 1
    assert summary['task_success']['unavailable'] == 1
    assert summary['latency']['mean_value'] == 50
    assert summary['latency']['judged'] == 0
