export async function api(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["x-seller-token"] = token;
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export function fmt(cents, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format((cents || 0) / 100);
}

// Deterministic hue per product so swatches stay the same between visits.
export function swatchSeed(name = "") {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h;
}
