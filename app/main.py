import asyncio, contextlib, json, os, shutil, signal, time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from .core import *
from . import worker

PHP_PORT = int(os.getenv('HOTCRP_PHP_PORT','8766'))

@asynccontextmanager
async def lifespan(app):
    # One local process owns the queue and the private PHP server.
    import fcntl
    lock=(DATA/'server.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    init_db()
    log=(DATA/'php.log').open('ab')
    php=await asyncio.create_subprocess_exec('php','-d','upload_max_filesize=50M','-d','post_max_size=55M',
        '-d','session.gc_maxlifetime=86400','-d','memory_limit=512M','-S',f'127.0.0.1:{PHP_PORT}',str(ROOT/'extensions/router.php'),
        cwd=UPSTREAM,stdout=log,stderr=log,start_new_session=True)
    await asyncio.sleep(.4)
    if php.returncode is not None:
        raise RuntimeError('PHP failed to start; see data/php.log')
    app.state.client=httpx.AsyncClient(base_url=f'http://127.0.0.1:{PHP_PORT}',timeout=120,follow_redirects=False)
    task=asyncio.create_task(worker.loop())
    app.state.worker=task
    app.state.php=php
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError): await task
        await app.state.client.aclose()
        with contextlib.suppress(ProcessLookupError): os.killpg(php.pid,signal.SIGTERM)
        await php.wait()
        log.close()
        lock.close()

app=FastAPI(title='Local HotCRP simulation',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def local_only(request,call_next):
    origin=request.headers.get('origin')
    if request.headers.get('sec-fetch-site')=='cross-site' or (origin and urlsplit(origin).netloc!=request.headers.get('host')):
        return JSONResponse({'detail':'Cross-origin access is disabled'},403)
    if int(request.headers.get('content-length','0'))>55*1024*1024:
        return JSONResponse({'detail':'Upload exceeds 55 MB'},413)
    return await call_next(request)

@app.get('/')
async def index(): return FileResponse(ROOT/'app/static/index.html')
app.mount('/assets',StaticFiles(directory=ROOT/'app/static'),name='assets')

@app.get('/api/health')
async def health():
    healthy=not app.state.worker.done() and app.state.php.returncode is None
    return JSONResponse({'ok':healthy},status_code=200 if healthy else 503)

@app.get('/api/state')
async def state():
    confs=rows('SELECT * FROM conferences ORDER BY created DESC')
    for c in confs:
        c['profile']=json.loads(c['profile']) if c['profile'] else None
    jobs=rows('SELECT id,cid,run_id,kind,reviewer,status,error,created,started,finished FROM jobs ORDER BY created')
    return {'conferences':confs,'jobs':jobs,'runs':rows('SELECT id,cid,pid,title,status,fingerprint,created FROM runs ORDER BY created DESC'),
        'codex_available':bool(shutil.which(os.getenv('CODEX_BIN','codex'))),'model':os.getenv('CODEX_MODEL','本机 Codex 默认模型')}

class ConferenceInput(BaseModel):
    name:str=Field(min_length=2,max_length=200)
    reviewers:int=Field(default=3,ge=2,le=5)
    language:str=Field(default='中文',pattern='^(中文|English)$')

@app.post('/api/conferences',status_code=201)
async def create(c:ConferenceInput):
    if not c.name.strip(): raise HTTPException(422,'会议名称不能为空')
    id=uid('c')
    execute('INSERT INTO conferences VALUES(?,?,?,?,?,?,?,?)',(id,c.name.strip(),c.reviewers,c.language,'queued',None,None,time.time()))
    worker.new_job(id,'research')
    return {'id':id}

@app.post('/api/jobs/{id}/retry')
async def retry(id:str):
    try: job=one('jobs',id)
    except ValueError: raise HTTPException(404,'任务不存在')
    if job['status']!='failed': raise HTTPException(409,'只有失败的任务可以重试')
    if job['run_id'] and one('runs',job['run_id'])['status']=='superseded':
        raise HTTPException(409,'论文已有新版本，请使用最新审稿任务')
    execute("UPDATE jobs SET status='queued',error=NULL,finished=NULL WHERE id=?",(id,))
    if job['kind']=='research': execute("UPDATE conferences SET status='queued',error=NULL WHERE id=?",(job['cid'],))
    return {'ok':True}

@app.get('/api/runs/{id}/export')
async def export(id:str):
    try: run=one('runs',id)
    except ValueError: raise HTTPException(404,'审稿轮次不存在')
    jobs=rows('SELECT reviewer,status,result,error FROM jobs WHERE run_id=? ORDER BY reviewer',(id,))
    for j in jobs: j['result']=json.loads(j['result']) if j['result'] else None
    return Response(json.dumps({'run':run,'reviews':jobs},ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="{id}.json"'})

@app.api_route('/c/{cid}',methods=['GET'])
async def slash(cid:str): return RedirectResponse(f'/c/{cid}/')

@app.api_route('/c/{cid}/{path:path}',methods=['GET','POST','HEAD','OPTIONS'])
async def proxy(cid:str,path:str,request:Request):
    try: c=one('conferences',cid)
    except ValueError: raise HTTPException(404,'会议不存在')
    if c['status']!='ready': raise HTTPException(409,'会议尚未准备好，请返回首页查看任务')
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>55*1024*1024: raise HTTPException(413,'文件过大')
    headers={k:v for k,v in request.headers.items() if k.lower() not in ('connection','transfer-encoding','x-sim-proxy','accept-encoding')}
    headers['x-sim-proxy']=(DATA/'proxy-key').read_text().strip()
    url=request.url.path+('?' + request.url.query if request.url.query else '')
    r=await app.state.client.request(request.method,url,headers=headers,content=bytes(body))
    response=Response(content=r.content,status_code=r.status_code)
    response.raw_headers=[(k,v) for k,v in r.headers.raw if k.lower() not in
        (b'content-length',b'content-encoding',b'transfer-encoding',b'connection')]
    return response
