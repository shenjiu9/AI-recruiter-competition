import ast
from pathlib import Path


def test_module_privacy_and_domain_purity():
    root = Path(__file__).parents[1] / "app"
    violations = []
    for path in (root / "modules").rglob("*.py"):
        module = path.relative_to(root).parts[1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else ([n.name for n in node.names] if isinstance(node, ast.Import) else [])
            )
            for name in names:
                parts = name.split(".")
                if (
                    name.startswith("app.modules.")
                    and parts[2] != module
                    and parts[3] not in {"public", "contracts"}
                ):
                    violations.append(f"{path}: private module import {name}")
                if "domain" in path.parts and (
                    name.startswith(("sqlalchemy", "fastapi", "app.platform", "httpx"))
                ):
                    violations.append(f"{path}: domain imports infrastructure {name}")
    assert violations == []
