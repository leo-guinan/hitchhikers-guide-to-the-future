function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers } });
}

function sessionCookie(request) {
  const match = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)hgf_session=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function onRequestGet({ request, env }) {
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'session relay is not configured' }, 503);
  const token = sessionCookie(request);
  if (!token) return json({ error: 'sign in required' }, 401);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/session`, {
    headers: { authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}`, 'x-hgf-session': token },
  });
  const body = await upstream.json();
  if (!upstream.ok) return json(body, upstream.status);
  return json({ ...body, email: body.email || null });
}
