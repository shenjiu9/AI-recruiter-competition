"""Exercise the deployed HTTPS/API/model path using one labelled synthetic profile."""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[2]
values = dotenv_values(root/'backend/.env')
report = {'https':{}, 'synthetic_data_only':True}
with httpx.Client(timeout=120, follow_redirects=True, trust_env=False) as client:
    for app in ('hr','biz','candidate','dify'):
        url = f'https://{app}.45-76-191-78.sslip.io'
        response = client.get(url)
        response.raise_for_status()
        report['https'][app] = response.status_code
    base = 'https://hr.45-76-191-78.sslip.io/api/v1'
    response = client.post(base+'/auth/dev-login', json={'user_id':'hr','password':values['DEV_LOGIN_PASSWORD']})
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer '+response.json()['token']
    response = client.get(base+'/hr/ai-health')
    response.raise_for_status()
    report['ai_health'] = response.json()
    def post(path, data):
        response = client.post(base+path, json=data, headers={'Idempotency-Key':str(uuid4())})
        response.raise_for_status()
        return response.json()
    candidate = post('/hr/candidates', {'profile':{'name':'云端联调候选人（合成）','skills':'Python；PostgreSQL'}})['candidate']
    post('/hr/candidates/'+candidate['id']+'/actions', {
        'action':'consent','expected_version':candidate['version'],'granted':True,
        'evidence':'系统联调合成资料，不涉及真实个人','reason':'云端集成测试',
    })
    result = post('/hr/ai-intents', {'text':'帮我提取云端联调候选人（合成）的简历信息'})
    report['intent'] = {k:result.get(k) for k in ('status','component','router')}
    job = result.get('job')
    assert job is not None, report['intent']
    for _ in range(60):
        response = client.get(base+'/hr/ai-jobs/'+job['id'])
        response.raise_for_status()
        job = response.json()
        if job['status'] not in ('queued','running','retry'):break
        time.sleep(2)
    report['job'] = {'id':job['id'],'status':job['status'],'component':job['component']}
    assert job['status']=='review',report['job']
    report['passed']=True
out=root/'test-results/cloud-live-smoke.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
