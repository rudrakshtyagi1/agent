"""Strict, ordered boundary playback; never fall back to live fixtures."""
from copy import deepcopy
import json
from app.runtime.retry import RecoverableStepError


class ReplayMismatchError(ValueError):
    pass


class Playback:
    def __init__(self, snapshot):
        self.snapshot=deepcopy(snapshot)
        self.position=0

    def consume(self,target,payload,span):
        records=self.snapshot['records']
        if self.position>=len(records):
            raise ReplayMismatchError(f'No recorded response remains for {target}')
        record=records[self.position]
        if record['name']!=target or json.dumps(record['input'],sort_keys=True)!=json.dumps(payload,sort_keys=True):
            raise ReplayMismatchError(f'Recorded call does not match requested {target}')
        self.position+=1
        span.metadata.update({'replayed':True,'replay_source_span_id':record['span_id']})
        span.output=deepcopy(record['output'])
        if record['error']:
            span.metadata['recorded_error']=record['error']
            exception,message=record['error'].split(':',1)
            if exception=='TimeoutError':
                raise TimeoutError(message.strip())
            if exception=='RecoverableStepError':
                raise RecoverableStepError(message.strip())
            raise ReplayMismatchError('Unsupported recorded exception')
        return deepcopy(record['output'])

    def assert_consumed(self):
        if self.position!=len(self.snapshot['records']):
            raise ReplayMismatchError('Candidate finished before consuming all recorded responses')
