const ALLOWED_ORIGINS = new Set([
  'https://hitchhikersguidetothefuture.com',
  'https://www.hitchhikersguidetothefuture.com',
]);

function cors(request) {
  const origin = request.headers.get('Origin');
  return origin && ALLOWED_ORIGINS.has(origin)
    ? { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', Vary: 'Origin' }
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
  if (!body || typeof body !== 'object' || body.node_id !== 'hgf:guide' || typeof body.subject_id !== 'string') {
    return json({ error: 'invalid checkout request' }, 400, headers);
  }
  const priceId = env.HGF_STRIPE_PRICE_ID || body.price_id;
  if (!priceId || !String(priceId).startsWith('price_')) {
    return json({ error: 'membership price is not configured' }, 503, headers);
  }
  body.price_id = priceId;
  const upstream = await fetch(`${env.PAYMENTS_SERVICE_URL}/v1/checkout/sessions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${env.PAYMENTS_SERVICE_TOKEN}` },
    body: JSON.stringify(body),
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { ...headers, 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}
