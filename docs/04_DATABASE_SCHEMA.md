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
