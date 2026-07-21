# RegHub v0.2.3.4 Release Manifest

## Baseline

- Built from the live v0.2.3.3 Settings 404 and responsiveness hotfix.
- Preserves all public API paths, Settings controls, service tokens, Keycloak behavior, template IDs,
  publication states, operation history, database objects, Coolify variables, and deployment boundaries.
- No database migration is required.

## Release scope

- Import-completion View Template action.
- Responsive template result card in the operation side panel.
- Friendly Already found / Skipped duplicate-import state.
- Continue to update template action using the existing source-sync workflow.
- Live operation status payload enrichment with safe template summary data.

## Safety

- Duplicate import never creates a second template record.
- Continue to update queues source synchronization and preserves curated template identity,
  classification, featured state, and publication status.
- No repository clone, install, build, or execution behavior was added.
