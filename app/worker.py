import asyncio, json, shutil, time
from pathlib import Path
from pypdf import PdfReader
from .core import *


def new_job(cid, kind, run_id=None, reviewer=None):
    id = uid('j')
    execute('INSERT INTO jobs(id,cid,run_id,kind,reviewer,status,created) VALUES(?,?,?,?,?,?,?)',
            (id,cid,run_id,kind,reviewer,'queued',time.time()))
    return id


def extract_pdf(path, dest):
    reader = PdfReader(path)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 80:
        raise ValueError('只支持未加密、1–80 页的 PDF。')
    chunks = []
    body_chars = 0
    for n, page in enumerate(reader.pages):
        content = page.extract_text() or ''
        body_chars += len(content.strip())
        chunks.append(f'\n\n--- PDF PAGE {n+1} ---\n' + content)
    text = ''.join(chunks)
    if body_chars < 300:
        raise ValueError('PDF 无法提取足够正文（可能为扫描件）；请上传含文本层的 PDF。')
    if len(text) > 300_000:
        raise ValueError('论文正文超过当前 300,000 字符上限，未截断送审；请精简文件。')
    (dest / 'paper.txt').write_text(text)
    return len(reader.pages)


def validate_form(paper, profile):
    fields = {f['id']:f for f in paper['sim_review_form']}
    for fid, expected in [('s01', profile['score_labels']), ('s02', ['Low','Medium','High','Very high'])]:
        f = fields.get(fid, {})
        if f.get('values') != expected or not f.get('order') or f.get('symbols', list(range(1,len(expected)+1))) != list(range(1,len(expected)+1)):
            raise ValueError('HotCRP 评分表已被修改，与会议模拟配置不一致；请恢复评分表后重试。')
    if any(not fields.get(fid, {}).get('order') for fid in ['t01','t02']):
        raise ValueError('HotCRP 审稿文本字段缺失。')


async def process(job):
    try:
        c = one('conferences', job['cid'])
        if job['kind'] == 'research':
            execute("UPDATE conferences SET status='researching',error=NULL WHERE id=?", (c['id'],))
            raw = json.loads(job['result']) if job['result'] else await codex(job, research_prompt(c), Profile.model_json_schema())
            p = Profile.model_validate(raw)
            for source in p.sources:
                if not source.url.startswith(('https://','http://')):
                    raise ValueError('调查来源必须是 HTTP(S) URL')
            execute('UPDATE jobs SET result=? WHERE id=?',(p.model_dump_json(),job['id']))
            execute('UPDATE conferences SET profile=? WHERE id=?',(p.model_dump_json(),c['id']))
            await asyncio.to_thread(create_database, c['id'])
            await bridge(c['id'],'setup',settings_for(p.model_dump()))
            execute("UPDATE conferences SET status='ready',error=NULL WHERE id=?", (c['id'],))
        else:
            run = one('runs',job['run_id'])
            paper = (await bridge(c['id'],'paper',{'pid':run['pid']}))[0]
            if not paper.get('submitted') or paper.get('withdrawn') or fingerprint(paper) != run['fingerprint']:
                execute("UPDATE jobs SET status='superseded',finished=? WHERE id=?",(time.time(),job['id']))
                return
            validate_form(paper, json.loads(c['profile']))
            folder = DATA / 'jobs' / job['id']
            folder.mkdir(parents=True,exist_ok=True)
            if job['result']:
                review = Review.model_validate_json(job['result'])
            else:
                pdf = paper.get('sim_pdf_path')
                if not pdf:
                    raise ValueError('投稿没有可读取的 PDF。')
                shutil.copyfile(pdf, folder / 'paper.pdf')
                await asyncio.to_thread(extract_pdf, folder / 'paper.pdf',folder)
                await command(['pdftoppm','-r','85','-png',str(folder/'paper.pdf'),str(folder/'page')],timeout=180)
                raw = await codex(job,review_prompt(c,run,job['reviewer'],paper['sim_review_form']),Review.model_json_schema())
                review = Review.model_validate(raw)
                if review.score > len(json.loads(c['profile'])['score_labels']):
                    raise ValueError('Agent 分数超出会议量表范围。')
                execute('UPDATE jobs SET result=? WHERE id=?',(review.model_dump_json(),job['id']))
            labels = json.loads(c['profile'])['score_labels']
            if review.score > len(labels):
                raise ValueError('Agent 分数超出会议量表范围。')
            current = (await bridge(c['id'],'paper',{'pid':run['pid']}))[0]
            if not current.get('submitted') or current.get('withdrawn') or fingerprint(current) != run['fingerprint']:
                execute("UPDATE jobs SET status='superseded',finished=? WHERE id=?",(time.time(),job['id']))
                return
            validate_form(current, json.loads(c['profile']))
            def section(title, items):
                return '\n\n'+title+'\n'+'\n'.join('- '+s for s in items)
            comments = (f'SIMULATED REVIEW · Reviewer {job["reviewer"]+1}\n'
                f'Submission snapshot: {run["fingerprint"][:16]} · Run {run["id"]}\n'
                + review.recommendation + section('Strengths',review.strengths)
                + section('Weaknesses',review.weaknesses) + section('Questions',review.questions)
                + section('Evidence / page anchors',review.evidence)
                + '\n\nLimitations\n'+review.limitations)
            # Existing reviewer identity makes retries idempotent; historical results live in runs/jobs.
            await bridge(c['id'],'review',{'pid':run['pid'],
                'email':f'reviewer{job["reviewer"]+1}@simulation.local',
                'given_name':'Simulated','family_name':f'Reviewer {job["reviewer"]+1}',
                'submitted':True,'s01':review.score,'s02':review.confidence,
                't01':review.summary,'t02':comments})
        execute("UPDATE jobs SET status='done',error=NULL,finished=? WHERE id=?",(time.time(),job['id']))
    except asyncio.CancelledError:
        raise
    except Exception as e:
        message = str(e)[:2000] or type(e).__name__
        execute("UPDATE jobs SET status='failed',error=?,finished=? WHERE id=?",(message,time.time(),job['id']))
        if job['kind']=='research':
            execute("UPDATE conferences SET status='failed',error=? WHERE id=?",(message,job['cid']))


