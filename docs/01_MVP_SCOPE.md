# MVP Scope History and Current Product Boundary

The original v0.1 MVP included OIDC login, SQLAdmin, GitHub metadata import, registry CRUD, a public
API and Draft/Published/Disabled lifecycle.

RegHub has since added Smart Registry analysis, GitLab/Bitbucket/local adapters, runtime Settings,
Operations, media management and API access controls. Those capabilities are now part of the current
product and the old exclusion list is historical only.

The permanent boundary remains unchanged:

- RegHub stores, analyzes, curates, governs and publishes template metadata.
- RegHub never clones untrusted repositories, installs dependencies, builds templates, provisions
  hosting or deploys user projects.
- Identity belongs to `auth.vib.tools`; deployment belongs to `ygit.net`.
