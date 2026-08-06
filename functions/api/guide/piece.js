function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers } });
}

export async function onRequestGet({ request, env }) {
  if (!env.HGF_API_SERVICE_TOKEN || !env.HGF_API_SERVICE_URL) return json({ error: 'guide piece service is not configured' }, 503);
  const incoming = new URL(request.url);
  const id = incoming.searchParams.get('id') || '';
  if (!id || !/^(?:(?:bipu|inv|sub)-)?[a-f0-9]{64}$/.test(id)) return json({ error: 'piece id is required' }, 400);
  const upstream = await fetch(`${env.HGF_API_SERVICE_URL}/v1/guide/piece?id=${encodeURIComponent(id)}`, { headers: { authorization: `Bearer ${env.HGF_API_SERVICE_TOKEN}` } });
  return json(await upstream.json(), upstream.status);
}
