"""Dify adapter: model calls only, no business stores or action permissions."""

import json
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.kernel.types import DomainError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DomainError("AI_REDIRECT_REJECTED", "AI 服务地址重定向，请检查配置", 503)


class DifyGateway:
    def __init__(self, settings):
        self.settings = settings
        self.failures = {}
        self.lock = threading.Lock()

    def configured(self, component):
        return bool(self.settings.dify_base_url and self.settings.dify_api_keys.get(component))

    def call(self, component, inputs, action_id, sample=0, retry_reason=None):
        if not self.configured(component):
            raise DomainError("AI_NOT_CONFIGURED", "Dify 工作流或模型尚未配置", 503)
        with self.lock:
            failures, until = self.failures.get(component, (0, 0))
            if until > time.monotonic():
                raise DomainError("AI_CIRCUIT_OPEN", "AI 服务暂时熔断，稍后重试", 503)
        key = self.settings.dify_api_keys[component].get_secret_value()
        request = Request(
            self.settings.dify_base_url.rstrip("/") + "/workflows/run",
            data=json.dumps(
                {
                    "inputs": {
                        "context": json.dumps(inputs, ensure_ascii=False),
                        "sample": str(sample),
                        "retry_reason": json.dumps(retry_reason or []),
                    },
                    "response_mode": "blocking",
                    "user": action_id,
                }
            ).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(
                request, timeout=self.settings.ai_timeout_seconds
            ) as response:
                body = response.read(512001)
                if len(body) > 512000:
                    raise ValueError("response too large")
            raw = json.loads(body)
            data = raw["data"]
            if data.get("status") != "succeeded":
                raise ValueError("workflow did not succeed")
            output = data["outputs"]
            output = output.get("result", output.get("text", output))
            if isinstance(output, str):
                output = json.loads(output)
            if not isinstance(output, dict):
                raise ValueError("structured output required")
            with self.lock:
                self.failures[component] = (0, 0)
            return {
                "output": output,
                "run_id": str(raw.get("workflow_run_id", ""))[:100],
                "tokens": int(data.get("total_tokens") or 0),
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            OverflowError,
        ):
            with self.lock:
                count = self.failures.get(component, (0, 0))[0] + 1
                self.failures[component] = (count, time.monotonic() + 60 if count >= 3 else 0)
            raise DomainError(
                "AI_PROVIDER_UNAVAILABLE", "AI 调用失败或结构不合法，已保留任务等待重试", 503
            ) from None
