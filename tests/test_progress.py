import json
from app import core
from app.progress import progress_for


def job(**extra):
    return dict(id='j000000000001',kind='research',status='running',progress=None,**extra)


def test_progress_summarizes_tools_without_private_content(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    folder=tmp_path/'jobs'/'j000000000001';folder.mkdir(parents=True)
    events=[{'type':'item.completed','item':{'type':'agent_message','text':'PRIVATE REASONING'}},
            {'type':'item.started','item':{'type':'web_search','query':'PRIVATE QUERY'}},
            {'type':'item.completed','item':{'type':'command_execution','command':'SECRET COMMAND','aggregated_output':'SECRET OUTPUT'}}]
    (folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n{"partial":')
    p=progress_for(job())
    assert len(p['activity'])==2 and p['last_event']
    assert 'PRIVATE' not in json.dumps(p) and 'SECRET' not in json.dumps(p)


def test_terminal_status_overrides_old_live_stage():
    j=job();j.update(status='done',progress=json.dumps({'stage':'publish'}))
    p=progress_for(j)
    assert p['label']=='已完成' and p['index']==len(p['steps'])
    assert p['activity']==[]
    j['status']='queued'
    p=progress_for(j)
    assert p['label']=='排队等待 worker'


def test_retry_exposes_deadline_and_agent_stage():
    j=job();j['progress']=json.dumps({'stage':'retry','attempt':2,'retry_at':12345})
    p=progress_for(j)
    assert p['retry_at']==12345 and p['index']==1
    assert '第 2 次重试' in p['label']


def test_missing_log_still_reports_local_review_stage():
    j=job();j.update(kind='review',progress=json.dumps({'stage':'extract'}))
    p=progress_for(j)
    assert p['label']=='提取正文与页面' and p['index']==1


def test_deployment_queue_resumes_on_startup(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    core.init_db()
    core.execute("INSERT INTO jobs(id,status) VALUES('held','deploy_wait')")
    core.init_db()
    assert core.one('jobs','held')['status']=='queued'
