import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, ClassVar

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.url_security import validate_public_https_url
from app.models.feature_flag import FeatureFlag
from app.models.integration_config import IntegrationConfig

_SLUG_RE = re.compile(r"^[a-z](?:[a-z0-9-]{0,118}[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    key: str
    name: str
    category: str
    description: str
    enabled: bool
    admin_task_allowed: bool = True


@dataclass(frozen=True, slots=True)
class EffectiveIntegration:
    slug: str
    name: str
    integration_type: str
    enabled: bool
    base_url: str | None = None
    username: str | None = None
    secret: str | None = None
    config: dict[str, Any] | None = None
    source: str = "environment"


class SecretCipher:
    """Versioned Fernet keyring with transparent v0.2.x compatibility."""

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValidationError("At least one runtime encryption key is required")
        self._keys: list[tuple[str, Fernet]] = []
        for raw in keys:
            digest = hashlib.sha256(
                ("reghub-runtime-settings-v2:" + raw).encode("utf-8")
            ).digest()
            key_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            self._keys.append((key_id, Fernet(base64.urlsafe_b64encode(digest))))
        self._legacy: list[Fernet] = []
        for raw in keys:
            digest = hashlib.sha256(
                ("reghub-runtime-settings-v1:" + raw).encode("utf-8")
            ).digest()
            self._legacy.append(Fernet(base64.urlsafe_b64encode(digest)))

    @property
    def primary_key_id(self) -> str:
        return self._keys[0][0]

    def encrypt(self, value: str) -> str:
        key_id, cipher = self._keys[0]
        token = cipher.encrypt(value.encode("utf-8")).decode("ascii")
        return f"fernet:v2:{key_id}:{token}"

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        candidates: list[Fernet] = []
        token = value
        if value.startswith("fernet:v2:"):
            try:
                _, _, key_id, token = value.split(":", 3)
            except ValueError as exc:
                raise ValidationError("Stored integration secret uses an invalid format") from exc
            candidates.extend(cipher for item_id, cipher in self._keys if item_id == key_id)
            candidates.extend(cipher for item_id, cipher in self._keys if item_id != key_id)
        elif value.startswith("fernet:v1:"):
            token = value.removeprefix("fernet:v1:")
            candidates.extend(self._legacy)
        else:
            raise ValidationError("Stored integration secret uses an unsupported format")

        for cipher in candidates:
            try:
                return cipher.decrypt(token.encode("ascii")).decode("utf-8")
            except (InvalidToken, UnicodeDecodeError):
                continue
        raise ValidationError(
            "Stored integration secret cannot be decrypted. Check runtime key continuity."
        )


class RuntimeSettingsService:
    FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = ()
    SYSTEM_INTEGRATIONS: ClassVar[dict[str, tuple[str, str]]] = {
        "github": ("GitHub", "source_provider"),
        "gitlab": ("GitLab", "source_provider"),
        "bitbucket": ("Bitbucket", "source_provider"),
        "ai": ("AI Metadata", "ai"),
        "screenshot": ("Screenshot Service", "media"),
    }
    INTEGRATION_FEATURES: ClassVar[dict[str, str]] = {
        "github": "github_import",
        "gitlab": "gitlab_import",
        "bitbucket": "bitbucket_import",
        "ai": "ai_metadata",
        "screenshot": "screenshot_generation",
    }

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._cipher = SecretCipher(settings.runtime_keyring)
        self._features: dict[str, tuple[bool, bool]] = {}
        self._integrations: dict[str, EffectiveIntegration] = {}
        self.FEATURE_DEFINITIONS = self._build_definitions(settings)

    @staticmethod
    def _build_definitions(settings: Settings) -> tuple[FeatureDefinition, ...]:
        return (
            FeatureDefinition(
                "operations_console",
                "Operations Console",
                "Operations",
                "Background operations, live progress, logs, retry and export.",
                True,
            ),
            FeatureDefinition(
                "github_import",
                "GitHub Import",
                "Imports",
                "Import repository metadata from GitHub.",
                True,
            ),
            FeatureDefinition(
                "gitlab_import",
                "GitLab Import",
                "Imports",
                "Import repository metadata from GitLab.",
                True,
            ),
            FeatureDefinition(
                "bitbucket_import",
                "Bitbucket Import",
                "Imports",
                "Import repository metadata from Bitbucket.",
                True,
            ),
            FeatureDefinition(
                "local_import",
                "Local Manifest / ZIP Import",
                "Imports",
                "Allow bounded local manifest and ZIP inspection.",
                settings.local_upload_enabled,
            ),
            FeatureDefinition(
                "source_sync",
                "Source Sync",
                "Template Tasks",
                "Refresh repository metadata, assets, analysis and history.",
                True,
            ),
            FeatureDefinition(
                "template_publication",
                "Template Publication",
                "Template Tasks",
                "Publish, move to draft and disable templates.",
                True,
            ),
            FeatureDefinition(
                "provider_auto_create",
                "Provider Auto-create",
                "Template Tasks",
                "Create provider records from repository owners.",
                True,
            ),
            FeatureDefinition(
                "asset_gallery",
                "Asset Gallery",
                "Media",
                "Manage manual and discovered template assets.",
                True,
            ),
            FeatureDefinition(
                "screenshot_generation",
                "Screenshot Generation",
                "Media",
                "Generate thumbnails through the configured external service.",
                bool(settings.screenshot_service_url),
            ),
            FeatureDefinition(
                "ai_metadata",
                "AI Metadata Enrichment",
                "Analysis",
                "Optional AI metadata enrichment. Deterministic analysis remains available.",
                settings.ai_metadata_enabled,
            ),
            FeatureDefinition(
                "public_api",
                "RegHub Public API",
                "API",
                "Master switch for public registry data endpoints. Health remains available.",
                True,
                False,
            ),
            FeatureDefinition(
                "api_catalog",
                "Catalog API",
                "API",
                "Template list/detail/manifest and resource endpoints.",
                True,
                False,
            ),
            FeatureDefinition(
                "api_assets",
                "Assets API",
                "API",
                "Published template asset endpoint.",
                True,
                False,
            ),
            FeatureDefinition(
                "api_freshness",
                "Freshness API",
                "API",
                "Published template freshness endpoint.",
                True,
                False,
            ),
            FeatureDefinition(
                "api_facets",
                "Facets API",
                "API",
                "Catalog filters and counts endpoint.",
                True,
                False,
            ),
            FeatureDefinition(
                "api_changes",
                "Change Feed API",
                "API",
                "Incremental template change feed.",
                True,
                False,
            ),
        )

    async def initialize(self) -> None:
        async with self._session_factory() as session:
            existing_features = {
                item.key: item for item in (await session.scalars(select(FeatureFlag))).all()
            }
            for definition in self.FEATURE_DEFINITIONS:
                row = existing_features.get(definition.key)
                if row is None:
                    session.add(
                        FeatureFlag(
                            key=definition.key,
                            name=definition.name,
                            category=definition.category,
                            description=definition.description,
                            enabled=definition.enabled,
                            admin_task_allowed=definition.admin_task_allowed,
                        )
                    )
                else:
                    row.name = definition.name
                    row.category = definition.category
                    row.description = definition.description
            existing_integrations = {
                item.slug: item for item in (await session.scalars(select(IntegrationConfig))).all()
            }
            defaults = self._environment_integration_defaults()
            for slug, (name, integration_type) in self.SYSTEM_INTEGRATIONS.items():
                row = existing_integrations.get(slug)
                if row is None:
                    default = defaults[slug]
                    session.add(
                        IntegrationConfig(
                            slug=slug,
                            name=name,
                            integration_type=integration_type,
                            enabled=default.enabled,
                            base_url=default.base_url,
                            username=default.username,
                            use_environment_fallback=True,
                            config=default.config or {},
                            is_system=True,
                        )
                    )
                else:
                    row.is_system = True
            await session.commit()
        await self.reload()

    async def reload(self) -> None:
        async with self._session_factory() as session:
            flags = list((await session.scalars(select(FeatureFlag))).all())
            rows = list((await session.scalars(select(IntegrationConfig))).all())
        self._features = {item.key: (item.enabled, item.admin_task_allowed) for item in flags}
        defaults = self._environment_integration_defaults()
        effective = dict(defaults)
        for row in rows:
            fallback = defaults.get(
                row.slug,
                EffectiveIntegration(
                    slug=row.slug,
                    name=row.name,
                    integration_type=row.integration_type,
                    enabled=False,
                    source="runtime",
                ),
            )
            secret = self._cipher.decrypt(row.secret_encrypted)
            if secret is None and row.use_environment_fallback:
                secret = fallback.secret
            base_url = row.base_url or (fallback.base_url if row.use_environment_fallback else None)
            username = row.username or (fallback.username if row.use_environment_fallback else None)
            merged_config = dict(fallback.config or {}) if row.use_environment_fallback else {}
            merged_config.update(row.config or {})
            effective[row.slug] = EffectiveIntegration(
                slug=row.slug,
                name=row.name,
                integration_type=row.integration_type,
                enabled=row.enabled,
                base_url=base_url,
                username=username,
                secret=secret,
                config=merged_config,
                source="runtime",
            )
        self._integrations = effective

    @property
    def primary_encryption_key_id(self) -> str:
        return self._cipher.primary_key_id

    def feature_enabled(self, key: str, *, task: bool = False) -> bool:
        enabled, task_allowed = self._features.get(key, (False, False))
        return enabled and (task_allowed if task else True)

    def integration(self, slug: str) -> EffectiveIntegration:
        value = self._integrations.get(slug)
        if value is None:
            raise NotFoundError(f"Integration {slug} is not configured")
        return value

    async def feature_rows(self) -> list[FeatureFlag]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(FeatureFlag).order_by(FeatureFlag.category, FeatureFlag.name)
                    )
                ).all()
            )

    async def integration_rows(self) -> list[IntegrationConfig]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(IntegrationConfig).order_by(
                            IntegrationConfig.is_system.desc(), IntegrationConfig.name
                        )
                    )
                ).all()
            )

    async def update_feature(
        self,
        key: str,
        *,
        enabled: bool,
        admin_task_allowed: bool,
        updated_by: str | None,
    ) -> None:
        await self.update_features_bulk(
            {key: (enabled, admin_task_allowed)},
            updated_by=updated_by,
        )

    async def update_features_bulk(
        self,
        values: dict[str, tuple[bool, bool]],
        *,
        updated_by: str | None,
    ) -> None:
        if not values:
            return
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(select(FeatureFlag).where(FeatureFlag.key.in_(values)))
                ).all()
            )
            rows_by_key = {row.key: row for row in rows}
            missing = sorted(set(values) - set(rows_by_key))
            if missing:
                raise NotFoundError(f"Feature setting not found: {', '.join(missing)}")
            for key, (enabled, admin_task_allowed) in values.items():
                row = rows_by_key[key]
                row.enabled = enabled
                row.admin_task_allowed = admin_task_allowed
                row.updated_by = updated_by
            await session.commit()
        await self.reload()

    async def upsert_integration(
        self,
        *,
        slug: str,
        name: str,
        integration_type: str,
        enabled: bool,
        base_url: str | None,
        username: str | None,
        secret: str | None,
        clear_secret: bool,
        use_environment_fallback: bool,
        config: dict[str, Any],
        updated_by: str | None,
    ) -> IntegrationConfig:
        normalized_slug = slug.strip().casefold()
        if not _SLUG_RE.fullmatch(normalized_slug):
            raise ValidationError(
                "Integration slug must use lowercase letters, numbers and hyphens"
            )
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 160:
            raise ValidationError("Integration name is required and must be at most 160 characters")
        clean_type = integration_type.strip().casefold().replace(" ", "-")
        if not clean_type or len(clean_type) > 80:
            raise ValidationError("Integration type is required")
        normalized_url = None
        if base_url and base_url.strip():
            normalized_url = validate_public_https_url(
                base_url.strip(), field_name="Integration base URL"
            )
        clean_username = username.strip()[:255] if username and username.strip() else None
        if secret is not None and len(secret) > 4000:
            raise ValidationError("Integration secret is too long")
        json.dumps(config)
        async with self._session_factory() as session:
            row = await session.scalar(
                select(IntegrationConfig).where(IntegrationConfig.slug == normalized_slug)
            )
            if row is None:
                row = IntegrationConfig(
                    slug=normalized_slug,
                    name=clean_name,
                    integration_type=clean_type,
                    is_system=normalized_slug in self.SYSTEM_INTEGRATIONS,
                )
                session.add(row)
            row.name = clean_name
            row.integration_type = clean_type
            row.enabled = enabled
            row.base_url = normalized_url
            row.username = clean_username
            row.use_environment_fallback = use_environment_fallback
            row.config = config
            row.updated_by = updated_by
            if clear_secret:
                row.secret_encrypted = None
            elif secret:
                row.secret_encrypted = self._cipher.encrypt(secret)
            await session.commit()
            await session.refresh(row)
        await self.reload()
        return row

    async def remove_integration(self, slug: str, *, updated_by: str | None) -> None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(IntegrationConfig).where(IntegrationConfig.slug == slug)
            )
            if row is None:
                raise NotFoundError("Integration not found")
            if row.is_system:
                row.enabled = False
                row.base_url = None
                row.username = None
                row.secret_encrypted = None
                row.use_environment_fallback = False
                row.config = {}
                row.updated_by = updated_by
            else:
                await session.delete(row)
            await session.commit()
        await self.reload()

    def integration_status(self, row: IntegrationConfig) -> dict[str, Any]:
        effective = self._integrations.get(row.slug)
        feature_key = self.INTEGRATION_FEATURES.get(row.slug)
        feature_enabled = self.feature_enabled(feature_key) if feature_key else True
        integration_enabled = bool(effective and effective.enabled)
        configured = True
        if row.slug == "ai":
            configured = bool(effective and effective.base_url and effective.secret)
        elif row.slug == "screenshot":
            configured = bool(effective and effective.base_url)
        return {
            "secret_configured": bool(effective and effective.secret),
            "integration_enabled": integration_enabled,
            "feature_enabled": feature_enabled,
            "configured": configured,
            "effective_enabled": integration_enabled and feature_enabled and configured,
            "source": effective.source if effective else "none",
        }

    def _environment_integration_defaults(self) -> dict[str, EffectiveIntegration]:
        settings = self._settings
        return {
            "github": EffectiveIntegration(
                slug="github",
                name="GitHub",
                integration_type="source_provider",
                enabled=True,
                secret=settings.github_token.get_secret_value() if settings.github_token else None,
                config={
                    "timeout": settings.github_timeout_seconds,
                    "allow_private": settings.github_allow_private_repositories,
                },
            ),
            "gitlab": EffectiveIntegration(
                slug="gitlab",
                name="GitLab",
                integration_type="source_provider",
                enabled=True,
                secret=settings.gitlab_token.get_secret_value() if settings.gitlab_token else None,
                config={"timeout": settings.provider_timeout_seconds},
            ),
            "bitbucket": EffectiveIntegration(
                slug="bitbucket",
                name="Bitbucket",
                integration_type="source_provider",
                enabled=True,
                username=settings.bitbucket_username,
                secret=(
                    settings.bitbucket_app_password.get_secret_value()
                    if settings.bitbucket_app_password
                    else None
                ),
                config={"timeout": settings.provider_timeout_seconds},
            ),
            "ai": EffectiveIntegration(
                slug="ai",
                name="AI Metadata",
                integration_type="ai",
                enabled=settings.ai_metadata_enabled,
                base_url=str(settings.ai_base_url).rstrip("/") if settings.ai_base_url else None,
                secret=settings.ai_api_key.get_secret_value() if settings.ai_api_key else None,
                config={
                    "model": settings.ai_model,
                    "timeout": settings.provider_timeout_seconds,
                },
            ),
            "screenshot": EffectiveIntegration(
                slug="screenshot",
                name="Screenshot Service",
                integration_type="media",
                enabled=bool(settings.screenshot_service_url),
                base_url=(
                    str(settings.screenshot_service_url)
                    if settings.screenshot_service_url
                    else None
                ),
                secret=(
                    settings.screenshot_service_token.get_secret_value()
                    if settings.screenshot_service_token
                    else None
                ),
                config={"timeout": settings.provider_timeout_seconds},
            ),
        }
