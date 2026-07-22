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
