import asyncio,json
import pytest
from app import core


def test_classification_uses_terminal_error_not_model_text(tmp_path):
    events=tmp_path/'events.jsonl'
    events.write_text(json.dumps({'type':'agent_message','text':'servers are currently overloaded'}))
    assert not isinstance(core.codex_failure(tmp_path,1),core.TransientCodexError)
    events.write_text(json.dumps({'type':'turn.failed','error':{'message':'stream disconnected before completion: Our servers are currently overloaded. Please try again later.'}}))
    assert isinstance(core.codex_failure(tmp_path,1),core.TransientCodexError)
    events.write_text(events.read_text()+'\n'+json.dumps({'type':'turn.failed','error':{'message':'invalid_json_schema'}}))
    assert not isinstance(core.codex_failure(tmp_path,1),core.TransientCodexError)
    assert 'invalid_json_schema' in str(core.codex_failure(tmp_path,1))


@pytest.mark.parametrize('failures,expected_calls',[(1,2),(3,3)])
def test_bounded_transient_retry(monkeypatch,failures,expected_calls):
    calls=[];delays=[]
    async def once(*args):
        calls.append(True)
        if len(calls)<=failures:raise core.TransientCodexError('overloaded')
        return {'ok':True}
    async def sleep(delay):delays.append(delay)
    monkeypatch.setattr(core,'codex_once',once)
    monkeypatch.setattr(core.asyncio,'sleep',sleep)
    monkeypatch.setattr(core,'execute',lambda *args:None)
    if failures==3:
        with pytest.raises(core.TransientCodexError,match='2 次'):asyncio.run(core.codex({'id':'test'},'',{}))
    else:assert asyncio.run(core.codex({'id':'test'},'',{}))=={'ok':True}
    assert len(calls)==expected_calls
    assert delays==[30,60][:expected_calls-1]


@pytest.mark.parametrize('error',[RuntimeError('invalid_json_schema'),asyncio.CancelledError()])
def test_permanent_errors_and_cancellation_not_retried(monkeypatch,error):
    calls=[]
    async def once(*args):calls.append(True);raise error
    monkeypatch.setattr(core,'codex_once',once)
    with pytest.raises(type(error)):asyncio.run(core.codex({'id':'test'},'',{}))
    assert len(calls)==1


def test_previous_logs_are_preserved(tmp_path):
    for name in ('events.jsonl','stderr.log','result.json'):(tmp_path/name).write_text(name)
    core.archive_codex_logs(tmp_path)
    archives=list((tmp_path/'attempts').iterdir())
    assert len(archives)==1
    assert (archives[0]/'events.jsonl').read_text()=='events.jsonl'
    assert not (tmp_path/'result.json').exists()
