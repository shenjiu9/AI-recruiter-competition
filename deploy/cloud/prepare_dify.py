"""Isolate a fresh Dify deployment and use its private Docker service network."""
import json
import secrets
import subprocess
from pathlib import Path
from dotenv import set_key

root = Path(__file__).resolve().parents[2]
checkout = root.parent / 'dify'
env = checkout / 'docker' / '.env'
if not env.exists():
    # setup_local produces fresh passwords and loopback-only port mappings.
    subprocess.run(['python', str(root/'deploy/setup_dify_local.py'), str(checkout)], check=True)
    set_key(env, 'SECRET_KEY', secrets.token_urlsafe(48))
    set_key(env, 'APP_WEB_URL', 'https://dify.45-76-191-78.sslip.io')
    set_key(env, 'FILES_URL', 'https://dify.45-76-191-78.sslip.io')
    set_key(env, 'NEXT_TELEMETRY_DISABLED', '1')
subprocess.run(['python', str(root/'deploy/setup_dify_local.py'), str(checkout)], check=True)
# Share only the Dify nginx network with the recruitment API. Host-published
# loopback ports cannot be reached through host-gateway on Linux.
path = checkout/'docker/compose.local.json'
config = json.loads(path.read_text())
config.setdefault('networks', {})['recruiter_internal'] = {'name':'recruiter-dify-link','external': True}
config['services']['nginx'].setdefault('networks', {})['recruiter_internal'] = {'aliases':['dify-gateway']}
path.write_text(json.dumps(config, indent=2))
path.chmod(0o600)
