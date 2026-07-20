# Database Schema

Core tables: templates, categories, providers, frameworks, import_history. PostgreSQL JSONB
stores topics, manifest, and immutable import snapshots. Repository URL, template slug, and
external repository ID are unique.
