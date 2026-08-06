function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
  });
}

function sessionCookie(request) {
  const value = request.headers.get('Cookie') || '';
  const match = value.match(/(?:^|;\s*)hgf_session=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function onRequest({ request, env }) {
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'session relay is not configured' }, 503);
  const token = sessionCookie(request);
  if (!token) return json({ error: 'sign in required' }, 401);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/diary/entries`, {
    method: request.method,
    headers: {
      authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}`,
      'x-hgf-session': token,
      ...(request.method === 'POST' ? { 'content-type': 'application/json' } : {}),
    },
    body: request.method === 'POST' ? await request.text() : undefined,
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store' },
  });
}
