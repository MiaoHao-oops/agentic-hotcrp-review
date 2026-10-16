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


def test_delete_cancels_jobs_and_isolates_storage(isolated,monkeypatch):
    cid='c000000000002'; other='c000000000003'
    core.execute('INSERT INTO conferences VALUES(?,?,?,?,?,?,?,?)',(other,'Keep',3,'English','failed',None,None,time.time()))
    jid=worker.new_job(cid,'research'); keep=worker.new_job(other,'research')
    for parent, ident in [('documents',cid),('papers',cid),('jobs',jid),('jobs',keep)]:
        folder=isolated/parent/ident;folder.mkdir(parents=True);(folder/'file').write_text('test')
    cancelled=[];dropped=[]
    def drop(target):
        assert cancelled==[True]
        dropped.append(target)
    monkeypatch.setattr(worker,'drop_conference_database',drop)
    async def run():
        async def agent():
            try: await asyncio.Event().wait()
            finally: cancelled.append(True)
        task=asyncio.create_task(agent());worker.ACTIVE_TASKS[jid]=(cid,task)
        await asyncio.sleep(0)
        try: await asyncio.gather(worker.delete_conference(cid),worker.delete_conference(cid))
        finally: worker.ACTIVE_TASKS.pop(jid,None)
    asyncio.run(run())
    assert dropped==[cid]
    assert not core.rows('SELECT * FROM conferences WHERE id=?',(cid,))
    assert not (isolated/'jobs'/jid).exists()
    assert not (isolated/'documents'/cid).exists()
    assert (isolated/'jobs'/keep/'file').exists()
    assert core.one('conferences',other)


def test_delete_failure_can_retry(isolated,monkeypatch):
    cid='c000000000002'
    def broken(cid):raise RuntimeError('database unavailable')
    monkeypatch.setattr(worker,'drop_conference_database',broken)
    with pytest.raises(RuntimeError):asyncio.run(worker.delete_conference(cid))
    assert core.one('conferences',cid)['status']=='delete_failed'
    monkeypatch.setattr(worker,'drop_conference_database',lambda cid:None)
    asyncio.run(worker.delete_conference(cid))
    assert not core.rows('SELECT * FROM conferences')


def test_cancel_waits_for_mutating_thread():
    import threading
    started=threading.Event();release=threading.Event();finished=[]
    def mutate():
        started.set();release.wait(3);finished.append(True)
    async def run():
        task=asyncio.create_task(core.finish_blocking(mutate))
        await asyncio.to_thread(started.wait,3)
        task.cancel();await asyncio.sleep(.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished==[True]
    asyncio.run(run())


def test_dimension_scores_require_complete_valid_coverage():
    r=core.Review(score=3,confidence=2,summary='A complete synthetic review summary',strengths=['S'],weaknesses=['W'],questions=[],evidence=['p1'],limitations='L',recommendation='R',dimension_scores=[{'dimension':'Correctness','score':2,'justification':'Section 3 establishes the claim.'}])
    p={'dimensions':[{'name':'Correctness','labels':['Weak','Strong']}]}
    assert core.validate_dimensions(r,p)=={'s03':2}
    r.dimension_scores[0].score=3
    with pytest.raises(ValueError):core.validate_dimensions(r,p)
    r.dimension_scores=[]
    with pytest.raises(ValueError):core.validate_dimensions(r,p)


def test_research_requires_traceable_historical_scales():
    p=core.Profile(name='Test',summary='Test',topics=['Systems'],anonymity='blind',submission_instructions='Test',page_limit='Unknown',deadline_reference='Unknown',review_guidance='Test',score_labels=['Reject','Borderline','Accept'],rubric_status='Simulation',sources=[{'title':'Guide','url':'https://example.org/guide','supports':'Fixture'}],uncertainties=[],dimensions=[{'name':'Correctness','description':'Quality','labels':['Weak','Strong'],'basis':'historical','editions':['2025'],'source_urls':[],'rationale':'Fixture'}])
    with pytest.raises(ValueError,match='来源'):core.validate_research(p)
    p.dimensions[0].source_urls=['https://example.org/guide']
    core.validate_research(p)
    p.dimensions[0].source_urls=['https://unlisted.example/']
    with pytest.raises(ValueError,match='sources'):core.validate_research(p)


@pytest.mark.parametrize('model',[core.ReviewOutput,core.DetailedReview,core.ResearchProfile])
def test_codex_output_schemas_require_all_object_fields(model):
    def check(node):
        if isinstance(node,dict):
            if node.get('type')=='object':
                assert set(node['required'])==set(node['properties'])
                assert node['additionalProperties'] is False
            for value in node.values():check(value)
        elif isinstance(node,list):
            for value in node:check(value)
    check(model.model_json_schema())


def test_legacy_review_cache_remains_readable():
    cached=dict(score=3,confidence=2,summary='A complete synthetic review summary',strengths=['S'],weaknesses=['W'],questions=[],evidence=['p1'],limitations='L',recommendation='R')
    assert core.Review.model_validate(cached).dimension_scores==[]
    with pytest.raises(ValidationError):core.ReviewOutput.model_validate(cached)
    assert core.ReviewOutput.model_validate(dict(cached,dimension_scores=[])).dimension_scores==[]
