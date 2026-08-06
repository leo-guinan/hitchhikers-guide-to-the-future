# Idea Nexus Ventures blog decommission preparation

Status: preparation only. No DNS, Traefik router, container, volume, or source deployment has been changed.

## Deployment identity

- Public hostname: `blog.ideanexusventures.com`
- DNS A record at audit time: `5.161.110.155`
- SSH host alias: `nexus-core`
- Application: Ghost 5.130
- Reverse proxy: Traefik Docker container, using the external `traefik_proxy` network
- Compose project: `/opt/indie-agent/apps/blog/compose.yml`
- Compose project name: `blog`
- Ghost container: `blog-ghost-1`
- Database container: `blog-db-1` (MySQL 8.4)
- Persistent volumes: `blog_ghost_content`, `blog_ghost_mysql`
- Traefik router host rule: `Host(`blog.ideanexusventures.com`)`
- TLS: Traefik ACME resolver `le`

## Inventory boundary

Native Ghost records at audit time:

- 41 published posts — all 41 imported into the public guide corpus
- 13 draft posts — not public and intentionally excluded
- 4 published pages — not part of the blog-post migration; review separately before deleting the Ghost deployment
- 3 draft pages — not public and intentionally excluded

The public sitemap contained 41 post URLs, matching the 41-post archive and redirect map.

## Backups

Native backup created on `nexus-core`:

`[REMOTE_BACKUP_ROOT]/blog-ideanexusventures-[BACKUP_TIMESTAMP]/`

Off-host copy:

`[OFF_HOST_BACKUP_ROOT]/blog-ideanexusventures-[BACKUP_TIMESTAMP]/`

Artifacts:

- `ghost-mysql.sql.gz` — SHA-256 `72bfd088a9492389614f4df6ea0bcf12ece08cbf71da62163a9f3ccbfcf4a4b`
- `ghost-content.tar.gz` — SHA-256 `9a9db056e25689a2cadd0ac8fe5ed2e83cec2e30e5eeca7ed6ed98eaaa36b074`
- `native-statuses.txt`
- `SHA256SUMS`

The raw HTML mirror remains at `/Users/leoguinan/Projects/trust-substrate-os/corpora/blog-ideanexusventures-com-ghost-block/`. The public repository contains only the text/provenance derivative because an archived HTML post contains embedded payment markup.

## Guide migration

- Guide source label: `Idea Nexus Ventures archive`
- Imported posts: 41
- Stable ID format: `inv-` + SHA-256 of `inv:<canonical_url>:<archive_id>`
- Native guide host: `https://guide.hitchhikersguidetothefuture.com`
- Redirect map: `data/archives/blog-ideanexusventures-com-ghost-block/redirect-map.csv`
- Live corpus verification: 413 total items; Chroma collection count 413; Idea Nexus count 41.

## Safe decommission sequence

1. Preserve the native backup and off-host copy above; verify both hashes and `gzip -t`.
2. Verify all 41 redirect-map guide URLs return the piece viewer and that the 41 source IDs exist in the guide database.
3. Decide treatment for the four published Ghost pages. Do not delete them as part of a posts-only migration without an explicit disposition.
4. Install a reversible redirect layer for `blog.ideanexusventures.com`, preferably preserving each old post path and redirecting to its mapped guide URL. Keep a catch-all fallback to the guide archive.
5. Monitor redirect responses and guide access before stopping Ghost.
6. Stop the Ghost compose project only after redirect verification. Do not remove either Docker volume.
7. Keep the compose file, database dump, content archive, and redirect map retained for rollback.
8. Only after the retention window and explicit approval: remove the Traefik router, then DNS routing if desired, and archive the deployment directory. Do not delete backups.

## Rollback

- Restore the Traefik router and start the compose project from `/opt/indie-agent/apps/blog/compose.yml`.
- Restore `blog_ghost_mysql` from `ghost-mysql.sql.gz` and `blog_ghost_content` from `ghost-content.tar.gz` only if the live volumes were intentionally removed; they have not been removed in preparation.
- Repoint the hostname to `5.161.110.155` if DNS was changed.
- Remove the redirect layer only after the Ghost health check and a representative post URL pass.

## Current blocker

The migration is ready for an approved reversible redirect/retirement execution, but no live decommission action has been taken. The four published Ghost pages need a separate decision if the entire Ghost site, rather than only the blog-post surface, is being retired.
