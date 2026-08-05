# Platform Charter

## 1. Product sentence

The Hitchhiker's Guide to the Future is a network of paid personal futures: writers publish a public guide, keep a private diary, and choose the price and permissions under which other people may enter their private thinking.

The promise is not that writing predicts the future. The promise is that repeated, searchable writing creates a closer relationship with the future one is trying to make.

## 2. Vocabulary

- **Traveler** — an account holder.
- **Node** — one traveler's publication, diary, pricing, and access policy.
- **Public guide** — the node's public newsletter/blog entries.
- **Private diary** — entries visible only to the writer by default.
- **Membership** — a paid recurring entitlement to one node's private diary, subject to that node's policy.
- **Atlas** — the semantic search surface over explicitly participating nodes.
- **Endpoint** — the access boundary for a node. A traveler enters a node through its membership endpoint; Atlas access is another entitlement, not an accidental side effect.
- **Waymark** — an immutable publication/version receipt for an entry.

## 3. Invariants

### Privacy and consent

1. New diary entries are private by default.
2. Public publication is an explicit action, never a side effect of saving.
3. Atlas inclusion is an explicit node-level opt-in, with separate controls for private entries and public entries.
4. A search result must carry its source node, access reason, corpus class, and policy version.
5. Search never returns raw private text from a node unless the requesting traveler has a currently valid entitlement for that node and the node permits that result shape.
6. A writer can revoke Atlas inclusion. Revocation stops new indexing immediately and schedules deletion of derived embeddings and cached snippets; it does not rewrite historical receipts.
7. Private content is not used for global model training without a separate, affirmative consent that can be revoked.

### Commerce

8. Each node has an owner-set price and billing cadence.
9. Revenue belongs to the node owner, less payment, platform, tax, refund, and dispute costs.
10. Membership access is entitlement-based, not client-side boolean state.
11. The platform must be able to suspend search, publication, and billing independently.
12. No launch promise depends on every node having a different payment rail. The first cohort uses one billing provider and one currency unless an experiment proves otherwise.

### Provenance and accountability

13. Every write, publication, policy change, membership grant, search, revocation, import, and deletion request creates an append-only receipt.
14. Content edits create new versions. We do not pretend the old version never existed.
15. Imports preserve source, source timestamp when known, import timestamp, transformation, and operator.
16. Any generated summary or embedding is derived data with model/version provenance, not canonical text.

### Product shape

17. The cover page stays quiet: premise, invitation, price/CTA. Functional surfaces live behind distinct routes.
18. The first cohort must be operable by one human without a distributed-systems opera.
19. The first release optimizes for trustworthy access and receipts before network effects.

## 4. Launch decisions

### D1 — Start as a modular monolith

**Decision:** One deployable application, one primary database, background jobs in the same repository, clear domain modules.

**Why:** The first risk is not throughput. It is whether writers will price access, whether members will pay, and whether cross-node search feels useful without feeling invasive. Microservices would add failure surfaces before the product has earned them.

**Initial modules:** identity, nodes, entries, publications, memberships, billing, search, imports, domains, receipts, admin.

**Split trigger:** extract a service only after a measured bottleneck, an independent security boundary, or an operational need that cannot be handled inside the monolith.

### D2 — PostgreSQL is the source of truth; use pgvector first

**Decision:** PostgreSQL for transactional data, full-text search, vector embeddings, and policy joins. Object storage for large media and import payloads.

**Why:** Access control and search results must be joined against current entitlements and node policy. A separate search system on day one invites stale permission leaks.

**Search contract:** hybrid retrieval (Postgres full text + vector similarity), filtered by node participation, corpus class, entitlement, and policy version before snippets are assembled.

**Later option:** move vector retrieval to a dedicated system only when query latency or corpus size proves the need. The authorization query remains authoritative.

### D3 — Model access as capability grants, not “paid = true”

A membership creates a time-bounded entitlement with:

- `traveler_id`
- `node_id`
- `scope` (`private_read`, `atlas_read`, `public_read`)
- `corpus_classes`
- `valid_from`, `valid_until`
- `source` (subscription, gift, admin grant)
- `revoked_at`
- policy version accepted at grant time

