"""Conservative symptom categories derived from errors and observed payloads."""
def classify(span, expected_documents=(), deadline=False):
    output = span.output if isinstance(span.output, dict) else {}
    error = span.error or ''
    if deadline:
        return 'latency_breach', 'execution_deadline', 'Execution deadline interrupted the agent'
    if span.span_type == 'tool_call':
        if error.startswith('TimeoutError:'):
            return 'tool_error', 'tool_timeout', 'Tool call timed out'
        if error.startswith('RecoverableStepError:') and 'invalid days_since_delivery' in error:
            return 'tool_error', 'malformed_tool', 'Order tool returned an invalid payload'
        return 'tool_error', 'tool_exception', 'Tool call raised an exception'
    if span.span_type == 'retrieval':
        documents = output.get('documents')
        if documents == []:
            return 'retrieval_failure', 'missing_documents', 'Retrieval returned no documents'
        if isinstance(documents, list) and expected_documents:
            ids = {d.get('id') for d in documents if isinstance(d, dict) and isinstance(d.get('id'), str)}
            if ids and not ids.intersection(expected_documents):
                return 'retrieval_failure', 'irrelevant_retrieval', 'Retrieved documents do not match the required evidence'
        return 'retrieval_failure', 'retrieval_exception', 'Retrieval raised an exception'
    if span.span_type == 'user_input' and error.startswith('ValidationError:'):
        return 'unknown', 'input_validation', 'Agent input failed validation'
    return 'unknown', 'unclassified_exception', 'Step raised an unclassified exception'
