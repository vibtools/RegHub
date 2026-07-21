import pytest

from app.core.exceptions import ValidationError
from app.registry.adapters.bitbucket import parse_bitbucket_repository_url
from app.registry.adapters.gitlab import parse_gitlab_repository_url


def test_gitlab_url_with_subgroup() -> None:
    path, normalized = parse_gitlab_repository_url("https://gitlab.com/group/subgroup/template.git")
    assert path == "group/subgroup/template"
    assert normalized == "https://gitlab.com/group/subgroup/template"


def test_bitbucket_url() -> None:
    workspace, slug, normalized = parse_bitbucket_repository_url(
        "https://bitbucket.org/ygit/template.git"
    )
    assert (workspace, slug) == ("ygit", "template")
    assert normalized == "https://bitbucket.org/ygit/template"


@pytest.mark.parametrize(
    "url",
    [
        "http://gitlab.com/group/repo",
        "https://gitlab.com/group/repo/-/issues",
        "https://user:pass@gitlab.com/group/repo",
    ],
)
def test_gitlab_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        parse_gitlab_repository_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://bitbucket.org/team/repo",
        "https://bitbucket.org/team/repo/src/main",
        "https://user:pass@bitbucket.org/team/repo",
    ],
)
def test_bitbucket_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        parse_bitbucket_repository_url(url)
