# Identity and payment rails

The Guide uses two separate infrastructure boundaries.

## Auth

HGF returning-traveler access redirects to:

`https://auth.ideanexusventures.com/login`

with:

- `workspace_id=org:idea-nexus`
- `property_id=x:marvin-panics`
- `return_to=https://hitchhikersguidetothefuture.com/enter/`

The auth service returns a short-lived `preview_handoff`; the HGF Pages relay sends it to the HGF API, which redeems it server-to-server and creates an opaque, node-scoped application session. The browser receives only an HTTP-only `hgf_session` cookie. The preview claim is never used as browser authority.

## Payments

Reusable service:

`https://payments.ideanexusventures.com`

Internal service:

`127.0.0.1:8845`

Routes:

- `GET /health`
- protected `POST /v1/checkout/sessions`
- protected `GET /v1/entitlements/{subject_id}`
- signed `POST /v1/webhooks/stripe`

The HGF Cloudflare Pages Function at `/api/payments/checkout` is the browser-facing relay. It keeps `PAYMENTS_SERVICE_TOKEN` in a Pages secret and forwards only approved HGF-origin requests to the payment service.

Checkout remains fail-closed until `HGF_STRIPE_PRICE_ID` is configured in the Pages project. A missing price returns `503 membership price is not configured`; it cannot create a charge. Stripe secrets and the payment service token remain server-side.

## Verification boundary

A green health check proves liveness, not entitlement correctness. Before the first real charge, verify:

1. a specific node price is approved;
2. Checkout creates a session with the intended node and subject metadata;
3. Stripe webhook signature verification succeeds;
4. duplicate webhook delivery is idempotent;
5. the resulting entitlement is readable only by the authenticated application service;
6. the private diary session is separate from the read-only auth preview claim.
