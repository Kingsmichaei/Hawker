import { useEffect, useState } from "react";
import { api, fmt } from "./lib";
import Swatch from "./Swatch";

const TKEY = "hawker.sellerToken";
const getToken = () => { try { return localStorage.getItem(TKEY) || ""; } catch { return ""; } };
const setTokenStore = (t) => { try { localStorage.setItem(TKEY, t); } catch { /* storage blocked */ } };

export default function Seller() {
  const [token, setToken] = useState(getToken());
  const [summary, setSummary] = useState(null);
  const [products, setProducts] = useState([]);
  const [tab, setTab] = useState("orders");
  const [error, setError] = useState("");
  const [transcript, setTranscript] = useState(null);

  async function refresh(t = token) {
    try {
      const [s, p] = await Promise.all([api("/seller/summary", { token: t }), api("/seller/products", { token: t })]);
      setSummary(s);
      setProducts(p);
      setError("");
    } catch (e) {
      setError(e.message);
      setSummary(null);
    }
  }

  useEffect(() => { if (token) refresh(token); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!summary) {
    return (
      <div className="adire flex min-h-full items-center justify-center p-4">
        <form
          onSubmit={(e) => { e.preventDefault(); setTokenStore(token); refresh(token); }}
          className="w-full max-w-sm rounded-2xl bg-resist p-6"
        >
          <h1 className="font-display text-3xl font-extrabold">Seller dashboard</h1>
          <p className="mt-1 text-sm text-ink/70">Enter the seller token from your backend .env.</p>
          <label htmlFor="tok" className="mt-4 block text-sm font-medium">Seller token</label>
          <input id="tok" type="password" value={token} onChange={(e) => setToken(e.target.value)} className="mt-1 w-full rounded-lg border border-indigo-wash px-3 py-2" />
          {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
          <button className="mt-4 w-full rounded-lg bg-indigo-dye py-2.5 font-semibold text-resist">Open dashboard</button>
        </form>
      </div>
    );
  }

  const { stats, store, orders } = summary;
  const cur = store.currency;

  return (
    <div className="min-h-full">
      <header className="adire text-resist">
        <div className="mx-auto max-w-6xl px-4 pb-6 pt-6 sm:px-6">
          <div className="flex items-end justify-between">
            <h1 className="font-display text-4xl font-extrabold leading-none tracking-tight">{store.name}</h1>
            <a href="/" className="rounded-full border border-white/30 px-3 py-1.5 text-sm hover:bg-white/10">Open shop</a>
          </div>
          <dl className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Revenue" value={fmt(stats.revenue_cents, cur)} />
            <Stat label="Paid orders" value={stats.orders_paid} />
            <Stat label="Chats" value={stats.conversations} />
            <Stat label="Chats that bought" value={`${stats.conversion_pct}%`} />
          </dl>
        </div>
      </header>

      <nav className="mx-auto flex max-w-6xl gap-1 px-4 pt-4 sm:px-6" aria-label="Dashboard sections">
        {[["orders", "Orders"], ["products", "Products"], ["settings", "Agent settings"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} aria-current={tab === k} className={`rounded-full px-4 py-2 text-sm font-medium ${tab === k ? "bg-indigo-night text-resist" : "text-indigo-dye hover:bg-indigo-wash/50"}`}>
            {l}
          </button>
        ))}
      </nav>

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {tab === "orders" && <Orders orders={orders} onOpen={async (id) => setTranscript(await api(`/seller/conversations/${id}`, { token }))} />}
        {tab === "products" && <Products products={products} token={token} cur={cur} onChange={refresh} />}
        {tab === "settings" && <Settings store={store} token={token} onSaved={refresh} />}
      </main>

      {transcript && <Transcript t={transcript} onClose={() => setTranscript(null)} />}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <dt className="text-sm text-indigo-wash">{label}</dt>
      <dd className="font-display text-3xl font-bold">{value}</dd>
    </div>
  );
}

function Orders({ orders, onOpen }) {
  if (!orders.length) return <p className="text-ink/70">No orders yet. Share your shop link and the agent will start selling.</p>;
  return (
    <div className="overflow-x-auto rounded-2xl bg-resist ring-1 ring-indigo-wash">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="text-ink/60">
          <tr><th className="p-3 font-medium">When</th><th className="p-3 font-medium">Buyer</th><th className="p-3 font-medium">Items</th><th className="p-3 font-medium">Total</th><th className="p-3 font-medium">Status</th><th className="p-3" /></tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id} className="border-t border-indigo-wash/70 align-top">
              <td className="p-3 whitespace-nowrap">{new Date(o.captured_at || o.created_at).toLocaleString()}</td>
              <td className="p-3">{o.payer_name || "—"}<div className="text-ink/60">{o.payer_email}</div></td>
              <td className="p-3">{o.items.map((i) => `${i.qty}× ${i.name}`).join(", ")}</td>
              <td className="p-3 whitespace-nowrap">
                {fmt(o.total_cents, o.currency)}
                {o.discount_cents > 0 && <div className="text-ochre">−{fmt(o.discount_cents, o.currency)} discount</div>}
              </td>
              <td className="p-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${o.status === "COMPLETED" ? "bg-indigo-dye text-resist" : "bg-cotton text-ink/70"}`}>
                  {o.status === "COMPLETED" ? "Paid" : "Awaiting payment"}
                </span>
              </td>
              <td className="p-3"><button onClick={() => onOpen(o.conversation_id)} className="text-indigo-dye underline">Read chat</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const EMPTY = { name: "", description: "", tags: "", price: "", stock: "" };

function Products({ products, token, cur, onChange }) {
  const [notes, setNotes] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function draft() {
    setBusy(true); setMsg("");
    try {
      const d = await api("/seller/products/draft", { method: "POST", token, body: { notes } });
      setForm((f) => ({ ...f, name: d.name, description: d.description, tags: d.tags.join(", ") }));
    } catch (e) { setMsg(e.message); }
    setBusy(false);
  }

  async function add(e) {
    e.preventDefault(); setMsg("");
    try {
      await api("/seller/products", {
        method: "POST", token,
        body: {
          name: form.name, description: form.description,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
          price_cents: Math.round(parseFloat(form.price) * 100), stock: parseInt(form.stock, 10),
        },
      });
      setForm(EMPTY); setNotes(""); setMsg("Product added. The agent can sell it now.");
      onChange();
    } catch (e) { setMsg(e.message); }
  }

  async function archive(id) {
    await api(`/seller/products/${id}`, { method: "DELETE", token });
    onChange();
  }

  const input = "w-full rounded-lg border border-indigo-wash px-3 py-2";
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <ul className="grid content-start gap-3 sm:grid-cols-2">
        {products.filter((p) => p.active).map((p) => (
          <li key={p.id} className="flex items-start gap-3 self-start rounded-xl bg-resist p-3 ring-1 ring-indigo-wash">
            <Swatch name={p.name} image={p.image_url} className="h-16 w-16 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1">
              <p className="font-display font-bold leading-tight">{p.name}</p>
              <p className="text-sm text-ink/70">{fmt(p.price_cents, cur)}, {p.stock} in stock</p>
              <button onClick={() => archive(p.id)} className="mt-1 text-xs text-ink/60 underline">Remove from shop</button>
            </div>
          </li>
        ))}
      </ul>

      <form onSubmit={add} className="space-y-3 rounded-2xl bg-resist p-5 ring-1 ring-indigo-wash">
        <h2 className="font-display text-xl font-bold">Add a product</h2>
        <div>
          <label htmlFor="notes" className="text-sm font-medium">Describe it in your own words</label>
          <textarea id="notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="small indigo pouch with zip, good for coins and earbuds" className={input} />
          <button type="button" onClick={draft} disabled={busy || notes.trim().length < 3} className="mt-2 rounded-lg border border-indigo-dye px-3 py-1.5 text-sm text-indigo-dye disabled:opacity-40">
            {busy ? "Writing…" : "Write the listing for me"}
          </button>
        </div>
        <Field label="Name"><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={input} /></Field>
        <Field label="Description"><textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={input} /></Field>
        <Field label="Search words (comma separated)"><input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} className={input} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={`Price (${cur})`}><input required type="number" min="0.01" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} className={input} /></Field>
          <Field label="Stock"><input required type="number" min="0" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} className={input} /></Field>
        </div>
        {msg && <p className="text-sm text-indigo-dye">{msg}</p>}
        <button className="w-full rounded-lg bg-indigo-dye py-2.5 font-semibold text-resist">Add product</button>
      </form>
    </div>
  );
}

