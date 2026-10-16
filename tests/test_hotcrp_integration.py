"""Real PHP/MariaDB integration. No Codex calls. Uses and drops its own unique DB."""
import asyncio, json, os, shutil
import pytest
import pymysql
from pypdf import PdfWriter
from app import core

pytestmark=pytest.mark.skipif(os.getenv('RUN_HOTCRP_INTEGRATION')!='1',reason='Set RUN_HOTCRP_INTEGRATION=1 for local PHP/MariaDB test')


def test_native_form_pdf_review_and_idempotence(tmp_path):
    cid=core.uid('c')
    p={'name':'Automated integration test','summary':'Fixture','topics':['Systems'],
       'anonymity':'blind','submission_instructions':'Test upload','page_limit':'Unknown',
       'deadline_reference':'Open locally','review_guidance':'Synthetic test',
       'score_labels':['Very poor','Poor','Borderline','Good','Very good','Excellent'],
       'rubric_status':'Test rubric','sources':[{'title':'Fixture','url':'https://example.com','supports':'Test only'}],
       'uncertainties':['Synthetic fixture']}
    path=tmp_path/'fixture.pdf'
    w=PdfWriter();w.add_blank_page(width=612,height=792);w.write(path)
    async def run():
        core.create_database(cid)
        settings=await core.bridge(cid,'setup',core.settings_for(p))
        assert settings['ok']
        result=await core.bridge(cid,'submit',{'pid':'new','title':'Test integration',
            'abstract':'Integration fixture only.','authors':[{'email':'chair@simulation.local','name':'Local Chair','affiliation':'Local simulation'}],
            'submission':{'content_file':str(path),'mimetype':'application/pdf'},'submitted':True})
        pid=result['pid']
        paper=(await core.bridge(cid,'paper',{'pid':pid}))[0]
        assert paper['submitted']
        assert core.Path(paper['sim_pdf_path']).is_file()
        fields={f['id']:f for f in paper['sim_review_form']}
        assert fields['s01']['values']==p['score_labels']
        assert fields['s02']['values']==['Low','Medium','High','Very high']
        review={'pid':pid,'email':'reviewer1@simulation.local','submitted':True,
                's01':6,'s02':3,'t01':'A synthetic integration test.','t02':'Not an actual academic review.'}
        first=await core.bridge(cid,'review',review)
        second=await core.bridge(cid,'review',review)
        assert first['status']=='complete' and first['rid']==second['rid']
        final=(await core.bridge(cid,'paper',{'pid':pid}))[0]
        assert len(final['sim_reviews'])==1
        assert final['sim_reviews'][0]['OveMer']==6
        assert core.fingerprint(paper)==core.fingerprint(final)
    try:
        asyncio.run(run())
    finally:
        creds=json.loads((core.DATA/'database.json').read_text())
        conn=pymysql.connect(unix_socket='/run/mysqld/mysqld.sock',**creds,autocommit=True)
        with conn.cursor() as cur: cur.execute(f'DROP DATABASE IF EXISTS `hcsim_{cid}`')
        conn.close()
        for parent in ['documents','papers']:
            shutil.rmtree(core.DATA/parent/cid,ignore_errors=True)