The API re-evaluates the grant server-side for every private read and search request. The browser is not trusted to enforce a paywall.

### D4 — Separate node membership from Atlas membership

**Decision:** A reader can subscribe to a node without joining the Atlas, and can join the Atlas only under a defined network-access plan.

**Launch simplification:** The first cohort may include Atlas access as a platform-level plan or invite-only entitlement. We should not build a marketplace of hundreds of independent micro-checkouts before proving that network search has repeat use.

**Longer-term experiment:** node owners can choose whether Atlas access is included, excluded, or priced as an add-on. This is an experiment, not a launch invariant.

### D5 — Writer-controlled search exposure has three independent switches

For every node:

1. include public entries in Atlas;
2. include private entries in Atlas for entitled readers only;
3. include private entries in Atlas for the broader Atlas cohort with redacted/snippet-only results.

Default: all false for private material; public Atlas inclusion may be suggested during onboarding but requires confirmation.

### D6 — Use Stripe Connect for money movement, but hide it behind a billing module

**Decision:** Stripe Connect Express or equivalent connected-account model, with platform fees and destination transfers represented in our own ledger.

**Non-negotiable:** Stripe state is not the product entitlement. Webhook events update our ledger; reconciliation compares provider state, internal state, and receipts.

**Launch scope:** one currency, monthly memberships, platform-managed refunds and disputes, owner payout dashboard after reconciliation exists.

### D7 — Custom domains are a first-class node property

**Decision:** Every node has a platform slug immediately. Custom domains are supported through a domain-verification record and an edge routing layer.

**Initial routing:**

- `guide.hitchhikersguidetothefuture.com` → first node;
- `node.platform-domain.example` → any node's stable fallback;
- writer custom domain → verified mapping to exactly one node.

**Verification:** DNS TXT or CNAME challenge before activation. Reject domain reuse. Keep canonical URLs stable so a domain change does not destroy publication links.

**Important:** Do not claim custom domains are complete until TLS issuance, apex/www behavior, host-header routing, canonical URL generation, and domain removal are tested.

### D8 — Backfill is an import pipeline, not a copy-paste task

Backfill stages:

1. inventory source collections;
2. classify each item as private, public candidate, or exclude;
3. preserve source metadata and original timestamps;
4. redact secrets, private third-party information, and unapproved identities;
5. create draft entries with provenance;
6. human review;
7. publish selected entries;
8. embed only according to the node's current policy;
9. record import receipts and a manifest hash.

No historic work is published merely because it exists in an archive.

## 5. Minimum domain model

```text
Traveler
  id, email, display_name, created_at, status

Node
  id, owner_id, slug, title, description, timezone
  default_visibility, atlas_policy, membership_price, billing_interval
  status, created_at

Entry
  id, node_id, author_id, visibility, title, body, created_at, updated_at

EntryVersion
  id, entry_id, version, body, content_hash, created_at, created_by

Publication
  id, entry_version_id, canonical_path, published_at, unpublished_at

Membership
  id, traveler_id, node_id, provider_customer_id, status
  current_period_end, created_at, canceled_at

Entitlement
  id, traveler_id, node_id, scope, corpus_class
  valid_from, valid_until, revoked_at, policy_version

AtlasDocument
  id, entry_version_id, node_id, corpus_class, embedding_model
  embedding, search_text, indexed_at, removed_at, policy_version

DomainMapping
  id, node_id, hostname, verification_token, status, verified_at

Receipt
  id, actor_id, event_type, subject_type, subject_id
  payload_hash, metadata, created_at
```

The model intentionally keeps canonical content, derived search data, commerce state, and receipts separate. The database will be less poetic than the landing page. That is its job.

## 6. First cohort product surface

### Public

- cover/premise;
- public guide index;
- entry page with canonical URL;
- author/node page;
- membership price and checkout CTA;
- public explanation of Atlas policy.

### Writer

- diary composer and version history;
- draft/public/private controls;
- price and membership settings;
- Atlas exposure settings;
- member list and access status;
- import review queue;
- domain settings;
- receipts/audit view.

