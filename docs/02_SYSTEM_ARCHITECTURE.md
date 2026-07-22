# System Architecture

```text
auth.vib.tools / Keycloak
        -> OIDC + roles
FastAPI / SQLAdmin
        -> Registry SDK
        -> PostgreSQL
        -> optional Redis cache, rate limits and operation queue
        -> standalone RegHub worker
        -> provider APIs / isolated screenshot service
        -> versioned read-only public API
        -> ygit.net
```

Provider identifies a publisher. Framework identifies technology. Integration connects an external
system. Registry Adapter imports metadata. These concepts remain separate.

RegHub web and worker use the same source, PostgreSQL and runtime configuration. The compatible
default executes operations in the web process. Production Redis mode separates request handling from
long-running imports, sync and media tasks.

## v0.3.1.0 registry-analysis boundary

Repository analysis remains an internal RegHub registry capability. It identifies framework,
language, package manager, license, topics, README-derived metadata, repository metadata, preview
media, quality and security signals. It does not decide build, start, runtime, environment or
deployment behavior. YGIT remains the owner of those decisions. No new service or repository is
introduced.
