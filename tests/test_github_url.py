import pytest

from app.core.exceptions import ValidationError
from app.registry.adapters.github import parse_github_repository_url


def test_normalizes_github_url() -> None:
    owner, repo, normalized = parse_github_repository_url("https://github.com/YGIT/Starter.git")
    assert (owner, repo) == ("YGIT", "Starter")
    assert normalized == "https://github.com/YGIT/Starter"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://github.com/a/b/issues",
        "https://user:pass@github.com/a/b",
        "https://github.com/a/b?x=1",
    ],
)
def test_rejects_unsafe_github_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        parse_github_repository_url(url)
