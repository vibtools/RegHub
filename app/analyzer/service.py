from app.analyzer.framework import detect_framework, detect_language
from app.analyzer.metadata import (
    descriptions,
    infer_category,
    infer_difficulty,
    infer_tags,
    infer_use_case,
    title_from_name,
)
from app.analyzer.models import AnalysisResult
from app.analyzer.package import detect_package_manager
from app.analyzer.score import calculate_quality
from app.analyzer.security import inspect_security
from app.registry.adapters.base import ImportedRepository


class TemplateAnalyzer:
    def analyze(self, repository: ImportedRepository) -> AnalysisResult:
        detection = detect_framework(repository)
        language = detect_language(repository, detection)
        package_manager = detect_package_manager(repository.root_files)
        title = title_from_name(repository.name)
        tags = infer_tags(repository, detection.slug)
        category_slug = infer_category(tags)
        short_description, description = descriptions(repository, title, detection)
        screenshots = list(dict.fromkeys(repository.screenshot_urls))[:12]
        security_signals = inspect_security(repository)
        score, breakdown = calculate_quality(
            repository,
            framework_detected=detection.slug != "unknown",
            screenshot_count=len(screenshots),
            security_signal_count=len(security_signals),
        )
        return AnalysisResult(
            framework_slug=detection.slug,
            framework_name=detection.name,
            framework_version=detection.version,
            language=language,
            package_manager=package_manager,
            title=title,
            short_description=short_description,
            description=description,
            tags=tags,
            category_slug=category_slug,
            difficulty=infer_difficulty(repository),
            use_case=infer_use_case(category_slug),
            screenshots=screenshots,
            quality_score=score,
            quality_breakdown=breakdown,
            security_signals=security_signals,
            evidence={
                "confidence": detection.confidence,
                "framework_evidence": detection.evidence,
                "root_files": sorted(repository.root_files)[:200],
                "readme_present": bool(repository.readme_text),
                "package_json_present": bool(repository.package_json),
                "requirements_present": bool(repository.requirements_text),
                "pyproject_present": bool(repository.pyproject_text),
                "license_present": bool(repository.license_spdx or repository.license_text),
            },
        )
