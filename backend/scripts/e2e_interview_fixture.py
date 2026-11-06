"""Synthetic finished interview, only for the disposable Playwright server.

Uses normal APIs to create the recruitment flow; adjusts the fixture's appointment
to the past so browser tests can submit feedback without waiting several days.
Never imported by production startup or the development seed command.
"""

import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.interfaces.api.app import create_api


def seed_finished_interview(container, for_hiring=False):
    sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))
    from test_interviews import action, choose, feedback, offer, setup

    settings = container.settings
    previous = settings.position_worker_enabled, settings.conversation_worker_enabled
    settings.position_worker_enabled = settings.conversation_worker_enabled = False
    try:
        with TestClient(create_api(container)) as client:

            def login(actor="hr", key=None):
                response = client.post(
                    "/api/v1/auth/dev-login",
                    json={"user_id": actor, "password": settings.dev_login_password},
                )
                assert response.status_code == 200
                return {
                    "Authorization": "Bearer " + response.json()["token"],
                    "Idempotency-Key": key or uuid4().hex,
                }

            fields = {
                "recruitType": "社招",
                "dept": "客服中心",
                "employmentType": "外包",
                "reqType": "新增",
                "headcount": "1",
                "title": "面评浏览器测试岗位",
                "series": "客服",
                "level": "P3",
                "city": "深圳",
                "reportTo": "何美玲",
                "expectedOnboard": (container.clock.now() + timedelta(days=30)).date().isoformat(),
                "salary": "8-12K/月×13",
                "reason": "面评浏览器测试",
                "duties": "客户服务",
                "requirements": "沟通能力",
            }
            f = setup(client, login, fields, container)
            iv = offer(f)
            assert choose(f, iv["slots"][0]["id"]).status_code == 200
            with container.scope() as s:
                iv = s.interview.store.get(f.iv["id"])
                iv.update(
                    start=(container.clock.now() - timedelta(hours=2)).isoformat(),
                    end=(container.clock.now() - timedelta(hours=1)).isoformat(),
                )
                s.interview.store.release(iv["id"])
                s.interview.store.save(iv, iv["version"])
            assert action(f, "complete", reason="仅限临时测试库的已结束场次").status_code == 200
            if for_hiring:
                assert feedback(f).status_code == 200
                with container.scope() as s:
                    s.decision.sync()
    finally:
        settings.position_worker_enabled, settings.conversation_worker_enabled = previous
