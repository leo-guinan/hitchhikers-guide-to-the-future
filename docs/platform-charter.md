# Platform Charter

## 1. Product sentence

The Hitchhiker's Guide to the Future is a network of paid personal futures: writers publish a public guide, keep a private diary, and choose the price and permissions under which other people may enter their private thinking.

The promise is not that writing predicts the future. The promise is that repeated, searchable writing creates a closer relationship with the future one is trying to make.

## 2. Vocabulary

- **Traveler** — an account holder.
- **Node** — one traveler's publication, diary, pricing, and access policy.
- **Public guide** — the node's public newsletter/blog entries.
- **Private diary** — entries visible only to the writer by default.
- **Membership** — a paid recurring entitlement. A membership in a host node may also grant the right to create a node, if the host's offer includes that capability.
- **Founding invitation** — a gifted or explicitly granted membership used to seed a trusted first cohort.
- **Node passport** — the capability to create and operate a node. It is not the same thing as access to every other node's private diary.
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
9. A membership offer may include a node passport: permission to create one node and operate it under platform rules.
10. A node passport does not automatically grant access to the private diaries of other nodes.
11. Revenue belongs to the node owner, less payment, platform, tax, refund, and dispute costs.
12. Membership access is entitlement-based, not client-side boolean state.
13. The platform must be able to suspend node creation, search, publication, and billing independently.
14. No launch promise depends on every node having a different payment rail. The first cohort uses one billing provider and one currency unless an experiment proves otherwise.

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

### D4 — A paid host membership can grant a node passport

**Decision:** Membership in the first host node can include permission to create one personal node. This is the network's primary growth loop: a traveler enters through a valuable node, then becomes a potential source of another valuable node.

**Entitlement shape:**

- `node_read` — access to the host node's private corpus, subject to host policy;
- `node_passport` — permission to create one node;
- `node_operate` — permission to edit, publish, price, and configure the created node;
- `atlas_read` — permission to search the network, if separately granted;
- `atlas_contribute` — permission for the node's opted-in corpora to be indexed.

The passport is consumed once at node creation. The resulting node remains owned and operated by its creator while the creator's membership remains in good standing, subject to a defined grace period and export path. We should not silently delete a person's intellectual archive because a card failed.

**Open commercial question:** whether the passport is permanently retained after creation or requires an active host membership. The first cohort should use a 30-day grace period after cancellation and make the rule explicit at checkout.

### D5 — Separate node membership from Atlas membership

**Decision:** A reader can subscribe to a node, receive a node passport, and still not receive Atlas access. Atlas search remains a separate entitlement.

**Launch simplification:** Leo's host membership can include Atlas access for the founding cohort as an explicit benefit, while gifted founding invitations can be granted the same or a narrower capability bundle. We should not build a marketplace of hundreds of independent micro-checkouts before proving that network search has repeat use.

**Longer-term experiment:** node owners can choose whether their own membership includes Atlas access, node-passport rights, both, or neither. This is an experiment, not a launch invariant.

### D6 — Seed the network deliberately, not indiscriminately

**Decision:** The first cohort is a curated network of valuable, somewhat prolific thinkers whose writing adds distinct dimensions of observation. It is not an open signup funnel at launch.

The seed cohort should be selected for:

- demonstrated ability to produce sustained original writing;
- distinct subject position or lived context;
- willingness to make some thinking legible to others;
- comfort with explicit privacy and pricing boundaries;
- capacity to maintain a node rather than merely claim one;
- evidence of reciprocal intellectual value, not just audience size.

Leo may gift founding invitations based on prior relationships. Every gifted invitation still creates a normal account, membership, policy record, and receipt. Relationship is the reason for the grant; it is not an authorization bypass.

The network's purpose is dimensional coverage, not ideological agreement. Cohort selection should record the intended dimension and the reason for inclusion, while avoiding a score that pretends human significance can be ranked cleanly.

**Seed-cohort artifact:** maintain a private invitation ledger containing invitee, relationship basis, intended dimension, capability bundle, inviter, date, and review outcome. Do not publish private relationship notes.

