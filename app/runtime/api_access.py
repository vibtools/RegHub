import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.models.api_access import ApiAccessPolicy, ApiBlockRule, ApiServiceToken


@dataclass(frozen=True, slots=True)
class ApiAccessSnapshot:
    mode: str
    tokens: tuple[ApiServiceToken, ...]
    block_rules: tuple[ApiBlockRule, ...]


class ApiAccessService:
    MODES: ClassVar[set[str]] = {"development", "live"}
    BLOCK_RULE_ALIASES: ClassVar[dict[str, str]] = {
        "10.x.x.x": "10.0.0.0/8",
        "172.x.x.x": "172.16.0.0/12",
        "192.168.x.x": "192.168.0.0/16",
        "169.254.x.x": "169.254.0.0/16",
    }
    SCOPES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("catalog", "Templates, manifest and resource lists"),
        ("assets", "Template asset endpoints"),
        ("freshness", "Template freshness endpoint"),
        ("facets", "Catalog facets endpoint"),
        ("changes", "Incremental change feed"),
        ("capabilities", "Capabilities endpoint"),
    )

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        master_secret: str,
    ) -> None:
        self._session_factory = session_factory
        self._hash_key = hashlib.sha256(
            ("reghub-api-token-v1:" + master_secret).encode("utf-8")
        ).digest()
        self._mode = "development"
        self._tokens: tuple[ApiServiceToken, ...] = ()
        self._block_rules: tuple[ApiBlockRule, ...] = ()
        self._ephemeral: dict[str, datetime] = {}

    async def initialize(self) -> None:
        async with self._session_factory() as session:
            policy = await session.scalar(
                select(ApiAccessPolicy).where(ApiAccessPolicy.key == "default")
            )
            if policy is None:
                session.add(ApiAccessPolicy(key="default", mode="development"))
                await session.commit()
        await self.reload()

    async def reload(self) -> None:
        async with self._session_factory() as session:
            policy = await session.scalar(
                select(ApiAccessPolicy).where(ApiAccessPolicy.key == "default")
            )
            tokens = list(
                (
                    await session.scalars(
                        select(ApiServiceToken).order_by(ApiServiceToken.created_at.desc())
                    )
                ).all()
            )
            rules = list(
                (
                    await session.scalars(
                        select(ApiBlockRule).order_by(ApiBlockRule.created_at.desc())
                    )
                ).all()
            )
        self._mode = policy.mode if policy and policy.mode in self.MODES else "development"
        self._tokens = tuple(tokens)
        self._block_rules = tuple(rules)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def live_mode(self) -> bool:
        return self._mode == "live"

    async def set_mode(self, mode: str, updated_by: str | None) -> None:
        normalized = mode.strip().casefold()
        if normalized not in self.MODES:
            raise ValidationError("API mode must be development or live")
        now = datetime.now(UTC)

        def active_token(item: ApiServiceToken) -> bool:
            if not item.enabled:
                return False
            if item.expires_at is None:
                return True
            expires = (
                item.expires_at.replace(tzinfo=UTC)
                if item.expires_at.tzinfo is None
                else item.expires_at.astimezone(UTC)
            )
            return expires > now

        if normalized == "live" and not any(active_token(item) for item in self._tokens):
            raise ValidationError("Create and enable at least one service token before Live Mode")
        async with self._session_factory() as session:
            policy = await session.scalar(
                select(ApiAccessPolicy).where(ApiAccessPolicy.key == "default")
            )
            if policy is None:
                policy = ApiAccessPolicy(key="default")
                session.add(policy)
            policy.mode = normalized
            policy.updated_by = updated_by
            await session.commit()
        await self.reload()

    def _digest(self, token: str) -> str:
        return hmac.new(self._hash_key, token.encode("utf-8"), hashlib.sha256).hexdigest()

    async def create_token(
        self,
        *,
        name: str,
        scopes: list[str],
        description: str | None,
        expires_at: datetime | None,
        created_by: str | None,
    ) -> tuple[ApiServiceToken, str]:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 160:
            raise ValidationError("Token name is required and must be at most 160 characters")
        allowed = {item[0] for item in self.SCOPES}
        normalized_scopes = sorted({item.strip().casefold() for item in scopes if item.strip()})
        invalid = sorted(set(normalized_scopes) - allowed)
        if invalid:
            raise ValidationError(f"Unsupported token scopes: {', '.join(invalid)}")
        if not normalized_scopes:
            raise ValidationError("Select at least one API permission")
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at and expires_at <= datetime.now(UTC):
            raise ValidationError("Token expiry must be in the future")
        raw = "vt_reg_" + secrets.token_urlsafe(36).rstrip("=")
        row = ApiServiceToken(
            name=clean_name,
            token_prefix=raw[:18],
            token_hash=self._digest(raw),
            last_four=raw[-4:],
            enabled=True,
            scopes=normalized_scopes,
            description=(description or "").strip()[:1000] or None,
            expires_at=expires_at,
            created_by=created_by,
            updated_by=created_by,
        )
        async with self._session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        await self.reload()
        return row, raw

    async def set_token_enabled(
        self, token_id: UUID, enabled: bool, updated_by: str | None
    ) -> None:
        async with self._session_factory() as session:
            row = await session.get(ApiServiceToken, token_id)
            if row is None:
                raise NotFoundError("Service token not found")
            row.enabled = enabled
            row.updated_by = updated_by
            await session.commit()
        await self.reload()

    async def delete_token(self, token_id: UUID) -> None:
        async with self._session_factory() as session:
            row = await session.get(ApiServiceToken, token_id)
            if row is None:
                raise NotFoundError("Service token not found")
            await session.delete(row)
            await session.commit()
        await self.reload()

    async def token_rows(self) -> list[ApiServiceToken]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ApiServiceToken).order_by(ApiServiceToken.created_at.desc())
                    )
                ).all()
            )

    @staticmethod
    def normalize_block_rule(value: str) -> tuple[str, str]:
        clean = value.strip().casefold().rstrip(".")
        clean = ApiAccessService.BLOCK_RULE_ALIASES.get(clean, clean)
        if not clean or len(clean) > 255:
            raise ValidationError("Block rule is required and must be at most 255 characters")
        try:
            network = ipaddress.ip_network(clean, strict=False)
            if "/" in clean:
                return str(network), "cidr"
            return str(network.network_address), "ip"
        except ValueError:
            if clean == "localhost":
                return clean, "hostname"
            labels = clean.split(".")
            if len(labels) < 2 or any(
                not label or len(label) > 63 or not label.replace("-", "").isalnum()
                for label in labels
            ):
                raise ValidationError(
                    "Block rule must be an IP address, CIDR, or hostname"
                ) from None
            return clean, "hostname"

    async def add_block_rule(
        self,
        *,
        value: str,
        note: str | None,
        created_by: str | None,
    ) -> ApiBlockRule:
        normalized, rule_type = self.normalize_block_rule(value)
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(ApiBlockRule).where(ApiBlockRule.value == normalized)
            )
            if existing:
                raise ConflictError("This block rule already exists")
            row = ApiBlockRule(
                value=normalized,
                rule_type=rule_type,
                enabled=True,
                note=(note or "").strip()[:500] or None,
                created_by=created_by,
                updated_by=created_by,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
        await self.reload()
        return row

    async def update_block_rule(
        self,
        rule_id: UUID,
        *,
        value: str,
        enabled: bool,
        note: str | None,
        updated_by: str | None,
    ) -> None:
        normalized, rule_type = self.normalize_block_rule(value)
        async with self._session_factory() as session:
            row = await session.get(ApiBlockRule, rule_id)
            if row is None:
                raise NotFoundError("Block rule not found")
            duplicate = await session.scalar(
                select(ApiBlockRule).where(
                    ApiBlockRule.value == normalized,
                    ApiBlockRule.id != rule_id,
                )
            )
            if duplicate:
                raise ConflictError("This block rule already exists")
            row.value = normalized
            row.rule_type = rule_type
            row.enabled = enabled
            row.note = (note or "").strip()[:500] or None
            row.updated_by = updated_by
            await session.commit()
        await self.reload()

    async def delete_block_rule(self, rule_id: UUID) -> None:
        async with self._session_factory() as session:
            result = await session.execute(delete(ApiBlockRule).where(ApiBlockRule.id == rule_id))
            if not result.rowcount:
                raise NotFoundError("Block rule not found")
            await session.commit()
        await self.reload()

    async def block_rule_rows(self) -> list[ApiBlockRule]:
        async with self._session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(ApiBlockRule).order_by(ApiBlockRule.created_at.desc())
                    )
                ).all()
            )

    @staticmethod
    def client_ip(request: Request) -> str | None:
        candidates = [
            request.headers.get("cf-connecting-ip"),
            request.headers.get("x-real-ip"),
            (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip(),
            request.client.host if request.client else None,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return str(ipaddress.ip_address(candidate.strip()))
            except ValueError:
                continue
        return None

    def blocked_reason(self, request: Request) -> str | None:
        client = self.client_ip(request)
        host = (request.url.hostname or "").casefold().rstrip(".")
        client_ip = ipaddress.ip_address(client) if client else None
        for rule in self._block_rules:
            if not rule.enabled:
                continue
            if rule.rule_type == "hostname" and host == rule.value:
                return f"host:{rule.value}"
            if client_ip is None:
                continue
            try:
                if rule.rule_type == "ip" and client_ip == ipaddress.ip_address(rule.value):
                    return f"ip:{rule.value}"
                if rule.rule_type == "cidr" and client_ip in ipaddress.ip_network(
                    rule.value, strict=False
                ):
                    return f"cidr:{rule.value}"
            except ValueError:
                continue
        return None

    @staticmethod
    def bearer_token(request: Request) -> str | None:
        authorization = request.headers.get("authorization", "")
        if authorization.casefold().startswith("bearer "):
            value = authorization[7:].strip()
            return value or None
        value = request.headers.get("x-reghub-token")
        return value.strip() if value and value.strip() else None

    def _ephemeral_valid(self, token: str) -> bool:
        expires = self._ephemeral.get(self._digest(token))
        if expires and expires > datetime.now(UTC):
            return True
        if expires:
            self._ephemeral.pop(self._digest(token), None)
        return False

    def issue_check_token(self, ttl_seconds: int = 60) -> str:
        raw = "vt_reg_check_" + secrets.token_urlsafe(24).rstrip("=")
        self._ephemeral[self._digest(raw)] = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        return raw

    async def authorize(self, request: Request, scope: str) -> None:
        token = self.bearer_token(request)
        if token and self._ephemeral_valid(token):
            return
        blocked = self.blocked_reason(request)
        if blocked:
            raise AuthorizationError("This client is blocked by the RegHub API policy")
        if not self.live_mode:
            return
        if not token:
            raise AuthorizationError("Live API mode requires Authorization: Bearer vt_reg_...")
        digest = self._digest(token)
        now = datetime.now(UTC)
        matched: ApiServiceToken | None = None
        for row in self._tokens:
            if not hmac.compare_digest(row.token_hash, digest):
                continue
            matched = row
            break
        if matched is None or not matched.enabled:
            raise AuthorizationError("The RegHub service token is invalid or disabled")
        expires = matched.expires_at
        if expires:
            expires = (
                expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires.astimezone(UTC)
            )
            if expires <= now:
                raise AuthorizationError("The RegHub service token has expired")
        scopes = set(matched.scopes or [])
        if "*" not in scopes and scope not in scopes:
            raise AuthorizationError(f"The service token does not permit the '{scope}' API")
        async with self._session_factory() as session:
            row = await session.get(ApiServiceToken, matched.id)
            if row:
                row.last_used_at = now
                await session.commit()
