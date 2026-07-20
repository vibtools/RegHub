# System Architecture

`auth.vib.tools -> OIDC -> FastAPI/SQLAdmin -> Registry SDK -> PostgreSQL -> public API -> ygit.net`

Provider identifies a publisher. Framework identifies technology. Integration connects an
external system. Registry Adapter imports metadata. These concepts must remain separate.