### D7 — Writer-controlled search exposure has three independent switches

For every node:

1. include public entries in Atlas;
2. include private entries in Atlas for entitled readers only;
3. include private entries in Atlas for the broader Atlas cohort with redacted/snippet-only results.

Default: all false for private material; public Atlas inclusion may be suggested during onboarding but requires confirmation.

### D8 — Use Stripe Connect for money movement, but hide it behind a billing module

**Decision:** Stripe Connect Express or equivalent connected-account model, with platform fees and destination transfers represented in our own ledger.

**Non-negotiable:** Stripe state is not the product entitlement. Webhook events update our ledger; reconciliation compares provider state, internal state, and receipts.

**Launch scope:** one currency, monthly memberships, platform-managed refunds and disputes, owner payout dashboard after reconciliation exists.

### D9 — Custom domains are a first-class node property

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

CapabilityGrant
  id, traveler_id, source_node_id, capability, target_node_id
  source, valid_from, valid_until, revoked_at, policy_version

NodePassport
  id, traveler_id, grant_id, status, consumed_at, created_node_id

FoundingInvitation
  id, inviter_id, invitee_id, capability_bundle, relationship_basis
  intended_dimension, status, created_at, accepted_at

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

### Founding member

- membership and capability bundle;
- node-passport claim/create flow;
- network policy acknowledgment;
- Atlas participation controls;
- invitation status, if granted invitation rights later.

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

Cohort target: 10–20 writers, beginning with Leo's host node plus a curated set of paid or gifted founding members. Each accepted founding member may create one node if their capability bundle includes a node passport. Use one billing provider, one primary currency, and one Atlas policy configuration at a time.

Measure before expanding:

- writer conversion from first private entry to setting a price;
- membership-to-node conversion: percentage of members who claim their passport and create a node;
- node survival: percentage of created nodes with at least three entries in 30 days;
- dimension coverage: qualitative map of distinct domains, contexts, and methods represented;
- gifted-member activation and retention versus paid-member activation;
- percentage of writers who publish at least one public entry;
- paid conversion and 30-day retention;
- private entries per paid member per week;
- Atlas searches per active member;
- percentage of Atlas results opened;
- access-denial false positives/negatives;
- revocation-to-deindex latency;
- payment reconciliation exceptions;
- support burden per node.

The central falsifiers: if members value Leo's node but do not claim or use their own node, node creation is a decorative perk; if the resulting nodes do not produce sustained writing, the network is not gaining dimensions; if people will pay for a node but do not use Atlas, the network is a garnish, not the product. If Atlas searches are frequent but result opens are low, retrieval or trust is broken. If writers refuse private opt-in, the default architecture is still correct; the market has answered a different question.

## 9. Explicit non-goals for launch

- no token or blockchain settlement;
- no arbitrary peer-to-peer pricing rails;
- no automatic right to create unlimited nodes;
- no public ranking of thinkers or forced "dimension" taxonomy;
- no global model training on private diaries;
- no autonomous publication or autonomous price changes;
- no public leaderboard of private-thought value;
- no multi-region active-active deployment;
- no microservices split;
- no promise that semantic search reveals truth, only that it finds relevant authorized writing.

## 10. Open decisions that need Leo's sign-off

1. **Passport persistence:** does a created node remain operable permanently after the host membership ends, or only after a grace period? Recommendation: 30-day grace period, then read-only/export until reactivation.
2. **Atlas commercial shape:** include Atlas in Leo's host membership for the founding cohort, or keep it invite-only at first? Recommendation: include it for the curated founding cohort, but retain a separate capability flag.
3. **Private search result shape:** full text for members of a node; what, if anything, may non-members see from opted-in private corpora?
4. **Writer payout:** immediate transfer after payment, or delayed payout after refund/dispute window and reconciliation?
5. **Identity:** email magic link first, or social login in the first cohort?
6. **Backfill boundary:** which prior corpus is in scope, and what categories are automatically excluded before human review?
7. **First deployment rail:** existing infrastructure or a fresh Cloudflare/VPS deployment? This changes domain and operational work.

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
