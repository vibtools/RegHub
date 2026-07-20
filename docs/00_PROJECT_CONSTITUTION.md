# RegHub Project Constitution

RegHub is a registry platform. It stores, curates, and publishes template metadata.
It never builds applications, provisions hosting, or calls Coolify. Identity belongs to
`auth.vib.tools`; deployment belongs to `ygit.net`; repository metadata belongs to adapters.

The Registry SDK is the business-logic boundary. HTTP routers and SQLAdmin are adapters to it.
Public API contracts are versioned and backward compatible inside a major version.