function Field({ label, children }) {
  return <label className="block text-sm font-medium">{label}<div className="mt-1 font-normal">{children}</div></label>;
}

function Settings({ store, token, onSaved }) {
  const [s, setS] = useState({ name: store.name, tagline: store.tagline, max_discount_pct: store.max_discount_pct, policies: store.policies });
  const [msg, setMsg] = useState("");
  async function saveIt(e) {
    e.preventDefault();
    try {
      await api("/seller/store", { method: "PATCH", token, body: { ...s, max_discount_pct: Number(s.max_discount_pct) } });
      setMsg("Saved. The agent uses these from the next message.");
      onSaved();
    } catch (err) { setMsg(err.message); }
  }
  const input = "w-full rounded-lg border border-indigo-wash px-3 py-2";
  return (
    <form onSubmit={saveIt} className="max-w-xl space-y-4 rounded-2xl bg-resist p-5 ring-1 ring-indigo-wash">
      <Field label="Shop name"><input value={s.name} onChange={(e) => setS({ ...s, name: e.target.value })} className={input} /></Field>
      <Field label="Tagline"><input value={s.tagline} onChange={(e) => setS({ ...s, tagline: e.target.value })} className={input} /></Field>
      <Field label={`Largest discount the agent may give: ${s.max_discount_pct}%`}>
        <input type="range" min="0" max="50" value={s.max_discount_pct} onChange={(e) => setS({ ...s, max_discount_pct: e.target.value })} className="w-full accent-[#2b4594]" />
      </Field>
      <Field label="What the agent should know (shipping, returns, tone)">
        <textarea rows={5} value={s.policies} onChange={(e) => setS({ ...s, policies: e.target.value })} className={input} />
      </Field>
      {msg && <p className="text-sm text-indigo-dye">{msg}</p>}
      <button className="rounded-lg bg-indigo-dye px-5 py-2.5 font-semibold text-resist">Save settings</button>
    </form>
  );
}

function Transcript({ t, onClose }) {
  return (
    <div className="fixed inset-0 z-10 flex justify-end bg-ink/40" onClick={onClose}>
      <div role="dialog" aria-label="Chat transcript" className="h-full w-full max-w-md overflow-y-auto bg-cotton p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl font-bold">How this sale happened</h2>
          <button onClick={onClose} className="rounded-full px-3 py-1 text-sm hover:bg-indigo-wash">Close</button>
        </div>
        {t.discount_reason && <p className="mt-2 text-sm text-ochre">Discount given because: {t.discount_reason}</p>}
        <ol className="mt-4 space-y-3">
          {t.transcript.map((m, i) => (
            <li key={i} className={m.role === "buyer" ? "text-right" : ""}>
              <p className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-xl px-3 py-2 text-left text-sm ${m.role === "buyer" ? "bg-indigo-dye text-resist" : m.role === "system" ? "bg-ochre/15 text-ink" : "bg-resist"}`}>{m.text}</p>
              {m.tools?.length > 0 && <p className="mt-1 text-xs text-ink/50">Agent used: {m.tools.join(", ")}</p>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
