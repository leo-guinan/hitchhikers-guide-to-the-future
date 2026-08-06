const ALLOWED_ORIGINS = new Set([
  'https://guide.hitchhikersguidetothefuture.com',
  'https://hitchhikersguidetothefuture.com',
  'https://www.hitchhikersguidetothefuture.com',
]);

function allowedOrigin(origin) {
  return ALLOWED_ORIGINS.has(origin) || origin.endsWith('.hitchhikers-guide.pages.dev');
}

function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers } });
}

function visitorCookie(request) {
  const match = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)guide_visitor=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : crypto.randomUUID();
}

export async function onRequestPost({ request, env }) {
  const origin = request.headers.get('Origin');
  const cors = origin && allowedOrigin(origin) ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {};
  if (origin && !allowedOrigin(origin)) return json({ error: 'origin not allowed' }, 403, cors);
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'guide search is not configured' }, 503, cors);
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400, cors); }
  const visitor = visitorCookie(request);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/guide/search`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}` },
    body: JSON.stringify({ query: body?.query, visitor_id: visitor }),
  });
  const headers = { ...cors };
  if (!request.headers.get('Cookie')?.includes('guide_visitor=')) headers['Set-Cookie'] = `guide_visitor=${encodeURIComponent(visitor)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=31536000`;
  return json(await upstream.json(), upstream.status, headers);
}
