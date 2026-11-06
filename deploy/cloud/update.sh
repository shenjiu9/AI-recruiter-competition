#!/usr/bin/env bash
set -euo pipefail
cd /opt/ai-recruiter/app
git pull --ff-only
docker compose --env-file backend/.env -f deploy/compose.yaml -f deploy/cloud/compose.yaml --profile web up -d --build
curl --fail --retry 15 --retry-all-errors --retry-delay 2 http://127.0.0.1:8000/health/ready
echo 'Application updated. Dify data and manually edited workflow drafts are preserved.'
