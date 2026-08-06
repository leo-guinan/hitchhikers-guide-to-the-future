# Substack migration archive

These are public Substack migration receipts for full-text archives normalized and imported into the Hitchhiker's Guide corpus. The full normalized archives are retained outside this public repository because embedded public media URLs trigger the repository secret scanner.

## Publications

- `engineering_generosity.json`: 96 full-text posts from `https://engineeringgenerosity.substack.com`
- `hitchhiker_to_the_future.json`: 103 full-text posts from `https://hitchhikertothefuture.substack.com`

Two public records were excluded because their live pages contain an empty `<p></p>` body and zero word count:

- Engineering Generosity: `what-if-we-built-an-internet-where`
- Hitchhiker to the Future: `the-winning-submission-to-the-boltnew`

Original Substack URLs are retained as `canonical_url` provenance. Guide IDs use the stable `sub-` prefix and are generated from the canonical URL. Full text is preserved in SQLite; Chroma documents use the existing 15,000-byte embedding boundary where required.

Full normalized archives: `/Users/leoguinan/Projects/trust-substrate-os/corpora/substack-migration-20260806/`
