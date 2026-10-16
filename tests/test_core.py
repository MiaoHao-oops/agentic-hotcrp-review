import asyncio, json, time
import pytest
from pydantic import ValidationError
from app import core, worker

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    monkeypatch.setattr(worker,'DATA',tmp_path)
    core.init_db()
    core.execute('INSERT INTO conferences VALUES(?,?,?,?,?,?,?,?)',('c000000000002','Test',3,'English','ready','{}',None,time.time()))
    return tmp_path


def test_fingerprint_ignores_reviews_not_submission():
    p={'pid':1,'title':'Title','abstract':'A','submission':{'hash':'abc'},'sim_reviews':[]}
    q=dict(p,sim_reviews=[{'score':5}],sim_pdf_path='/private/path',sim_review_form={})
    assert core.fingerprint(p)==core.fingerprint(q)
    assert core.fingerprint(p)!=core.fingerprint(dict(p,abstract='Changed'))
    assert core.fingerprint(p)!=core.fingerprint(dict(p,submission={'hash':'new'}))


def test_scores_reject_invalid_outputs():
    with pytest.raises(ValidationError):
        core.Review.model_validate({'score':11})


def test_poll_skips_drafts_and_deduplicates_versions(isolated,monkeypatch):
    paper={'pid':1,'title':'Paper','submitted':False,'abstract':'Text'}
    async def fake_bridge(*args): return [paper]
    monkeypatch.setattr(worker,'bridge',fake_bridge)
    asyncio.run(worker.poll_submissions())
    assert not core.rows('SELECT * FROM runs')
    paper['submitted']=True
    asyncio.run(worker.poll_submissions())
    asyncio.run(worker.poll_submissions())
    assert len(core.rows('SELECT * FROM runs'))==1
    assert len(core.rows('SELECT * FROM jobs'))==3
    paper['abstract']='Updated'
    asyncio.run(worker.poll_submissions())
    assert len(core.rows('SELECT * FROM runs'))==2
    assert len(core.rows("SELECT * FROM jobs WHERE status='queued'"))==3
    assert len(core.rows("SELECT * FROM jobs WHERE status='superseded'"))==3


def test_interrupted_jobs_become_retryable(isolated):
    j=worker.new_job('c000000000002','research')
    core.execute("UPDATE jobs SET status='running' WHERE id=?",(j,))
    core.init_db()
    assert core.one('jobs',j)['status']=='failed'


def test_withdrawn_paper_never_launches_jobs(isolated,monkeypatch):
    async def fake_bridge(*args):return [{'pid':1,'title':'P','submitted':True,'withdrawn':True}]
    monkeypatch.setattr(worker,'bridge',fake_bridge)
    asyncio.run(worker.poll_submissions())
    assert not core.rows('SELECT * FROM jobs')


def test_partial_failure_status(isolated):
    core.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('r1','c000000000002',1,'hash','Paper','reviewing','{}',None,time.time()))
    for state in ['done','failed','done']:
        j=worker.new_job('c000000000002','review','r1',0)
        core.execute('UPDATE jobs SET status=? WHERE id=?',(state,j))
    core.execute("UPDATE conferences SET status='failed'")
    asyncio.run(worker.poll_submissions())
    assert core.one('runs','r1')['status']=='failed'


def test_reverting_to_old_version_restores_cached_run(isolated,monkeypatch):
    paper={'pid':1,'title':'Paper','submitted':True,'abstract':'Original'}
    async def fake_bridge(*args):return [paper]
    monkeypatch.setattr(worker,'bridge',fake_bridge)
    asyncio.run(worker.poll_submissions())
    original=core.rows('SELECT id FROM runs')[0]['id']
    core.execute("UPDATE jobs SET status='done',result='{}'")
    paper['abstract']='Changed'
    asyncio.run(worker.poll_submissions())
    paper['abstract']='Original'
    asyncio.run(worker.poll_submissions())
    assert len(core.rows('SELECT * FROM runs'))==2
    assert core.one('runs',original)['status']=='reviewing'
    assert all(j['status']=='queued' and j['result']=='{}' for j in core.rows('SELECT * FROM jobs WHERE run_id=?',(original,)))


def test_score_form_mismatch_rejected():
    paper={'sim_review_form':[{'id':'s01','order':1,'values':['Accept','Reject']} ]}
    with pytest.raises(ValueError,match='评分表'):
        worker.validate_form(paper,{'score_labels':['Reject','Accept']})
