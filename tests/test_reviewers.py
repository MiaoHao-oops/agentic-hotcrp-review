import json
from app import core
from app.reviewers import sample_persona


def test_panel_has_distinct_backgrounds_and_stable_retries():
    run={'id':'r-example'}; conference={'topics':['Operating systems']}
    panel=[sample_persona(run,i,conference) for i in range(5)]
    assert len({p['archetype'] for p in panel})==5
    assert len({p['calibration'] for p in panel[:3]})==3
    assert panel==[sample_persona(run,i,conference) for i in range(5)]
    assert panel!=[sample_persona({'id':'r-other'},i,conference) for i in range(5)]


def test_saved_persona_drives_prompt_without_author_leakage():
    c={'profile':json.dumps({'anonymity':'blind','topics':['Systems'],'score_labels':['Reject','Borderline','Accept']}),'language':'English'}
    run={'id':'r-test','snapshot':json.dumps({'title':'Paper','authors':['SECRET AUTHOR'],'abstract':'Claim'})}
    persona=sample_persona(run,0,json.loads(c['profile']))
    persona['name']='Persisted persona sentinel'
    prompt=core.review_prompt(c,run,0,[],persona)
    assert 'Persisted persona sentinel' in prompt
    assert 'SECRET AUTHOR' not in prompt
    assert 'artificial disagreement' in prompt
    assert 'what evidence would change' in prompt


def test_jobs_persona_migration_preserves_rows(tmp_path,monkeypatch):
    monkeypatch.setattr(core,'DATA',tmp_path)
    with core.db() as db:
        db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,cid TEXT,run_id TEXT,kind TEXT,reviewer INTEGER,status TEXT,result TEXT,error TEXT,created REAL,started REAL,finished REAL)')
        db.execute("INSERT INTO jobs(id,status,result) VALUES('legacy','done','{}')")
    core.init_db();core.init_db()
    job=core.one('jobs','legacy')
    assert job['persona'] is None and job['result']=='{}' and job['status']=='done'


def test_public_background_matching_uses_content_not_author():
    conference={'public_pc':[
        {'name':'A','research_areas':['distributed storage']},
        {'name':'B','research_areas':['computer vision']},
        {'name':'C','research_areas':['program verification']} ]}
    run={'id':'r-match','snapshot':json.dumps({'title':'Distributed storage','authors':['B']})}
    panel=[sample_persona(run,i,conference) for i in range(3)]
    assert panel[0]['public_background']['name']=='A'
    assert len({p['public_background']['name'] for p in panel})==3
    run['snapshot']=json.dumps({'title':'Distributed storage','authors':['A']})
    assert sample_persona(run,0,conference)==panel[0]
    run['snapshot']=json.dumps({'title':'Computer vision'})
    assert sample_persona(run,0,conference)['public_background']['name']=='B'


def test_dynamic_brief_changes_with_paper_and_lens():
    from app.reviewers import paper_focus
    run={'id':'r-focus','snapshot':json.dumps({'title':'Paper A','abstract':'Claim A'})}
    a=sample_persona(run,0,{})
    b=sample_persona(run,1,{})
    assert paper_focus(run,a)['inspection_lens']!=paper_focus(run,b)['inspection_lens']
    original=paper_focus(run,a)
    run['snapshot']=json.dumps({'title':'Paper B','abstract':'Claim B'})
    assert paper_focus(run,a)!=original
