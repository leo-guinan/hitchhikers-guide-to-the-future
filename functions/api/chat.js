function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers } });
}

function sessionCookie(request) {
  const match = (request.headers.get('Cookie') || '').match(/(?:^|;\s*)hgf_session=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function onRequestPost({ request, env }) {
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'AI chat service is not configured' }, 503);
  const token = sessionCookie(request);
  if (!token) return json({ error: 'sign in required' }, 401);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/chat`, {
    method: 'POST',
    headers: { authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}`, 'x-hgf-session': token, 'content-type': 'application/json' },
    body: await request.text(),
  });
  return new Response(await upstream.text(), { status: upstream.status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}