### Member

- node access status;
- private diary reader/search for nodes joined;
- Atlas search if entitled;
- result explanations: why this result is visible;
- export and cancellation controls.

### Operator

- node/member/entitlement lookup;
- webhook and reconciliation status;
- import/job failures;
- domain verification failures;
- revoke/suspend controls with reason;
- audit trail.

## 7. Route shape

```text
/                         cover
/guide                     public entries
/guide/:entry              public entry
/enter                     sign-in and checkout
/app                       writer/member home
/app/diary                 private diary
/app/atlas                 semantic network search
/app/settings              pricing, policy, domains
/app/imports               backfill review
/app/receipts              audit view
/api/v1/...                versioned API
```

Custom domains resolve to the node's public surface and authenticated app routes without exposing tenant IDs in URLs.

## 8. First cohort experiment

Cohort target: 10–20 writers, invited members, one billing provider, one primary currency, one Atlas policy configuration at a time.

Measure before expanding:

- writer conversion from first private entry to setting a price;
- percentage of writers who publish at least one public entry;
- paid conversion and 30-day retention;
- private entries per paid member per week;
- Atlas searches per active member;
- percentage of Atlas results opened;
- access-denial false positives/negatives;
- revocation-to-deindex latency;
- payment reconciliation exceptions;
- support burden per node.

The central falsifier: if people will pay for a node but do not use Atlas, the network is a garnish, not the product. If Atlas searches are frequent but result opens are low, retrieval or trust is broken. If writers refuse private opt-in, the default architecture is still correct; the market has answered a different question.

## 9. Explicit non-goals for launch

- no token or blockchain settlement;
- no arbitrary peer-to-peer pricing rails;
- no global model training on private diaries;
- no autonomous publication or autonomous price changes;
- no public leaderboard of private-thought value;
- no multi-region active-active deployment;
- no microservices split;
- no promise that semantic search reveals truth, only that it finds relevant authorized writing.

## 10. Open decisions that need Leo's sign-off

1. **Atlas commercial shape:** platform-level Atlas membership for the cohort, or pay-per-node Atlas add-on from day one?
2. **Private search result shape:** full text for members of a node; what, if anything, may non-members see from opted-in private corpora?
3. **Writer payout:** immediate transfer after payment, or delayed payout after refund/dispute window and reconciliation?
4. **Identity:** email magic link first, or social login in the first cohort?
5. **Backfill boundary:** which prior corpus is in scope, and what categories are automatically excluded before human review?
6. **First deployment rail:** existing infrastructure or a fresh Cloudflare/VPS deployment? This changes domain and operational work.

## 11. Build order

1. Freeze this charter and the entitlement/policy vocabulary.
2. Create the new repository and local development environment.
3. Implement typed domain models and migrations.
4. Implement identity, node creation, and private/public entry versioning.
5. Implement receipts and policy evaluation before search.
6. Add public publication and the first guide node.
7. Add Stripe checkout, webhook ingestion, ledger, and entitlement tests.
8. Add member-only diary reads.
9. Add Atlas indexing and hybrid search with authorization filters.
10. Add import manifests, review queue, and controlled backfill.
11. Add custom domain verification and routing.
12. Run the cohort with operator receipts and a written outcome review.

## 12. Acceptance gate for the first real release

A release is not ready because the cover looks good. It is ready when all of the following have real tests and receipts:

- an unpaid traveler cannot read a private entry;
- a paid traveler can read only the node and corpus they are entitled to;
- a revoked membership fails immediately at the API;
- Atlas returns no result from a node that opted out;
- an opted-in private result is filtered by current entitlement before snippet generation;
- an edit creates a new version and preserves the old receipt;
- a backfill item can be held as draft and traced to its source;
- a Stripe webhook can be replayed idempotently;
- internal ledger and provider state can be reconciled;
- a verified custom domain routes to the correct node;
- a removed domain no longer serves authenticated tenant content;
- every externally visible write has a receipt.

The thesis means nothing without the artifact. The artifact means nothing without the access test.
