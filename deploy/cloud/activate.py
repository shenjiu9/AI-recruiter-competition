"""Enable the provisioned cloud workflows with mandatory human review."""
import json
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parents[2]
env = root / 'backend/.env'
set_key(env, 'DIFY_DOCKER_BASE_URL', 'http://dify-gateway/v1')
values = dotenv_values(env)
with httpx.Client(base_url='http://127.0.0.1:8000/api/v1', timeout=30, trust_env=False) as client:
    response = client.post('/auth/dev-login', json={'user_id':'admin','password':values['DEV_LOGIN_PASSWORD']})
    response.raise_for_status()
    client.headers['Authorization'] = 'Bearer ' + response.json()['token']
    response = client.get('/hr/automation-live')
    response.raise_for_status()
    before = response.json()
    response = client.post('/hr/automation-live', headers={'Idempotency-Key':str(uuid4())}, json={
        'expected_version': before['version'], 'mode':'manual',
        'components': {**before['components'], **{f'A{i}':True for i in range(1,8)}},
    })
    response.raise_for_status()
    print('A1-A7 enabled in human-review mode.')
env.chmod(0o600)
(root/'backend/.env.dify-local').chmod(0o600)
print('Cloud model connectivity and credentials configured.')
