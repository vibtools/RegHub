from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    framework_slug: str
    framework_name: str
    framework_version: str | None
    language: str | None
    package_manager: str | None
    build_command: str | None
    start_command: str | None
    deploy_type: str
    title: str
    short_description: str | None
    description: str | None
    tags: list[str]
    category_slug: str
    difficulty: str
    use_case: str
    environment: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    quality_score: int = 0
    quality_breakdown: dict[str, int] = field(default_factory=dict)
    security_signals: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "framework": self.framework_slug,
            "framework_name": self.framework_name,
            "framework_version": self.framework_version,
            "language": self.language,
            "package_manager": self.package_manager,
            "build_command": self.build_command,
            "start_command": self.start_command,
            "deploy_type": self.deploy_type,
            "title": self.title,
            "short_description": self.short_description,
            "description": self.description,
            "tags": self.tags,
            "category": self.category_slug,
            "difficulty": self.difficulty,
            "use_case": self.use_case,
            "environment": self.environment,
            "screenshots": self.screenshots,
            "quality_score": self.quality_score,
            "quality_breakdown": self.quality_breakdown,
            "security_signals": self.security_signals,
            "evidence": self.evidence,
        }
