import json
from types import SimpleNamespace

from app.integrations.github import client as github_client_module
from app.integrations.github.client import GitHubClient


def test_github_token_is_used_without_being_exposed(monkeypatch) -> None:
    captured: dict[str, object] = {}
    token_object = object()

    def fake_token(value: str):
        captured["token_value"] = value
        return token_object

    class FakeGithub:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(github_client_module.Auth, "Token", fake_token)
    monkeypatch.setattr(github_client_module, "Github", FakeGithub)

    client = GitHubClient("  company-token  ", timeout=15, allow_private=False)

    assert client.is_authenticated is True
    assert captured["token_value"] == "company-token"
    assert captured["auth"] is token_object
    assert "company-token" not in repr(client.__dict__)


def test_reads_small_package_json() -> None:
    payload = {"dependencies": {"astro": "^5.0.0"}}
    content = SimpleNamespace(
        type="file",
        size=len(json.dumps(payload).encode()),
        decoded_content=json.dumps(payload).encode(),
    )
    repo = SimpleNamespace(get_contents=lambda path: content)

    assert GitHubClient._read_package_json(repo) == payload


def test_ignores_oversized_package_json() -> None:
    content = SimpleNamespace(type="file", size=300_000, decoded_content=b"{}")
    repo = SimpleNamespace(get_contents=lambda path: content)

    assert GitHubClient._read_package_json(repo) is None
