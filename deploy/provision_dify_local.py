"""Initialize a loopback Dify workspace and import reproducible workflow drafts.

Credentials and app IDs are stored only in backend/.env.dify-local (gitignored).
Publishing and configuring API keys is explicit via --publish, after a model is configured.
"""

import argparse
import base64
import json
import secrets
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--install-model", action="store_true")
    parser.add_argument("--configure-model", action="store_true")
    parser.add_argument("--sync-drafts", action="store_true")
    parser.add_argument("--components", nargs="+", choices=[f"A{i}" for i in range(8)])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / "backend" / ".env.dify-local"
    path.touch(exist_ok=True)
    values = dotenv_values(path)
    if not values.get("DIFY_ADMIN_PASSWORD"):
        set_key(path, "DIFY_ADMIN_EMAIL", "admin@example.com")
        set_key(path, "DIFY_ADMIN_PASSWORD", "Recruiter9" + secrets.token_hex(12))
        values = dotenv_values(path)
    with httpx.Client(
        base_url="http://localhost:8080/console/api",
        timeout=90,
        trust_env=False,
        headers={
            "Origin": "http://localhost:8080",
            "Referer": "http://localhost:8080/",
        },
    ) as client:

        def call(method, url, **kwargs):
            response = client.request(method, url, **kwargs)
            if response.status_code >= 400:
                # Do not echo request/response bodies containing credentials.
                raise SystemExit(f"Dify {method} {url}: HTTP {response.status_code}")
            return response.json()

        if call("GET", "/setup")["step"] == "not_started":
            call(
                "POST",
                "/setup",
                json={
                    "email": values["DIFY_ADMIN_EMAIL"],
                    "name": "招聘系统管理员",
                    "password": values["DIFY_ADMIN_PASSWORD"],
                    "language": "zh-Hans",
                },
            )
            print("Dify local administrator initialized; credentials saved privately")
        call(
            "POST",
            "/login",
            json={
                "email": values["DIFY_ADMIN_EMAIL"],
                "password": base64.b64encode(
                    values["DIFY_ADMIN_PASSWORD"].encode()
                ).decode(),
                "remember_me": True,
            },
        )
        for cookie in client.cookies.jar:
            if "csrf" in cookie.name.lower():
                client.headers["X-CSRF-Token"] = cookie.value
        if args.install_model:
            # Official publisher package pinned for reproducible local deployment.
            identifier = "langgenius/deepseek:0.0.26@bdf47cb41e9062bba00d26625d2a795c1874011d8ce64bff738c44b5a31787ea"
            result = call(
                "POST",
                "/workspaces/current/plugin/install/marketplace",
                json={"plugin_unique_identifiers": [identifier]},
            )
            print(
                "DeepSeek plugin installation requested; task="
                + str(result.get("task_id", "pending"))
            )
        if args.configure_model:
            key = dotenv_values(root / "backend" / ".env").get("DEEPSEEK_API_KEY")
            if not key:
                raise SystemExit(
                    "Save DEEPSEEK_API_KEY in backend/.env first; never put it on the command line"
                )
            digest = sha256(key.encode()).hexdigest()
            if values.get("DIFY_MODEL_KEY_FINGERPRINT") != digest:
                call(
                    "POST",
                    "/workspaces/current/model-providers/langgenius/deepseek/deepseek/credentials",
                    json={
                        "credentials": {
                            "api_key": key,
                            "endpoint_url": "https://api.deepseek.com",
                            "enable_request_metadata": "disabled",
                        },
                        "name": "Recruiter DeepSeek",
                    },
                )
                set_key(path, "DIFY_MODEL_KEY_FINGERPRINT", digest)
            print("DeepSeek model credential configured")
        keys = {}
        for file in sorted((root / "deploy" / "dify" / "workflows").glob("A*.yml")):
            component = file.stem
            if args.components and component not in args.components:
                continue
            app_id = values.get("DIFY_APP_" + component)
            if not app_id or args.sync_drafts:
                if app_id:
                    # Keep the previous DSL private so a manually edited workflow is recoverable.
                    backup = (
                        root
                        / "backups"
                        / "dify-workflows"
                        / datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                    )
                    backup.mkdir(parents=True, exist_ok=True)
                    exported = call(
                        "GET",
                        f"/apps/{app_id}/export",
                        params={"include_secret": "false"},
                    )
                    saved = backup / f"{component}.yml"
                    saved.write_text(exported["data"], encoding="utf-8")
                    saved.chmod(0o600)
                result = call(
                    "POST",
                    "/apps/imports",
                    json={
                        "mode": "yaml-content",
                        "yaml_content": file.read_text(encoding="utf-8"),
                        **({"app_id": app_id} if app_id else {}),
                    },
                )
                if result["status"] == "pending":
                    result = call(
                        "POST", "/apps/imports/" + result["id"] + "/confirm", json={}
                    )
                if result["status"] not in {"completed", "completed-with-warnings"}:
                    raise SystemExit("Dify import needs attention: " + component)
                app_id = result["app_id"]
                set_key(path, "DIFY_APP_" + component, app_id)
            # Workflows run through the authenticated backend, never an anonymous WebApp.
            call("POST", f"/apps/{app_id}/site-enable", json={"enable_site": False})
            print(component + " workflow draft available")
            if args.publish:
                if not dotenv_values(path).get("DIFY_MODEL_KEY_FINGERPRINT"):
                    raise SystemExit(
                        "Configure and validate the model credential before publishing"
                    )
                call(
                    "POST",
                    f"/apps/{app_id}/workflows/publish",
                    json={
                        "marked_name": "Recruiter v1",
                        "marked_comment": "Backend evidence validation required",
                    },
                )
                existing = call("GET", f"/apps/{app_id}/api-keys")["data"]
                key = (
                    existing[0]
                    if existing
                    else call("POST", f"/apps/{app_id}/api-keys", json={})
                )
                keys[component] = key["token"]
        if keys:
            env = root / "backend" / ".env"
            current = dotenv_values(env)
            merged = json.loads(current.get("DIFY_API_KEYS") or "{}") | keys
            set_key(env, "DIFY_API_KEYS", json.dumps(merged))
            if not current.get("DIFY_BASE_URL"):
                set_key(env, "DIFY_BASE_URL", "http://localhost:8080/v1")
            if not current.get("DIFY_DOCKER_BASE_URL"):
                set_key(
                    env, "DIFY_DOCKER_BASE_URL", "http://host.docker.internal:8080/v1"
                )
            print(
                "Published workflow API keys saved to backend/.env; component policy remains unchanged"
            )


if __name__ == "__main__":
    main()
