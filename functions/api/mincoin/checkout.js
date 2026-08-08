const ALLOWED_ORIGINS = new Set([
  'https://hitchhikersguidetothefuture.com',
  'https://www.hitchhikersguidetothefuture.com',
]);

function cors(request) {
  const origin = request.headers.get('Origin');
  return origin && ALLOWED_ORIGINS.has(origin)
    ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' }
    : {};
}

function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
  });
}

export async function onRequestOptions({ request }) {
  return new Response(null, {
    status: 204,
    headers: {
      ...cors(request),
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'content-type',
    },
  });
}

export async function onRequestPost({ request, env }) {
  const headers = cors(request);
  const origin = request.headers.get('Origin');
  if (!origin || !ALLOWED_ORIGINS.has(origin)) return json({ error: 'origin not allowed' }, 403, headers);
  if (!env.PAYMENTS_SERVICE_TOKEN || !env.PAYMENTS_SERVICE_URL) {
    return json({ error: 'payment relay is not configured' }, 503, headers);
  }
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400, headers); }
  const amountCents = body && body.amount_cents;
  if (!Number.isInteger(amountCents) || amountCents < 1 || amountCents > 5_000_000) {
    return json({ error: 'enter a valid positive amount at or below the cap' }, 400, headers);
  }
  const contributionId = `mincoin:${crypto.randomUUID()}`;
  const returnUrl = 'https://hitchhikersguidetothefuture.com/mincoin/';
  const upstream = await fetch(`${env.PAYMENTS_SERVICE_URL}/v1/campaigns/mincoin/checkout`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${env.PAYMENTS_SERVICE_TOKEN}` },
    body: JSON.stringify({
      amount_cents: amountCents,
      contribution_id: contributionId,
      success_url: `${returnUrl}?status=success`,
      cancel_url: `${returnUrl}?status=cancelled`,
    }),
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { ...headers, 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}
