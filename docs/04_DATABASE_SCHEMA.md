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
