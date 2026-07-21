from datetime import UTC, datetime, timedelta

from app.analyzer.service import TemplateAnalyzer
from app.registry.adapters.base import ImportedRepository


def repository(**overrides) -> ImportedRepository:
    base = dict(
        adapter="github",
        external_id="demo",
        name="saas-dashboard-nextjs",
        description="A modern dashboard with authentication and Tailwind",
        repository_url="https://github.com/ygit/demo",
        default_branch="main",
        homepage_url="https://demo.example.com",
        license_spdx="MIT",
        topics=["dashboard", "saas"],
        primary_language="TypeScript",
        stars_count=120,
        forks_count=10,
        root_files=frozenset(
            {"package.json", "package-lock.json", "next.config.mjs", ".env.example"}
        ),
        package_json={
            "dependencies": {"next": "15.1.0", "react": "19.0.0"},
            "devDependencies": {"typescript": "5.7.0"},
            "scripts": {"build": "next build", "start": "next start"},
        },
        metadata={},
        source_updated_at=datetime.now(UTC) - timedelta(days=30),
        readme_text="# Dashboard\n" + "Detailed documentation. " * 50,
        env_example_text="DATABASE_URL=change-me\nNEXTAUTH_SECRET=change-me\n",
        screenshot_urls=["https://example.com/screenshot.png"],
    )
    base.update(overrides)
    return ImportedRepository(**base)


def test_auto_metadata_and_quality_score() -> None:
    result = TemplateAnalyzer().analyze(repository())
    assert result.framework_slug == "nextjs"
    assert result.framework_version == "15.1.0"
    assert result.language == "TypeScript"
    assert result.package_manager == "npm"
    assert result.category_slug == "saas"
    assert result.difficulty in {"intermediate", "advanced"}
    assert "dashboard" in result.tags
    assert result.quality_score >= 70
    assert result.environment[0]["key"] == "DATABASE_URL"
    assert result.environment[1]["secret"] is True


def test_quality_score_drops_without_docs_or_license() -> None:
    strong = TemplateAnalyzer().analyze(repository())
    weak = TemplateAnalyzer().analyze(
        repository(
            readme_text=None,
            license_spdx=None,
            screenshot_urls=[],
            homepage_url=None,
            stars_count=0,
            forks_count=0,
            env_example_text=None,
        )
    )
    assert weak.quality_score < strong.quality_score
    assert weak.security_signals
