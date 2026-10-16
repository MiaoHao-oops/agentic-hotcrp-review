"""Public progress summaries: never expose model prose, commands or tool outputs."""
import json
import re
from . import core

STEPS = {
    'research': [('prepare','准备调研'),('agent','检索会议、量表与 PC 资料'),('validate','校验调研结果'),('publish','配置 HotCRP')],
    'review': [('prepare','检查投稿'),('extract','提取正文与页面'),('agent','独立阅读与评审'),('validate','校验评分与投稿版本'),('publish','写入 HotCRP reviews')],
}


def progress_for(job):
    saved = json.loads(job.get('progress') or '{}')
    status = job['status']
    stage = saved.get('stage', 'agent' if status=='running' else 'prepare')
    steps = STEPS[job['kind']]
    index = next((i for i,(key,_) in enumerate(steps) if key==stage),0)
    result = {'steps':[label for _,label in steps], 'index':index,
              'stage':stage, 'label':dict(steps).get(stage, '等待上游恢复'),
              'updated':saved.get('updated'), 'activity':[], 'last_event':None}
    if status!='running':
        if status in ('queued','deploy_wait'):result['index']=0
        result['label']={'deploy_wait':'等待服务更新后继续','done':'已完成','queued':'排队等待 worker','failed':'失败，可重试','cancelled':'已取消','superseded':'历史版本，已停止'}.get(status,status)
        if status=='done':result['index']=len(steps)
        return result
    if stage=='retry':
        result['label']=f"上游暂时不可用，等待第 {saved.get('attempt',1)} 次重试"
        result['retry_at']=saved.get('retry_at')
        result['index']=next(i for i,(key,_) in enumerate(steps) if key=='agent')
    # Read a bounded tail; partial JSON records are expected while the CLI writes.
    if not re.fullmatch(r'j[a-f0-9]{12}',job['id']):return result
    path=core.DATA/'jobs'/job['id']/'events.jsonl'
    try:
        with path.open('rb') as f:
            size=f.seek(0,2);f.seek(max(0,size-131072));raw=f.read()
        result['last_event']=path.stat().st_mtime
    except OSError:
        return result
    if stage not in ('agent','retry'):return result
    for line in raw.decode(errors='replace').splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if not isinstance(event,dict):continue
        kind=event.get('type');item=event.get('item') or {}
        if not isinstance(item,dict):continue
        label=None
        if kind=='thread.started':label='Codex 会话已建立'
        elif kind=='turn.started':label='Agent 已开始处理任务'
        elif kind=='turn.completed':label='Agent 已返回结果'
        elif kind=='turn.failed':label='本次 Agent 执行失败'
        elif kind=='error':label='上游连接异常或正在重连'
        elif kind in ('item.started','item.completed'):
            complete=kind=='item.completed'
            action={'web_search':'网页检索或来源核查','command_execution':'本地材料读取或工具操作','image_view':'论文页面查看'}.get(item.get('type'))
            if action:label=('已完成：' if complete else '进行中：')+action
        if label:
            if not result['activity'] or result['activity'][-1]!=label:result['activity'].append(label)
    result['activity']=result['activity'][-5:]
    return result
