"""server.json (MCP Registry listing) must stay in step with the package."""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_server_json_matches_the_package() -> None:
    server = json.loads((ROOT / "server.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    [package] = server["packages"]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == project["name"]
    assert server["version"] == package["version"] == project["version"]
    assert len(server["description"]) <= 100


def test_readme_carries_the_registry_ownership_marker() -> None:
    server = json.loads((ROOT / "server.json").read_text())
    readme = (ROOT / "README.md").read_text()
    assert f"<!-- mcp-name: {server['name']} -->" in readme
