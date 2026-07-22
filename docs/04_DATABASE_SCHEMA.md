# Database Schema

Core tables: templates, categories, providers, frameworks, import_history. PostgreSQL JSONB
stores topics, manifest, and immutable import snapshots. Repository URL, template slug, and
external repository ID are unique.

## v0.2.1 additive records

### sync_history additions

```text
trigger
requested_by
changes
```

### screenshot_jobs

```text
id
template_id
status
preview_url
screenshot_url
attempts
requested_by
error_message
response_metadata
completed_at
created_at
updated_at
```

No existing table or column is removed or renamed.

## v0.2.2 additive records

### feature_flags

Runtime feature state, administrator task permission, category, description, and updater.

### integration_configs

Runtime integration state, public base URL/account, encrypted secret, environment fallback,
non-secret JSON config, and updater.

### admin_operations / operation_logs

Persistent task lifecycle, progress, requester, return context, result/error, retry/cancel state, and
ordered live/exportable logs. No existing table or column is removed or renamed.

## v0.2.3 additive records

### api_access_policies

Stores the current `development` or `live` registry API mode and updater identity.

### api_service_tokens

Stores token name, safe prefix/last-four display values, HMAC-SHA256 digest, enabled state, endpoint
scopes, optional expiry, last-used timestamp, description, and audit identities. Raw service tokens
are never stored.

### api_block_rules

Stores enabled IP, CIDR, or hostname rules with optional notes and audit identities.

Migration `20260721_0005_api_access_operations` creates these tables only. No existing table,
column, index, or record is removed or renamed.

## v0.3.0 governance additions

- `admin_operations.requested_roles` records the requesting administrator roles used by audit.
- `audit_chain_states` serializes append order and stores the latest signed chain hash.
- `audit_events` is an append-only, HMAC-signed chain with actor, roles, action, resource, request,
  client, redacted details, signing-key ID and previous/event hashes.
- Catalog ordering indexes and a PostgreSQL GIN index on `templates.topics` support larger catalogs.


## v0.3.1.0 integrity stabilization

Migration `20260722_0007_architecture_stabilization` is additive/non-breaking at the schema level:

- widens `templates.external_repository_id` from 120 to 160 characters to match the model;
- clamps invalid operation progress, quality, star/fork, screenshot-attempt and asset-order values;
- removes exact duplicate template assets while preserving the oldest row;
- adds bounded numeric, API-mode, block-rule, audit-chain and asset-identity constraints;
- removes redundant unique indexes that duplicate existing unique constraints;
- removes obsolete generated deployment intelligence from analysis, version/import snapshots and
  stored generated manifests; and
- recalculates quality breakdowns using registry-only metadata and repository-structure dimensions.

No table or column is removed or renamed. Existing template IDs, slugs, publication states, audit
events, operation history, tokens, integration credentials and relationships are preserved.
