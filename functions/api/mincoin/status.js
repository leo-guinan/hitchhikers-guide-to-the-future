const ALLOWED_ORIGINS = new Set([
  'https://hitchhikersguidetothefuture.com',
  'https://www.hitchhikersguidetothefuture.com',
]);

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}

export async function onRequestGet({ request, env }) {
  const origin = request.headers.get('Origin');
  if (origin && !ALLOWED_ORIGINS.has(origin)) return json({ error: 'origin not allowed' }, 403);
  if (!env.PAYMENTS_SERVICE_TOKEN || !env.PAYMENTS_SERVICE_URL) {
    return json({ error: 'payment relay is not configured' }, 503);
  }
  const upstream = await fetch(`${env.PAYMENTS_SERVICE_URL}/v1/campaigns/mincoin`, {
    headers: { authorization: `Bearer ${env.PAYMENTS_SERVICE_TOKEN}` },
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}