async def poll_submissions():
    for c in rows("SELECT * FROM conferences WHERE status='ready'"):
        try:
            papers = await bridge(c['id'],'papers')
            for paper in papers:
                if not paper.get('submitted') or paper.get('withdrawn'):
                    execute("UPDATE runs SET status='superseded' WHERE cid=? AND pid=?",(c['id'],paper['pid']))
                    execute("UPDATE jobs SET status='superseded' WHERE run_id IN (SELECT id FROM runs WHERE cid=? AND pid=?) AND status='queued'",(c['id'],paper['pid']))
                    continue
                fp = fingerprint(paper)
                previous = rows('SELECT * FROM runs WHERE cid=? AND pid=? AND fingerprint=?',(c['id'],paper['pid'],fp))
                if previous:
                    if previous[0]['status']=='superseded':
                        with db() as conn:
                            conn.execute("UPDATE runs SET status='superseded' WHERE cid=? AND pid=?",(c['id'],paper['pid']))
                            conn.execute("UPDATE jobs SET status='superseded' WHERE run_id IN (SELECT id FROM runs WHERE cid=? AND pid=?) AND status='queued'",(c['id'],paper['pid']))
                            conn.execute("UPDATE runs SET status='reviewing' WHERE id=?",(previous[0]['id'],))
                            conn.execute("UPDATE jobs SET status='queued',error=NULL,finished=NULL WHERE run_id=? AND status!='running'",(previous[0]['id'],))
                    continue
                rid = uid('r')
                snapshot = {k:v for k,v in paper.items() if k!='sim_reviews'}
                with db() as conn:
                    conn.execute("UPDATE runs SET status='superseded' WHERE cid=? AND pid=?",(c['id'],paper['pid']))
                    conn.execute("UPDATE jobs SET status='superseded' WHERE run_id IN (SELECT id FROM runs WHERE cid=? AND pid=?) AND status='queued'",(c['id'],paper['pid']))
                    conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',(rid,c['id'],paper['pid'],fp,paper['title'],
                        'reviewing',json.dumps(snapshot,ensure_ascii=False),None,time.time()))
                    for n in range(c['count']):
                        conn.execute('INSERT INTO jobs(id,cid,run_id,kind,reviewer,status,created) VALUES(?,?,?,?,?,?,?)',
                            (uid('j'),c['id'],rid,'review',n,'queued',time.time()))
            execute('UPDATE conferences SET error=NULL WHERE id=?',(c['id'],))
        except Exception as e:
            execute('UPDATE conferences SET error=? WHERE id=?',(f'同步投稿失败：{str(e)[:1000]}',c['id']))
    for run in rows("SELECT * FROM runs WHERE status!='superseded'"):
        states = [j['status'] for j in rows('SELECT status FROM jobs WHERE run_id=?',(run['id'],))]
        status = 'done' if states and all(s=='done' for s in states) else 'failed' if 'failed' in states else 'reviewing'
        if 'superseded' in states:
            status='superseded'
        execute('UPDATE runs SET status=? WHERE id=?',(status,run['id']))


async def loop():
    tasks = set()
    last_poll = 0
    concurrency = max(1,min(5,int(os.getenv('AGENT_CONCURRENCY','3'))))
    try:
        while True:
            if time.monotonic()-last_poll > 5:
                await poll_submissions()
                last_poll=time.monotonic()
            tasks = {t for t in tasks if not t.done()}
            for job in rows("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT ?",(max(0,concurrency-len(tasks)),)):
                execute("UPDATE jobs SET status='running',started=?,error=NULL WHERE id=?",(time.time(),job['id']))
                tasks.add(asyncio.create_task(process(job)))
            await asyncio.sleep(1)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
