# Leo Twitter archive and Community Archive refresh

## One-time import

The public Twitter archive was imported from the June 2026 export for account `leo_guinan` (`1325102346792218629`). It contained 43,452 authored public tweets spanning 2020-11-07 through 2026-06-10.

Guide IDs use `tw-<tweet_id>`. Original X status URLs are stored as provenance in `guide_items.source_url`. Direct messages and other private export sections were not imported.

The source export remains outside the public repository at:

`/var/lib/hgf-api/leo-twitter-archive-tweets.js`

## Daily refresh

`/etc/cron.d/hgf-community-archive` runs daily at 03:17 UTC on `arc-vps`. It queries the read-only Community Archive `enriched_tweets` API for `leo_guinan`, using a two-day overlap against the persisted cursor, deduplicates by tweet ID, upserts SQLite and Chroma, and writes a JSON receipt.

- Script: `/opt/hgf-api/community_archive_daily.py`
- Cursor: `/var/lib/hgf-api/community_archive_cursor.json`
- Receipts: `/var/lib/hgf-api/community_archive_receipts/`
- Log: `/var/log/hgf-community-archive.log`

The updater retrieves the public anon key from the canonical Community Archive agent documentation at runtime. No key is stored in this repository or the cron file. It uses no write access to Community Archive and never changes the source archive.

The Community Archive raw Leo blob was stale at 2025-10-12; the live API returned records through 2026-08-06 during setup, which is why the updater uses the API path.
