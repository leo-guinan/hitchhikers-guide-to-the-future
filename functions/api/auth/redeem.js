const ALLOWED_ORIGINS = new Set([
  'https://hitchhikersguidetothefuture.com',
  'https://www.hitchhikersguidetothefuture.com',
]);

function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
  });
}

export async function onRequestPost({ request, env }) {
  const origin = request.headers.get('Origin');
  const cors = origin && ALLOWED_ORIGINS.has(origin) ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {};
  if (origin && !ALLOWED_ORIGINS.has(origin)) return json({ error: 'origin not allowed' }, 403, cors);
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'session relay is not configured' }, 503, cors);
  let body;
  try { body = await request.json(); } catch { return json({ error: 'invalid JSON' }, 400, cors); }
  if (!body || typeof body.handoff !== 'string' || body.handoff.length < 20) return json({ error: 'handoff is required' }, 400, cors);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/auth/redeem`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}` },
    body: JSON.stringify({ handoff: body.handoff }),
  });
  const result = await upstream.json();
  if (!upstream.ok) return json(result, upstream.status, cors);
  const cookie = `hgf_session=${encodeURIComponent(result.session_token)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${Math.min(result.expires_in || 1209600, 1209600)}`;
  return json({ authenticated: true, node_id: result.node_id, expires_in: result.expires_in }, 200, { ...cors, 'Set-Cookie': cookie });
}
