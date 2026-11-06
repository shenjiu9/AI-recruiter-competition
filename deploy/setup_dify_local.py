"""Prepare an existing official Dify checkout without exposing generated secrets."""

import argparse
import hashlib
import json
import secrets
import subprocess
from pathlib import Path

from dotenv import dotenv_values, set_key

parser = argparse.ArgumentParser()
parser.add_argument("checkout", type=Path)
args = parser.parse_args()
directory = args.checkout.resolve() / "docker"
if not (directory / "docker-compose.yaml").is_file():
    raise SystemExit("Clone the official Dify release first")
env_file = directory / ".env"
if not env_file.exists():
    values = {
        "COMPOSE_PROJECT_NAME": "recruiter-dify",
        "COMPOSE_PROFILES": "weaviate,postgresql,collaboration",
        "EXPOSE_NGINX_PORT": "8080",
        "EXPOSE_NGINX_SSL_PORT": "8443",
        "EXPOSE_PLUGIN_DEBUGGING_PORT": "5003",
        "DIFY_AGENT_SERVER_SECRET_KEY": secrets.token_urlsafe(32),
        "WEAVIATE_AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED": "false",
        "WEAVIATE_DISABLE_TELEMETRY": "true",
        "CHECK_UPDATE_URL": "",
    }
    for key in (
        "DB_PASSWORD",
        "REDIS_PASSWORD",
        "SANDBOX_API_KEY",
        "PLUGIN_DAEMON_KEY",
        "PLUGIN_DIFY_INNER_API_KEY",
        "DIFY_AGENT_API_TOKEN",
        "DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN",
        "WEAVIATE_API_KEY",
    ):
        values[key] = secrets.token_hex(32)
    values["CODE_EXECUTION_API_KEY"] = values["SANDBOX_API_KEY"]
    values["WEAVIATE_AUTHENTICATION_APIKEY_ALLOWED_KEYS"] = values["WEAVIATE_API_KEY"]
    env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
values = dotenv_values(env_file)
for key in (
    "EXPOSE_NGINX_PORT",
    "EXPOSE_NGINX_SSL_PORT",
    "EXPOSE_PLUGIN_DEBUGGING_PORT",
):
    if values.get(key, "").startswith("127.0.0.1:"):
        set_key(env_file, key, values[key].split(":")[-1])
if values.get("DIFY_AGENT_SERVER_SECRET_KEY", "").endswith("="):
    set_key(
        env_file,
        "DIFY_AGENT_SERVER_SECRET_KEY",
        values["DIFY_AGENT_SERVER_SECRET_KEY"].rstrip("="),
    )
result = subprocess.run(
    ["docker", "compose", "-f", "docker-compose.yaml", "config", "--format", "json"],
    cwd=directory,
    capture_output=True,
    check=True,
)
config = json.loads(result.stdout)
config.setdefault("volumes", {})
for service in config["services"].values():
    if "depends_on" in service:
        service["depends_on"] = {
            k: v for k, v in service["depends_on"].items() if k in config["services"]
        }
    for port in service.get("ports", []):
        port["host_ip"] = "127.0.0.1"
    for mount in service.get("volumes", []):
        source = mount.get("source", "").replace("\\", "/")
        if mount["type"] == "bind" and "/volumes/" in source:
            volume = "local_" + hashlib.sha256(source.encode()).hexdigest()[:16]
            config["volumes"][volume] = {}
            mount.update(type="volume", source=volume)
            mount.pop("bind", None)
plugin_mounts = config["services"]["plugin_daemon"]["volumes"]
storage = next(m for m in plugin_mounts if m["target"] == "/app/storage")
config["services"]["init_plugin_permissions"] = {
    "image": "busybox:latest",
    "user": "0",
    "restart": "no",
    "command": ["chown", "-R", "1001:1001", "/app/storage"],
    "volumes": [storage],
}
config["services"]["plugin_daemon"].setdefault("depends_on", {})["init_plugin_permissions"] = {
    "condition": "service_completed_successfully",
    "required": True,
}
(directory / "compose.local.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
print(
    "Local settings prepared; .env and resolved compose.local.json contain private settings. Run with -f compose.local.json only."
)
