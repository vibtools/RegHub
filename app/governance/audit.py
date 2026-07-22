import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.core.security import AdminIdentity
from app.models.audit_event import AuditChainState, AuditEvent


@dataclass(frozen=True, slots=True)
class AuditVerification:
    valid: bool
    checked: int
    total: int
    complete: bool
    first_invalid_sequence: int | None = None
    message: str = "Audit chain is valid"


class AuditService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        signing_keys: list[str] | tuple[str, ...] | str,
    ) -> None:
        self._session_factory = session_factory
        raw_keys = [signing_keys] if isinstance(signing_keys, str) else list(signing_keys)
        if not raw_keys:
            raise ValueError("At least one audit signing key is required")
        self._keys: dict[str, bytes] = {}
        for raw in raw_keys:
            key_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
            self._keys[key_id] = hashlib.sha256(("reghub-audit-v1:" + raw).encode()).digest()
        self.primary_key_id = next(iter(self._keys))

    @staticmethod
    def _safe_details(value: dict[str, Any] | None) -> dict[str, Any]:
        forbidden = {"secret", "token", "password", "credential", "authorization", "api_key"}

        def sanitize(item: Any, *, depth: int = 0) -> Any:
            if depth > 6:
                return "[MAX_DEPTH]"
            if isinstance(item, dict):
                result: dict[str, Any] = {}
                for key, nested in list(item.items())[:100]:
                    normalized = str(key).casefold()
                    result[str(key)] = (
                        "[REDACTED]"
                        if any(part in normalized for part in forbidden)
                        else sanitize(nested, depth=depth + 1)
                    )
                return result
            if isinstance(item, (list, tuple, set)):
                return [sanitize(nested, depth=depth + 1) for nested in list(item)[:100]]
            if isinstance(item, str):
                return item[:4000]
            if item is None or isinstance(item, (bool, int, float)):
                return item
            return str(item)[:4000]

        return sanitize(value or {})

    def _digest(self, payload: dict[str, Any], key_id: str) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        key = self._keys.get(key_id)
        if key is None:
            raise KeyError(key_id)
        return hmac.new(key, canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def _client_ip(request: Request | None) -> str | None:
        if request is None or request.client is None:
            return None
        return request.client.host

    async def append(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        outcome: str = "succeeded",
        identity: AdminIdentity | None = None,
        actor_subject: str | None = None,
        actor_email: str | None = None,
        actor_roles: list[str] | None = None,
        request: Request | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        occurred_at = datetime.now(UTC)
        safe_details = self._safe_details(details)
        normalized_action = action.strip()[:160]
        normalized_resource_type = resource_type.strip()[:120]
        normalized_resource_id = resource_id.strip()[:255] if resource_id else None
        normalized_outcome = outcome.strip()[:32] or "succeeded"
        normalized_subject = identity.subject if identity else actor_subject
        normalized_email = identity.email if identity else actor_email
        normalized_roles = list(identity.roles) if identity else list(actor_roles or [])
        if normalized_subject:
            normalized_subject = normalized_subject[:255]
        if normalized_email:
            normalized_email = normalized_email[:320]
        normalized_roles = [str(item)[:80] for item in normalized_roles[:50]]
        request_id = getattr(getattr(request, "state", None), "request_id", None)
        if request_id:
            request_id = str(request_id)[:100]
        client_ip = self._client_ip(request)
        if client_ip:
            client_ip = client_ip[:80]
        async with self._session_factory() as session:
            state = await session.scalar(
                select(AuditChainState).where(AuditChainState.id == 1).with_for_update()
            )
            if state is None:
                state = AuditChainState(
                    id=1,
                    last_sequence=0,
                    last_hash="GENESIS",
                    updated_at=occurred_at,
                )
                session.add(state)
                await session.flush()
            sequence = int(state.last_sequence) + 1
            payload = {
                "sequence": sequence,
                "occurred_at": occurred_at.isoformat(),
                "actor_subject": normalized_subject,
                "actor_email": normalized_email,
                "actor_roles": normalized_roles,
                "action": normalized_action,
                "resource_type": normalized_resource_type,
                "resource_id": normalized_resource_id,
                "outcome": normalized_outcome,
                "request_id": request_id,
                "client_ip": client_ip,
                "details": safe_details,
                "signing_key_id": self.primary_key_id,
                "previous_hash": state.last_hash,
            }
            event_hash = self._digest(payload, self.primary_key_id)
            event = AuditEvent(
                sequence=sequence,
                occurred_at=occurred_at,
                actor_subject=payload["actor_subject"],
                actor_email=payload["actor_email"],
                actor_roles=payload["actor_roles"],
                action=normalized_action,
                resource_type=normalized_resource_type,
                resource_id=normalized_resource_id,
                outcome=normalized_outcome,
                request_id=payload["request_id"],
                client_ip=payload["client_ip"],
                details=safe_details,
                signing_key_id=self.primary_key_id,
                previous_hash=state.last_hash,
                event_hash=event_hash,
            )
            session.add(event)
            state.last_sequence = sequence
            state.last_hash = event_hash
            state.updated_at = occurred_at
            await session.commit()
            await session.refresh(event)
            return event

    async def verify(self, limit: int = 100_000) -> AuditVerification:
        safe_limit = max(1, min(limit, 1_000_000))
        async with self._session_factory() as session:
            total = int(await session.scalar(select(func.count(AuditEvent.id))) or 0)
            state = await session.get(AuditChainState, 1)
            events = list(
                (
                    await session.scalars(
                        select(AuditEvent).order_by(AuditEvent.sequence).limit(safe_limit)
                    )
                ).all()
            )
        previous_hash = "GENESIS"
        for index, event in enumerate(events, start=1):
            if event.sequence != index:
                return AuditVerification(
                    valid=False,
                    checked=index,
                    total=total,
                    complete=index >= total,
                    first_invalid_sequence=event.sequence,
                    message=(
                        f"Audit sequence gap or reordering detected at sequence {event.sequence}"
                    ),
                )
            occurred_at = event.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=UTC)
            else:
                occurred_at = occurred_at.astimezone(UTC)
            payload = {
                "sequence": event.sequence,
                "occurred_at": occurred_at.isoformat(),
                "actor_subject": event.actor_subject,
                "actor_email": event.actor_email,
                "actor_roles": list(event.actor_roles or []),
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "outcome": event.outcome,
                "request_id": event.request_id,
                "client_ip": event.client_ip,
                "details": event.details or {},
                "signing_key_id": event.signing_key_id,
                "previous_hash": event.previous_hash,
            }
            try:
                expected_hash = self._digest(payload, event.signing_key_id)
            except KeyError:
                return AuditVerification(
                    valid=False,
                    checked=index,
                    total=total,
                    complete=index >= total,
                    first_invalid_sequence=event.sequence,
                    message=(
                        f"Audit signing key '{event.signing_key_id}' is unavailable at "
                        f"sequence {event.sequence}"
                    ),
                )
            if event.previous_hash != previous_hash or not hmac.compare_digest(
                event.event_hash, expected_hash
            ):
                return AuditVerification(
                    valid=False,
                    checked=index,
                    total=total,
                    complete=index >= total,
                    first_invalid_sequence=event.sequence,
                    message=f"Audit chain validation failed at sequence {event.sequence}",
                )
            previous_hash = event.event_hash
        complete = len(events) >= total
        if complete:
            expected_sequence = events[-1].sequence if events else 0
            expected_hash = events[-1].event_hash if events else "GENESIS"
            if (
                state is None
                or int(state.last_sequence) != expected_sequence
                or state.last_hash != expected_hash
            ):
                return AuditVerification(
                    valid=False,
                    checked=len(events),
                    total=total,
                    complete=True,
                    first_invalid_sequence=expected_sequence + 1,
                    message="Audit chain state does not match the stored event tail",
                )
        return AuditVerification(
            valid=True,
            checked=len(events),
            total=total,
            complete=complete,
            message=(
                "Audit chain is valid"
                if complete
                else f"Audit chain prefix is valid; {total - len(events)} event(s) were not scanned"
            ),
        )
