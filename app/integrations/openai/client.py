import json
import logging
from dataclasses import replace

import httpx

from app.analyzer.models import AnalysisResult
from app.registry.adapters.base import ImportedRepository

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 1_000_000


class AIMetadataEnricher:
    """Optional OpenAI-compatible enrichment. Failures never block registry imports."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str | None,
        api_key: str | None,
        model: str,
        timeout: int = 20,
    ) -> None:
        self._enabled = bool(enabled and base_url and api_key)
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return self._enabled

    def can_enrich(self, repository: ImportedRepository) -> bool:
        return self._enabled and not repository.is_private

    async def enrich(
        self, repository: ImportedRepository, analysis: AnalysisResult
    ) -> AnalysisResult:
        if not self._enabled:
            return analysis
        if repository.is_private:
            logger.warning(
                "AI metadata enrichment skipped for a private %s repository",
                repository.adapter,
            )
            return analysis
        payload = {
            "model": self._model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return JSON only with title, short_description, description, tags, "
                        "category, difficulty, use_case. Do not invent unsupported capabilities."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "repository_name": repository.name,
                            "repository_description": repository.description,
                            "topics": repository.topics,
                            "framework": analysis.framework_name,
                            "language": analysis.language,
                            "readme_excerpt": (repository.readme_text or "")[:5000],
                            "deterministic_metadata": {
                                "title": analysis.title,
                                "short_description": analysis.short_description,
                                "description": analysis.description,
                                "tags": analysis.tags,
                                "category": analysis.category_slug,
                                "difficulty": analysis.difficulty,
                                "use_case": analysis.use_case,
                            },
                        }
                    ),
                },
            ],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                if len(response.content) > _MAX_RESPONSE_BYTES:
                    raise ExternalServiceError("AI metadata response was too large")
                content = response.json()["choices"][0]["message"]["content"]
                result = json.loads(content)
            title = str(result.get("title") or analysis.title)[:160]
            short = (
                str(result.get("short_description") or analysis.short_description or "")[:320]
                or None
            )
            description = (
                str(result.get("description") or analysis.description or "")[:5000] or None
            )
            tags = [
                str(x).casefold()[:60]
                for x in result.get("tags", analysis.tags)
                if isinstance(x, str)
            ][:20]
            category = str(result.get("category") or analysis.category_slug).casefold()[:120]
            difficulty = str(result.get("difficulty") or analysis.difficulty).casefold()
            if difficulty not in {"beginner", "intermediate", "advanced"}:
                difficulty = analysis.difficulty
            return replace(
                analysis,
                title=title,
                short_description=short,
                description=description,
                tags=tags or analysis.tags,
                category_slug=category or analysis.category_slug,
                difficulty=difficulty,
                use_case=str(result.get("use_case") or analysis.use_case)[:160],
            )
        except Exception:
            logger.exception("AI metadata enrichment failed; deterministic metadata retained")
            return analysis
