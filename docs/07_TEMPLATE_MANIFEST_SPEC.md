# Template Manifest Specification

RegHub accepts Manifest v1 and v2. The manifest is descriptive only. YGIT interprets it; RegHub
never executes build or deployment commands.

## Manifest 1.0 — preserved

```json
{
  "schema_version": "1.0",
  "framework": "astro",
  "repository": "https://github.com/owner/repository",
  "branch": "main",
  "deploy": {"type": "static"}
}
```

## Manifest 2.0 — Smart Registry

```json
{
  "schema_version": "2.0",
  "name": "Astro Starter",
  "framework": "astro",
  "framework_version": "5.2.1",
  "language": "TypeScript",
  "package_manager": "pnpm",
  "repository": "https://github.com/owner/repository",
  "branch": "main",
  "build": {
    "command": "pnpm build",
    "start_command": "pnpm preview"
  },
  "deploy": {"type": "static"},
  "environment": [
    {
      "key": "PUBLIC_API_URL",
      "required": false,
      "secret": false
    }
  ]
}
```

Supported repository hosts are GitHub, GitLab, and Bitbucket over HTTPS. Local import references are
accepted for Draft records but must be replaced by a deployable HTTPS repository before publication.


## v0.3.1.0 generated-manifest policy

The v1/v2 schemas above remain accepted for backward compatibility. RegHub may store and serve an
explicitly supplied compatible manifest, but RegHub no longer invents build, start, environment,
runtime or deployment recommendations from repository analysis. Newly generated manifests are
deployment-neutral (`deploy.type = unknown`), omit `build`, and use an empty v2 `environment` list.
YGIT interprets deployment requirements outside the registry boundary.
