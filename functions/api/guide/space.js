function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers } });
}

export async function onRequestGet({ request, env }) {
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'guide space is not configured' }, 503);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/guide/space`, { headers: { authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}` } });
  return json(await upstream.json(), upstream.status);
}
